import re
import pandas as pd
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from config import config

D = config.DATA_DIR
files = {"baseline": "01_baseline.csv", "year1": "02_year_one.csv", "year2": "03_year_two.csv"}
d = {k: pd.read_csv(D / f, dtype=str, low_memory=False) for k, f in files.items()}

# shape
for k, df in d.items():
    print(k, df.shape, "all-null cols:", int(df.isna().all().sum()))

print("\n")

# key hhid2
for k, df in d.items():
    h = df["hhid_2"]
    print(k, "null ids:", h.isna().sum(), "unique:", h.nunique(), "rows w/ dup id:", h.duplicated(keep=False).sum())

print("\n")

# overlap hhid2
ids = {k: set(df["hhid_2"].dropna()) for k, df in d.items()}
norm = {k: {re.sub(r"\s+", "", i.upper()) for i in v} for k, v in ids.items()}
print("in all 3 rounds, raw:", len(ids["baseline"] & ids["year1"] & ids["year2"]),
      "normalized:", len(norm["baseline"] & norm["year1"] & norm["year2"]))

print("\n")

# schema drift
cols = {k: set(df.columns) for k, df in d.items()}
print("shared by all:", len(cols["baseline"] & cols["year1"] & cols["year2"]))

print("\n")

for k, df in d.items():
    print(k, df["SubmissionDate"].dropna().sample(3, random_state=1).tolist())

print("\n")
for k, df in d.items():
    print(k, pd.crosstab(df["district"], df["pre_district"]), sep="\n")
