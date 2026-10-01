"""Fast unit tests: no data files needed."""
import pandas as pd

from config.config import CYCLE_BY_CODE
from pipeline.catalog import classify
from pipeline.harmonize import normalize_household_id, parse_timestamps, split_and_dedupe
from utils.helpers import normalize_column


def test_each_cycle_timestamp_format_parses():
    samples = {"baseline": "6/30/2020, 6:49:56 PM",
               "year1": "Aug 18, 2022 10:47:35 PM",
               "year2": "2023-08-06 11:06:47"}
    for code, value in samples.items():
        out = parse_timestamps(pd.Series([value], dtype="string"), CYCLE_BY_CODE[code].ts_format)
        assert out.notna().all(), code


def test_mixed_formats_within_one_file():
    s = pd.Series(["2023-08-06 11:06:47", "2023-08-05 22:15:40.000"], dtype="string")
    out = parse_timestamps(s, CYCLE_BY_CODE["year2"].ts_format)
    assert out.notna().all()
    assert out.iloc[1] == pd.Timestamp("2023-08-05 22:15:40")


def test_ambiguous_dates_are_not_guessed():
    # an ISO date must NOT be accepted by the baseline (US m/d/Y) format
    out = parse_timestamps(pd.Series(["2020-06-30 10:00:00"], dtype="string"), CYCLE_BY_CODE["baseline"].ts_format)
    assert out.isna().all()


def test_normalize_column_collapses_whitespace():
    assert normalize_column(" Consumption + Residues (USD_PPP)") == "Consumption + Residues (USD_PPP)"
    assert normalize_column("Seasonal  Agriculture Value (USD)") == "Seasonal Agriculture Value (USD)"


def test_household_id_normalisation():
    s = pd.Series(["Kan-byu-ale-k4048", "MIT-NYA-M U-M11019", None], dtype="string")
    assert normalize_household_id(s).tolist()[:2] == ["KAN-BYU-ALE-K4048", "MIT-NYA-MU-M11019"]


def _frame(rows):
    cols = ["household_id", "submission_key", "submitted_at", "interview_status", "consent"]
    df = pd.DataFrame(rows, columns=cols)
    df["submitted_at"] = pd.to_datetime(df["submitted_at"])
    df["interview_status"] = df["interview_status"].astype("Int64")
    df["consent"] = df["consent"].astype("Int64")
    return df


def test_dedupe_keeps_latest_and_flags_outcomes():
    df = _frame([("H1", "k1", "2023-08-01", 1, 1),
                 ("H1", "k2", "2023-08-03", 1, 1),     # latest → kept
                 ("H2", "k3", "2023-08-02", 1, 0),     # completed, no consent → kept, flagged
                 (None, "k4", "2023-08-02", 1, 1),     # no id → quarantined
                 ("H3", "k5", "2023-08-02", 3, None)]) # not found → kept, flagged
    ok, q = split_and_dedupe(df)
    assert sorted(ok.submission_key) == ["k2", "k3", "k5"]
    assert dict(zip(q.submission_key, q.reject_reason)) == {"k4": "missing_household_id", "k1": "superseded_duplicate"}
    flags = ok.set_index("submission_key")[["is_completed", "is_consented"]].to_dict("index")
    assert flags == {"k2": {"is_completed": True, "is_consented": True},
                     "k3": {"is_completed": True, "is_consented": False},
                     "k5": {"is_completed": False, "is_consented": False}}


def test_dedupe_is_deterministic_on_ties():
    df = _frame([("H1", "b", "2023-08-01", 1, 1), ("H1", "a", "2023-08-01", 1, 1)])
    ok, _ = split_and_dedupe(df)
    assert ok.submission_key.tolist() == ["a"]


def test_dedupe_tie_prefers_completed_interview():
    df = _frame([("H1", "a", "2023-08-01", 3, None), ("H1", "b", "2023-08-01", 1, 1)])
    ok, _ = split_and_dedupe(df)
    assert ok.submission_key.tolist() == ["b"]


def test_catalog_classification():
    form = {"Loan_from": {"choices": [{"code": "1"}]}, "hhmem": {"choices": []}, "hh_size": {"choices": []}}
    assert classify("Loan_from_97", form) == "select_multiple_option"
    assert classify("hhmem3", form) == "repeat_instance"
    assert classify("hh_size", form) == "question"
    assert classify("HH Income (USD)", form) == "derived_metric"
    assert classify("KEY", form) == "system"
