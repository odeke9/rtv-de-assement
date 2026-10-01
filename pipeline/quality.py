from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from config import config
from pipeline.catalog import schema_drift
from pipeline.harmonize import parse_timestamps
from pipeline.ingest import bronze_columns, read_bronze
from utils.helpers import log_event
from pipeline.warehouse import connect, write_table

# Two ID layouts exist: DIS-SUB-ABC-K1234 (most) and RUB-KAG-M-2177 (Rubanda)
HHID_PATTERN = r"^[A-Z]{3}-[A-Z]{3}-([A-Z]{3}-[A-Z]|[A-Z]-)[0-9]+$"

SQL_CHECKS = [
    ("grain_unique_household_cycle", "error",
     "SELECT count(*) - count(DISTINCT (household_id, survey_cycle)), count(*) FROM fct_survey_submissions"),
    ("household_id_format", "warn",
     f"SELECT count(*) FILTER (WHERE NOT regexp_matches(household_id, '{HHID_PATTERN}')), count(*) FROM fct_survey_submissions"),
    ("household_id_needed_normalisation", "info",
     "SELECT count(*) FILTER (WHERE household_id_raw <> household_id), count(*) FROM stg_household_cycle"),
    ("hh_size_in_range", "warn",
     f"SELECT count(*) FILTER (WHERE hh_size NOT BETWEEN {config.HH_SIZE_RANGE[0]} AND {config.HH_SIZE_RANGE[1]} OR hh_size IS NULL), count(*) FROM fct_survey_submissions"),
    ("hhip_not_null", "error",
     "SELECT count(*) FILTER (WHERE hhip_usd_day IS NULL), count(*) FROM fct_survey_submissions WHERE is_consented"),
    ("hhip_plausible_range", "warn",
     f"SELECT count(*) FILTER (WHERE hhip_usd_day < 0 OR hhip_usd_day > {config.MAX_HHIP_USD_DAY}), count(*) FROM fct_survey_submissions"),
    ("hhip_daily_reconciles_with_annual", "warn",
     "SELECT count(*) FILTER (WHERE abs(hhip_usd_day * 365 - hhip_usd_year) > 0.01 * greatest(hhip_usd_year, 1)), "
     "count(*) FROM fct_survey_submissions WHERE hhip_usd_year IS NOT NULL"),
    ("income_components_le_total_income", "warn",
     "SELECT count(*) FILTER (WHERE coalesce(inc_seasonal_crops_usd,0)+coalesce(inc_perennial_crops_usd,0)+coalesce(inc_livestock_usd,0)"
     "+coalesce(inc_casual_labour_usd,0)+coalesce(inc_formal_employment_usd,0)+coalesce(inc_business_usd,0)"
     "+coalesce(inc_remittances_usd,0)+coalesce(inc_rent_usd,0) > hh_income_usd_year * 1.01 + 1), count(*) FROM fct_survey_submissions"),
    ("village_maps_to_one_parish_within_cycle", "warn",
     "SELECT count(*) FILTER (WHERE n > 1), count(*) FROM (SELECT survey_cycle, geo_key, count(DISTINCT lower(parish)) n "
     "FROM dim_geography_name_history GROUP BY ALL)"),
    ("villages_with_parish_spelling_change_across_cycles", "info",
     "SELECT count(*) FILTER (WHERE parish_spellings_seen > 1), count(*) FROM dim_geography"),
    ("fact_rows_without_geography", "error",
     "SELECT count(*) FILTER (WHERE g.geo_key IS NULL), count(*) FROM fct_survey_submissions f LEFT JOIN dim_geography g USING (geo_key)"),
    ("interview_duration_plausible_10min_6h", "warn",
     "SELECT count(*) FILTER (WHERE interview_duration_min < 10 OR interview_duration_min > 360), count(*) "
     "FROM fct_survey_submissions WHERE is_completed"),
    ("wall_clock_start_to_end_over_6h", "info",
     "SELECT count(*) FILTER (WHERE wall_clock_minutes > 360), count(*) FROM fct_survey_submissions"),
    ("head_age_plausible_15_100", "warn",
     "SELECT count(*) FILTER (WHERE head_age NOT BETWEEN 15 AND 100 OR head_age IS NULL), count(*) "
     "FROM fct_survey_submissions WHERE is_consented"),
    ("completed_interview_has_consent_answer", "warn",
     "SELECT count(*) FILTER (WHERE consent IS NULL), count(*) FROM fct_survey_submissions WHERE is_completed"),
    ("fact_dates_covered_by_dim_time", "error",
     "SELECT count(*) FILTER (WHERE t.date_key IS NULL), count(*) FROM fct_survey_submissions f LEFT JOIN dim_time t USING (date_key)"),
    ("geography_has_region", "error",
     "SELECT count(*) FILTER (WHERE region_code IS NULL), count(*) FROM dim_geography"),
    ("submitted_after_started", "warn",
     "SELECT count(*) FILTER (WHERE s.submitted_at < s.started_at - INTERVAL 1 DAY), count(*) FROM stg_household_cycle s"),
    ("district_code_decodes_to_preloaded_label", "warn",
     "SELECT count(*) FILTER (WHERE coalesce(lower(choice_label(t.survey_cycle, 'district', t.district_code)), '?') "
     "<> lower(t.district)), count(*) FROM (SELECT DISTINCT survey_cycle, district_code, district FROM stg_household_cycle) t"),
    ("households_changed_district", "info",
     "SELECT count(*) FILTER (WHERE moved_district), count(*) FROM dim_household"),
    ("baseline_households_missing_a_follow_up_cycle", "info",
     "SELECT count(*) FILTER (WHERE has_baseline AND NOT in_balanced_panel), count(*) FILTER (WHERE has_baseline) FROM dim_household"),
]


def source_checks() -> list[dict]:
    """Checks that need the raw/bronze shape (before harmonisation)."""
    out = []
    for rnd in config.CYCLES:
        cols = bronze_columns(rnd.code)
        b = read_bronze(rnd.code, columns=["_row_hash", "hhid_2", "hhid_2_again", "district", "pre_district",
                                           "SubmissionDate"])
        out.append(dict(check=f"{rnd.code}: identical rows in export (same row hash)", severity="info",
                        failed=int(b._row_hash.duplicated().sum()), total=len(b)))
        mism = int((b.hhid_2.fillna("") != b.hhid_2_again.fillna("")).sum())
        out.append(dict(check=f"{rnd.code}: hhid_2 equals hhid_2_again", severity="warn", failed=mism, total=len(b)))
        codes = b.dropna(subset=["district", "pre_district"]).groupby("district")["pre_district"].nunique()
        out.append(dict(check=f"{rnd.code}: district code maps to one label", severity="warn",
                        failed=int((codes > 1).sum()), total=int(len(codes)),
                        detail="; ".join(f"{k}={v}" for k, v in b.dropna(subset=["district"])
                                         .groupby("district")["pre_district"].first().items())))
        parsed = parse_timestamps(b.SubmissionDate.astype("string").str.strip(), rnd.ts_format)
        out.append(dict(check=f"{rnd.code}: SubmissionDate parses with known formats", severity="error",
                        failed=int(parsed.isna().sum() - b.SubmissionDate.isna().sum()), total=len(b),
                        detail=" / ".join(rnd.ts_format)))
        dup_headers = [c for c in cols if c.endswith(".1")]
        out.append(dict(check=f"{rnd.code}: duplicate headers in export (pandas '.1' suffix)", severity="info",
                        failed=len(dup_headers), total=len(cols), detail=", ".join(dup_headers[:6])))
    return out


def run_quality() -> pd.DataFrame:
    rows = source_checks()
    for r in rows:
        r.setdefault("detail", "")
    with connect() as con:
        for name, severity, sql in SQL_CHECKS:
            failed, total = con.execute(sql).fetchone()
            rows.append(dict(check=name, severity=severity, failed=int(failed or 0), total=int(total or 0), detail=""))
        variables = con.execute("SELECT * FROM meta_variable").df()
        results = pd.DataFrame(rows)
        results["fail_pct"] = (100 * results.failed / results.total.where(results.total > 0)).round(2)
        results["passed"] = results.failed == 0
        results["checked_at"] = datetime.now(timezone.utc).isoformat()
        write_table(con, "dq_results", results)
        drift = schema_drift(variables)
        write_table(con, "dq_schema_drift", drift)
        quarantine = con.execute("SELECT survey_cycle, reject_reason, count(*) AS rows FROM stg_quarantine "
                                 "GROUP BY ALL ORDER BY 1, 2").df()
        kinds = con.execute("SELECT survey_cycle, kind, count(*) AS columns, sum(all_null::INT) AS all_null "
                            "FROM meta_variable GROUP BY ALL ORDER BY 1, 3 DESC").df()
        counts = con.execute("SELECT survey_cycle, submissions_raw, submissions_deduplicated, submissions_superseded, "
                             "submissions_rejected, round(duplicate_household_rate, 4) AS duplicate_household_rate "
                             "FROM rpt_field_operations_cycle").df()
    write_report(results, drift, quarantine, kinds, counts)
    for r in results.itertuples():
        log_event("dq_check", check=r.check, severity=r.severity, failed=r.failed, total=r.total)
    blocking = results[(results.severity == "error") & ~results.passed]
    if len(blocking):
        raise RuntimeError(f"Blocking data-quality failures:\n{blocking[['check', 'failed', 'total']]}")
    return results


def write_report(results, drift, quarantine, kinds, counts) -> None:
    (config.PROJECT_DIR / "docs").mkdir(exist_ok=True)
    icon = {True: "PASS", False: "FAIL"}
    lines = ["# Data quality report", "",
             f"Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m pipeline.run`.", "",
             "## Row counts per cycle", "", counts.to_markdown(index=False), "",
             "## Checks", "", "| Check | Severity | Result | Failed / total | Detail |", "|---|---|---|---|---|"]
    for r in results.itertuples():
        result = "INFO" if r.severity == "info" else icon[bool(r.passed)]
        lines.append(f"| {r.check} | {r.severity} | {result} | {r.failed} / {r.total} | {r.detail if isinstance(r.detail, str) else ''} |")
    lines += ["", "## Quarantined rows", "", quarantine.to_markdown(index=False), "",
              "## Schema drift between cycles", "", drift.to_markdown(index=False), "",
              "## Exported columns by kind", "", kinds.to_markdown(index=False), ""]
    (config.PROJECT_DIR / "docs" / "DATA_QUALITY_REPORT.md").write_text("\n".join(lines))
