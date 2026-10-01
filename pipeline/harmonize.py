from __future__ import annotations

import pandas as pd

from config import config
from pipeline.ingest import bronze_columns, read_bronze
from utils.helpers import log_event


def load_variable_map() -> pd.DataFrame:
    vm = pd.read_csv(config.VARIABLE_MAP, dtype=str, keep_default_na=False)
    if vm["canonical_name"].duplicated().any():
        raise ValueError("variable_map.csv has duplicate canonical names")
    return vm


def parse_timestamps(s: pd.Series, formats: tuple) -> pd.Series:
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    for fmt in formats:
        todo = out.isna() & s.notna()
        if not todo.any():
            break
        out.loc[todo] = pd.to_datetime(s[todo], format=fmt, errors="coerce")
    return out


def _cast(series: pd.Series, dtype: str, ts_formats: tuple) -> pd.Series:
    s = series.astype("string").str.strip()
    if dtype == "timestamp":
        return parse_timestamps(s, ts_formats)
    if dtype == "float":
        return pd.to_numeric(s, errors="coerce").astype("Float64")
    if dtype == "int":
        num = pd.to_numeric(s, errors="coerce")
        return num.where(num.isna() | (num == num.round())).astype("Int64")
    if s.name == "form_version":
        return s.str.replace(r"\.0$", "", regex=True)
    return s


def harmonize_round(code: str, vm: pd.DataFrame) -> pd.DataFrame:
    rnd = config.CYCLE_BY_CODE[code]
    available = set(bronze_columns(code))
    sources = {row.canonical_name: getattr(row, code) for row in vm.itertuples()}
    wanted = sorted({c for c in sources.values() if c and c in available})
    missing = {k: v for k, v in sources.items() if v and v not in available}
    if missing:
        raise KeyError(f"{code}: mapped source columns not found: {missing}")

    lineage = ["_source_row", "_row_hash", "_ingested_at"]
    bronze = read_bronze(code, columns=lineage + wanted)
    out = pd.DataFrame({"survey_cycle": code, "cycle_order": rnd.order, **{c: bronze[c] for c in lineage}})
    for row in vm.itertuples():
        src = sources[row.canonical_name]
        col = bronze[src] if src else pd.Series(pd.NA, index=bronze.index, dtype="string")
        col = col.rename(row.canonical_name)
        out[row.canonical_name] = _cast(col, row.dtype, rnd.ts_format)
    out["interview_minutes"] = (out["ended_at"] - out["started_at"]).dt.total_seconds() / 60
    out["household_id_raw"] = out["household_id"]
    for c in ("household_id", "household_id_confirm"):
        out[c] = normalize_household_id(out[c])
    return out


def normalize_household_id(s: pd.Series) -> pd.Series:
    return s.astype("string").str.upper().str.replace(r"\s+", "", regex=True)


def split_and_dedupe(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Keep the latest submission per household; everything else goes to quarantine with a reason.

    Tie-breakers for submissions with the same timestamp: completed+consented first, then lowest KEY.
    Failed attempts (respondent not found, no consent) are kept and flagged, so completion and
    consent rates have a real denominator.
    """
    reasons = pd.Series(pd.NA, index=df.index, dtype="string")
    reasons = reasons.mask(df["submission_key"].isna(), "empty_row")  # blank lines at the end of an export
    reasons = reasons.mask(reasons.isna() & df["household_id"].isna(), "missing_household_id")
    reasons = reasons.mask(reasons.isna() & df["submission_key"].duplicated(keep="first"), "duplicate_submission_key")
    quarantine = df[reasons.notna()].assign(reject_reason=reasons[reasons.notna()])

    ok = df[reasons.isna()].copy()
    ok["is_completed"] = (ok["interview_status"] == 1).fillna(False).astype(bool)
    ok["is_consented"] = (ok["is_completed"] & (ok["consent"] == 1).fillna(False)).astype(bool)
    ok["household_submissions"] = ok.groupby("household_id")["submission_key"].transform("size")
    ok = ok.sort_values(["household_id", "submitted_at", "is_consented", "is_completed", "submission_key"],
                        ascending=[True, False, False, False, True])
    superseded = ok.duplicated(["household_id"], keep="first")
    quarantine = pd.concat([quarantine, ok[superseded].assign(reject_reason="superseded_duplicate")])
    return ok[~superseded].copy(), quarantine


def build_silver() -> dict[str, int]:
    config.SILVER_DIR.mkdir(parents=True, exist_ok=True)
    vm = load_variable_map()
    kept, rejected, counts = [], [], {}
    for cycle in config.CYCLES:
        df = harmonize_round(cycle.code, vm)
        ok, q = split_and_dedupe(df)
        kept.append(ok)
        rejected.append(q)
        counts[cycle.code] = {"bronze": len(df), "silver": len(ok), "quarantined": len(q)}
        log_event("silver_cycle", survey_cycle=cycle.code, bronze_rows=len(df), silver_rows=len(ok),
                  quarantined=len(q), reasons=q["reject_reason"].value_counts().to_dict())
    silver = pd.concat(kept, ignore_index=True)
    quarantine = pd.concat(rejected, ignore_index=True)

    assert not silver.duplicated(["household_id", "survey_cycle"]).any(), "grain violated: household x cycle"
    assert silver["submitted_at"].notna().all(), "unparseable SubmissionDate (check config ts_format)"

    silver.to_parquet(config.SILVER_DIR / "household_cycle.parquet", index=False)
    quarantine.to_parquet(config.SILVER_DIR / "quarantine.parquet", index=False)
    return counts
