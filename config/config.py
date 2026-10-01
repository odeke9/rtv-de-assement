from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]

DATA_DIR = Path(os.environ.get("RTV_DATA_DIR", PROJECT_DIR / "Assessment/data"))

LAKE_DIR = Path(os.environ.get("RTV_LAKE_DIR", PROJECT_DIR / "lake"))
RAW_DIR = LAKE_DIR / "raw"
BRONZE_DIR = LAKE_DIR / "bronze"
SILVER_DIR = LAKE_DIR / "silver"
WAREHOUSE_PATH = LAKE_DIR / "warehouse.duckdb"
DUCKDB_MEMORY_LIMIT = os.environ.get("RTV_DUCKDB_MEMORY_LIMIT", "1GB")

LOG_DIR = PROJECT_DIR / "logs"
SQL_DIR = PROJECT_DIR / "sql"
VARIABLE_MAP = PROJECT_DIR / "config" / "variable_map.csv"

ULTRA_POOR_USD_DAY = 1.0
TARGET_USD_DAY = 2.0
MAX_HHIP_USD_DAY = 50
HH_SIZE_RANGE = (1, 30)


@dataclass(frozen=True)
class SurveyCycle:
    code: str          # stable key used in paths and the warehouse
    order: int         # 0 = baseline, 1 = year 1, 2 = year 2
    label: str
    csv: str
    form: str          # SurveyCTO form definition
    ts_format: tuple
    # Year 1 exported codes follow the Year 2 form's choice lists, not its own form.
    choice_list_cycle: str | None = None


CYCLES: tuple[SurveyCycle, ...] = (
    SurveyCycle("baseline", 0, "Baseline", "01_baseline.csv", "ahs_2021_baseline.html", ("%m/%d/%Y, %I:%M:%S %p",)),
    SurveyCycle("year1", 1, "Year 1", "02_year_one.csv", "ahs_2021_year1.html", ("%b %d, %Y %I:%M:%S %p",), "year2"),
    SurveyCycle("year2", 2, "Year 2", "03_year_two.csv", "ahs_2021_year2.html", ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f")),
)

CYCLE_BY_CODE = {c.code: c for c in CYCLES}
