"""Indian Startup Funding - data cleaning + EDA.
Run: python analysis.py  (reads startup_funding.csv, writes startup_funding_clean.csv and v1-v8 chart PNGs)
"""
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="whitegrid", palette="deep")
RAW, CLEAN, IMG = "startup_funding.csv", "startup_funding_clean.csv", ""

# ---------------- 1. LOAD ----------------
df = pd.read_csv(RAW)
print("Raw shape:", df.shape)
report = {"raw_rows": len(df)}

# ---------------- 2. TIDY COLUMN NAMES ----------------
df.columns = ["sr_no", "date", "startup", "industry", "subvertical",
              "city", "investors", "investment_type", "amount_usd", "remarks"]
df = df.drop(columns=["sr_no"])

def strip_junk(s):
    """Remove escaped non-breaking spaces (\\xc2\\xa0), newlines and extra spaces."""
    if pd.isna(s):
        return s
    s = str(s).replace("\\\\xc2\\\\xa0", " ").replace("\\xc2\\xa0", " ").replace("\\\\n", " ").replace("\\n", " ")
    return re.sub(r"\s+", " ", s).strip()

for c in ["date", "startup", "industry", "subvertical", "city", "investors", "investment_type", "amount_usd", "remarks"]:
    df[c] = df[c].apply(strip_junk)

# ---------------- 3. DATA TYPES ----------------
# 3a. Dates: fix typos like '12/05.2015', '22/01//2015', '05/072018', '01/07/015'
fix = {"05/072018": "05/07/2018", "01/07/015": "01/07/2015"}
df["date"] = df["date"].replace(fix).str.replace(".", "/", regex=False).str.replace("//", "/", regex=False)
df["date"] = pd.to_datetime(df["date"], format="%d/%m/%Y", errors="coerce")
report["bad_dates_after_fix"] = int(df["date"].isna().sum())
df["year"] = df["date"].dt.year
df["month"] = df["date"].dt.to_period("M")

# 3b. Amount: '20,00,00,000' / 'undisclosed' / 'N/A' -> float
amt = df["amount_usd"].astype(str).str.replace(",", "", regex=False).str.replace("+", "", regex=False)
df["amount_usd"] = pd.to_numeric(amt, errors="coerce")
df.loc[df["amount_usd"] <= 0, "amount_usd"] = np.nan

# ---------------- 4. STANDARDISE CATEGORIES ----------------
city_map = {"Bengaluru": "Bangalore", "Gurugram": "Gurgaon", "Delhi": "New Delhi",
            "Nw Delhi": "New Delhi", "Ahemadabad": "Ahmedabad", "Ahemdabad": "Ahmedabad",
            "Bombay": "Mumbai", "Kolkatta": "Kolkata"}
df["city"] = df["city"].str.split("/").str[0].str.strip().replace(city_map)

def clean_type(t):
    if pd.isna(t):
        return np.nan
    t = t.lower()
    if "seed" in t or "angel" in t or "angle" in t:
        return "Seed / Angel"
    if "private equity" in t or t == "equity":
        return "Private Equity"
    if "debt" in t:
        return "Debt"
    if "series" in t:
        return "Series A+ (Venture)"
    return "Other"
df["investment_type"] = df["investment_type"].apply(clean_type)

ind = df["industry"].str.lower().str.replace(r"[^a-z ]", "", regex=True).str.strip()
ind_map = {"ecommerce": "E-Commerce", "e commerce": "E-Commerce", "consumer internet": "Consumer Internet",
           "technology": "Technology", "fintech": "FinTech", "finance": "FinTech", "healthcare": "Healthcare",
           "edtech": "EdTech", "education": "EdTech", "etech": "EdTech", "logistics": "Logistics"}
df["industry"] = ind.map(ind_map).fillna(df["industry"])

ind_map2 = {"Food and Beverage": "Food & Beverage", "IT": "Technology"}
df["industry"] = df["industry"].replace(ind_map2)

# startup names: drop '.com', unify known variants
df["startup"] = (df["startup"].str.replace(r"\.com$|\.in$", "", regex=True).str.strip()
                 .replace({"Ola Cabs": "Ola", "OYO Rooms": "OYO", "Oyo Rooms": "OYO", "OyoRooms": "OYO",
                           "Oyo": "OYO", "Paytm Marketplace": "Paytm", "Byju's": "BYJU'S", "BYJU’S": "BYJU'S"}))

df["investors"] = df["investors"].replace({"Undisclosed Investors": "Undisclosed", "Undisclosed investors": "Undisclosed"})

# ---------------- 5. MISSING VALUES ----------------
report["missing_before"] = df.isna().sum().to_dict()
df = df.drop(columns=["remarks"])                        # ~86% empty -> dropped
for c in ["industry", "subvertical", "city", "investors", "investment_type"]:
    df[c] = df[c].fillna("Unknown")                      # categorical -> 'Unknown'
df["amount_disclosed"] = df["amount_usd"].notna()       # amount kept NaN (undisclosed), flagged

# ---------------- 6. DUPLICATES ----------------
before = len(df)
df = df.drop_duplicates(subset=["date", "startup", "investment_type", "amount_usd", "investors"])
report["duplicates_removed"] = before - len(df)

# ---------------- 7. OUTLIERS (IQR on log amount) ----------------
log_amt = np.log10(df["amount_usd"].dropna())
q1, q3 = log_amt.quantile([.25, .75]); iqr = q3 - q1
lo, hi = 10 ** (q1 - 1.5 * iqr), 10 ** (q3 + 1.5 * iqr)
df["is_outlier"] = (df["amount_usd"] < lo) | (df["amount_usd"] > hi)
report["outlier_bounds_usd"] = (round(lo), round(hi))
report["outliers"] = int(df["is_outlier"].sum())
# Known data-entry error: Rapido Bike Taxi 3.9 B (actual round ~USD 52 M) -> set NaN
bad = df["amount_usd"] > 3e9
report["data_entry_errors_fixed"] = int(bad.sum())
df.loc[bad, "amount_usd"] = np.nan
df.loc[bad, "amount_disclosed"] = False

df.to_csv(CLEAN, index=False)
report["clean_rows"] = len(df)
print("Cleaning report:"); [print(" ", k, ":", v) for k, v in report.items()]

# ---------------- 8. VISUALIZATIONS ----------------
def save(name):
    plt.tight_layout(); plt.savefig(IMG + name, dpi=150); plt.close()

d = df[df["year"].between(2015, 2020)]

# V1 deals + funding per year
yr = d.groupby("year").agg(deals=("startup", "size"), funding=("amount_usd", "sum"))
fig, ax1 = plt.subplots(figsize=(9, 5))
ax1.bar(yr.index, yr["deals"], color="#4C72B0", label="Number of deals")
ax1.set_ylabel("Number of deals"); ax1.set_xlabel("Year")
ax2 = ax1.twinx(); ax2.plot(yr.index, yr["funding"] / 1e9, color="#DD8452", marker="o", lw=2.5, label="Funding (USD bn)")
ax2.set_ylabel("Total funding (USD billion)"); ax2.grid(False)
ax1.set_title("V1. Deals vs total funding per year (2020 = January only)")
fig.legend(loc="upper center", bbox_to_anchor=(0.5, 0.86), ncol=2); save("v1_yearly_trend.png")

# V2 top cities
city = d[d.city != "Unknown"]["city"].value_counts().head(10)
plt.figure(figsize=(9, 5)); sns.barplot(x=city.values, y=city.index, color="#4C72B0")
plt.title("V2. Top 10 cities by number of funding deals"); plt.xlabel("Number of deals"); plt.ylabel("")
save("v2_top_cities.png")

# V3 top industries
indc = d[d.industry != "Unknown"]["industry"].value_counts().head(10)
plt.figure(figsize=(9, 5)); sns.barplot(x=indc.values, y=indc.index, color="#55A868")
plt.title("V3. Top 10 industry verticals by number of deals"); plt.xlabel("Number of deals"); plt.ylabel("")
save("v3_top_industries.png")

# V4 top startups by total funding
top_s = d.groupby("startup")["amount_usd"].sum().sort_values(ascending=False).head(10) / 1e6
plt.figure(figsize=(9, 5)); sns.barplot(x=top_s.values, y=top_s.index, color="#C44E52")
plt.title("V4. Top 10 startups by total funding raised"); plt.xlabel("Total funding (USD million)"); plt.ylabel("")
save("v4_top_startups.png")

# V5 investment type: deals vs money share
it = d[d.investment_type != "Unknown"].groupby("investment_type").agg(deals=("startup", "size"), funding=("amount_usd", "sum"))
it_pct = (it / it.sum() * 100).sort_values("deals", ascending=False)
it_pct.plot(kind="bar", figsize=(9, 5), color=["#4C72B0", "#DD8452"])
plt.title("V5. Share of deals vs share of money by investment type"); plt.ylabel("% of total"); plt.xlabel("")
plt.xticks(rotation=0); plt.legend(["% of deals", "% of funding"]); save("v5_investment_type.png")

# V6 distribution of deal size (log) + boxplot for outliers
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
sns.histplot(np.log10(d["amount_usd"].dropna()), bins=30, ax=axes[0], color="#8172B3")
axes[0].set_xlabel("Deal size (log10 USD)"); axes[0].set_title("Distribution of deal size")
sns.boxplot(x=np.log10(d["amount_usd"].dropna()), ax=axes[1], color="#8172B3", fliersize=4)
axes[1].set_xlabel("Deal size (log10 USD): 6 = USD 1 M, 8 = USD 100 M"); axes[1].set_title("Outliers (boxplot)")
fig.suptitle("V6. How big is a typical funding round?"); save("v6_amount_distribution.png")

# V7 top investors (split multi-investor strings)
inv = (d["investors"].str.split(",").explode().str.strip())
inv = inv[~inv.isin(["Unknown", "Undisclosed", "", "Undisclosed Investor", "undisclosed investors"])]
top_inv = inv.value_counts().head(10)
plt.figure(figsize=(9, 5)); sns.barplot(x=top_inv.values, y=top_inv.index, color="#937860")
plt.title("V7. Most active investors (number of deals)"); plt.xlabel("Number of deals"); plt.ylabel("")
save("v7_top_investors.png")

# V8 heatmap city x year
top5 = city.head(6).index
hm = d[d.city.isin(top5)].pivot_table(index="city", columns="year", values="startup", aggfunc="size").fillna(0).astype(int)
hm = hm.loc[top5]
plt.figure(figsize=(9, 4.5)); sns.heatmap(hm, annot=True, fmt="d", cmap="Blues")
plt.title("V8. Deals per year in the top 6 cities"); plt.xlabel("Year"); plt.ylabel("")
save("v8_city_year_heatmap.png")

# numbers for the report
print("\nYEARLY\n", yr.assign(funding_bn=yr.funding / 1e9).round(2))
print("\nCITY\n", city); print("\nIND\n", indc); print("\nTOP STARTUPS (USD m)\n", top_s.round(0))
print("\nTYPE %\n", it_pct.round(1)); print("\nINVESTORS\n", top_inv)
print("\nAMOUNT median/mean (USD m):", round(d.amount_usd.median() / 1e6, 2), round(d.amount_usd.mean() / 1e6, 2))
print("disclosed share:", round(d.amount_disclosed.mean() * 100, 1))
print("HEATMAP\n", hm)

cf = d.groupby("city")["amount_usd"].sum().sort_values(ascending=False)
print("\nCITY FUNDING SHARE %\n", (cf / cf.sum() * 100).head(5).round(1))
print("top4 deal share:", round(city.head(4).sum() / d[d.city != "Unknown"].shape[0] * 100, 1))
print("top3 ind share:", round(indc.head(3).sum() / len(d) * 100, 1))
print("total funding bn:", round(d.amount_usd.sum() / 1e9, 1))
