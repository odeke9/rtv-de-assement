from __future__ import annotations

import duckdb
import pandas as pd

from config import config
from utils.helpers import log_event


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    config.WAREHOUSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Explicit cap + spill dir: inside a container DuckDB otherwise sizes itself to the host's RAM.
    return duckdb.connect(str(config.WAREHOUSE_PATH), read_only=read_only,
                          config={"memory_limit": config.DUCKDB_MEMORY_LIMIT,
                                  "temp_directory": str(config.LAKE_DIR / "duckdb_tmp")})


def write_table(con, name: str, df: pd.DataFrame) -> None:
    con.register("_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _df")
    con.unregister("_df")


def render(sql: str) -> str:
    cycle_values = ", ".join(
        f"('{c.code}', {c.order}, '{c.label}', '{c.csv}', '{c.form}', "
        f"{repr(c.choice_list_cycle) if c.choice_list_cycle else 'NULL'})" for c in config.CYCLES)
    return (sql.replace("{silver}", str(config.SILVER_DIR))
               .replace("{cycle_values}", cycle_values)
               .replace("{n_cycles}", str(len(config.CYCLES)))
               .replace("{ultra_poor}", str(config.ULTRA_POOR_USD_DAY))
               .replace("{target}", str(config.TARGET_USD_DAY))
               .replace("{config_dir}", str(config.VARIABLE_MAP.parent))
               .replace("{choice_sources}", ", ".join(
                   f"('{c.code}', '{c.choice_list_cycle or c.code}')" for c in config.CYCLES)))


def build_warehouse(meta: dict[str, pd.DataFrame]) -> dict[str, int]:
    with connect() as con:
        for name, df in meta.items():
            write_table(con, name, df)
        for path in sorted(config.SQL_DIR.glob("*.sql")):  # file order = dependency order
            con.execute(render(path.read_text()))
            log_event("sql_model", file=path.name)
        counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                  for t in ("fct_survey_submissions", "dim_survey_cycle", "dim_geography", "dim_time",
                            "dim_household", "rpt_field_operations", "rpt_program_summary")}
    log_event("warehouse_built", **counts)
    return counts
