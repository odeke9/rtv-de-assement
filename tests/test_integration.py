"""Integration tests on the built lake/warehouse. Skipped until `python -m pipeline.run` has run."""
import duckdb
import pandas as pd
import pytest

from config import config
from pipeline.harmonize import load_variable_map
from pipeline import ingest
from pipeline.ingest import bronze_columns, bronze_path, read_bronze

built = pytest.mark.skipif(not config.WAREHOUSE_PATH.exists(), reason="warehouse not built")


def bronze_rows() -> int:
    return sum(len(read_bronze(c.code, columns=["KEY"])) for c in config.CYCLES)


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(config.WAREHOUSE_PATH), read_only=True)
    yield c
    c.close()


@built
def test_every_mapped_source_column_exists():
    vm = load_variable_map()
    for r in config.CYCLES:
        cols = set(bronze_columns(r.code))
        missing = [c for c in vm[r.code] if c and c not in cols]
        assert not missing, (r.code, missing)


@built
def test_fact_grain_is_household_cycle(con):
    dup = con.execute("SELECT count(*) FROM (SELECT household_id, survey_cycle FROM fct_survey_submissions "
                      "GROUP BY ALL HAVING count(*) > 1)").fetchone()[0]
    assert dup == 0


@built
def test_row_reconciliation_bronze_equals_silver_plus_quarantine(con):
    silver = con.execute("SELECT count(*) FROM stg_household_cycle").fetchone()[0]
    quarantine = con.execute("SELECT count(*) FROM stg_quarantine").fetchone()[0]
    assert bronze_rows() == silver + quarantine


@built
def test_daily_metric_reconciles_with_annual(con):
    bad = con.execute("SELECT count(*) FROM fct_survey_submissions WHERE abs(hhip_usd_day*365 - hhip_usd_year) "
                      "> 0.01 * greatest(hhip_usd_year, 1)").fetchone()[0]
    assert bad == 0


@built
def test_year1_codes_decode_with_year2_lists(con):
    # the district code is our Rosetta stone: decoded label must equal the preloaded label
    bad = con.execute("SELECT count(*) FROM (SELECT DISTINCT survey_cycle, district_code, district FROM stg_household_cycle "
                      "WHERE survey_cycle <> 'baseline') t WHERE lower(choice_label(t.survey_cycle, 'district', t.district_code)) "
                      "IS DISTINCT FROM lower(t.district)").fetchone()[0]
    assert bad == 0


@built
def test_panel_uses_normalised_ids(con):
    n = con.execute("SELECT count(*) FROM dim_household WHERE in_balanced_panel").fetchone()[0]
    assert n >= 500      # 474 without household-ID normalisation


@built
def test_required_gold_objects_exist(con):
    names = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    required = {"fct_survey_submissions", "dim_geography", "dim_time", "dim_survey_cycle",
                "rpt_field_operations", "rpt_program_summary"}
    assert required <= names, required - names


@built
def test_bronze_has_ingest_metadata_and_is_write_once():
    meta = {"_ingested_at", "_source_file", "_survey_cycle", "_row_hash"}
    for c in config.CYCLES:
        assert meta <= set(bronze_columns(c.code)), c.code
    before = {c.code: bronze_path(c.code).stat().st_mtime_ns for c in config.CYCLES}
    ingest.build_bronze()
    assert before == {c.code: bronze_path(c.code).stat().st_mtime_ns for c in config.CYCLES}


@built
def test_field_operations_account_for_every_bronze_row(con):
    raw = con.execute("SELECT sum(submissions_raw) FROM rpt_field_operations").fetchone()[0]
    empty = con.execute("SELECT count(*) FROM stg_quarantine WHERE reject_reason = 'empty_row'").fetchone()[0]
    assert raw + empty == bronze_rows()


@built
def test_dim_time_covers_every_submission_date(con):
    missing = con.execute("SELECT count(*) FROM rpt_field_operations o LEFT JOIN dim_time t USING (date_key) "
                          "WHERE t.date_key IS NULL").fetchone()[0]
    assert missing == 0


@built
def test_program_rates_are_consistent(con):
    bad = con.execute("SELECT count(*) FROM rpt_program_summary WHERE NOT (households_consented <= households_completed "
                      "AND households_completed <= households_attempted AND completion_rate BETWEEN 0 AND 1)").fetchone()[0]
    assert bad == 0
