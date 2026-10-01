"""Draft config/label_conform.csv from the SurveyCTO forms.

Two kinds of rows:
  automatic: labels in the same field that differ only by case/punctuation/spacing
             -> conformed to the latest cycle's spelling
  MANUAL:    rewordings a person has confirmed mean the same option

Then prints, for fields the SQL decodes with choice_label(), any code whose label still differs
across cycles so a person can decide whether it belongs in MANUAL.

    python -m utils.build_label_conform            # writes only if the file does not exist
    python -m utils.build_label_conform --force
"""
from __future__ import annotations

import re
import sys

import pandas as pd

from config import config
from pipeline.catalog import parse_form

OUT = config.VARIABLE_MAP.parent / "label_conform.csv"

MANUAL: list[tuple[str, str, str]] = [
    ("Material_roof", "Thatch/Tins", "Thatch/Tins/Grass"),
    ("Type_of_Toilet_Facility", "VIP Toilet Flushable", "VIP flushable"),
    ("Lighting_source", "Electricity Solar/Generator/Grid", "Electricity/Solar"),
]


def _clean(label: str) -> str:
    # must match the normalisation in sql/03_facts.sql (trim + drop square brackets)
    return re.sub(r"[\[\]]", "", label).strip()


def _key(label: str) -> str:
    return re.sub(r"[^a-z0-9]", "", label.lower())


def load_choices() -> pd.DataFrame:
    rows = []
    for c in config.CYCLES:
        for f in parse_form(config.DATA_DIR / c.form):
            for ch in f["choices"]:
                rows.append({"cycle_order": c.order, "survey_cycle": c.code, "field": f["name"],
                             "code": ch["code"], "label": _clean(ch["label"])})
    return pd.DataFrame(rows)


def automatic_rows(choices: pd.DataFrame) -> pd.DataFrame:
    df = choices.assign(key=choices.label.map(_key))
    latest = (df.sort_values("cycle_order").groupby(["field", "key"]).label.last()
                .rename("conformed_label").reset_index())
    out = df[["field", "key", "label"]].drop_duplicates().merge(latest, on=["field", "key"])
    out = out[out.label != out.conformed_label]
    return out.rename(columns={"label": "raw_label"})[["field", "raw_label", "conformed_label"]]


def decoded_fields() -> set[str]:
    sql = " ".join(p.read_text() for p in config.SQL_DIR.glob("*.sql"))
    return set(re.findall(r"choice_label\([^,]+,\s*'([^']+)'", sql))


def review(choices: pd.DataFrame, conform: pd.DataFrame) -> pd.DataFrame:
    mapping = {(r.field, r.raw_label): r.conformed_label for r in conform.itertuples()}
    df = choices[choices.field.isin(decoded_fields())].copy()
    df["final"] = [mapping.get((f, l), l) for f, l in zip(df.field, df.label)]
    differs = df.groupby(["field", "code"]).final.transform("nunique") > 1
    return (df[differs].pivot_table(index=["field", "code"], columns="survey_cycle", values="final", aggfunc="first")
              .reindex(columns=[c.code for c in config.CYCLES]))


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    choices = load_choices()
    manual = pd.DataFrame(MANUAL, columns=["field", "raw_label", "conformed_label"])
    conform = (pd.concat([manual, automatic_rows(choices)])
                 .drop_duplicates(["field", "raw_label"], keep="first")   # the SQL joins on (field, raw_label)
                 .sort_values(["field", "raw_label"]))
    return conform, review(choices, conform)


if __name__ == "__main__":
    conform, todo = build()
    if len(todo):
        print("Codes whose label still differs across cycles (decide: add to MANUAL, or leave as-is):")
        print(todo.to_string())
    if OUT.exists() and "--force" not in sys.argv:
        sys.exit(f"{OUT} exists; rerun with --force to overwrite")
    conform.to_csv(OUT, index=False)
    print(f"wrote {len(conform)} rows to {OUT}")
