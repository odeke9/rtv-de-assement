"""
variable catalog.
Builds three metadata tables from the SurveyCTO printable forms + the Bronze data:
"""
from __future__ import annotations

import re

import pandas as pd
from bs4 import BeautifulSoup

from config import config
from pipeline.harmonize import load_variable_map
from pipeline.ingest import raw_path, read_bronze
from utils.helpers import log_event, normalize_column

SYSTEM_COLUMNS = {
    "SubmissionDate", "starttime", "endtime",
    "KEY", "instanceID", "formdef_version",
    "version", "duration", "_survey_cycle", "_source_file", "_source_sha256",
    "_source_row", "_row_hash", "_ingested_at",
}

DERIVED_PATTERN = re.compile(r"\((USD|Ugx|UGX)|USD_|Ugx|PPI Score|^Quartile$|/Day", re.I)
SUFFIX_PATTERN = re.compile(r"^(?P<base>.+?)_?(?P<idx>\d+)$")


def parse_form(path) -> list[dict]:
    soup = BeautifulSoup(open(path, encoding="utf-8", errors="ignore").read(), "lxml")
    fields, section = [], None
    for row in soup.select("tr.entryRow"):
        tds = row.find_all("td", recursive=False)
        if len(tds) == 1 and tds[0].get("colspan"):          # group header row
            section = tds[0].get_text(" ", strip=True)
            continue
        cell = row.select_one("td.fieldCell")
        if not cell:
            continue
        name = normalize_column(cell.get_text(" ", strip=True).replace("(required)", ""))
        q = row.select_one("td.questionCell")
        choices = []
        for tr in tds[-1].select("table tr"):
            c = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(c) >= 3 and c[1] != "":
                choices.append({"code": c[1], "label": c[2]})
        fields.append({"name": name, "section": section,
                       "label": q.get_text(" ", strip=True) if q else "", "choices": choices})
    return fields


def classify(column: str, form_fields: dict[str, dict]) -> str:
    if column in SYSTEM_COLUMNS:
        return "system"
    if column in form_fields:
        return "select_question" if form_fields[column]["choices"] else "question"
    m = SUFFIX_PATTERN.match(column)
    if m and m.group("base") in form_fields:
        return "select_multiple_option" if form_fields[m.group("base")]["choices"] else "repeat_instance"
    if DERIVED_PATTERN.search(column):
        return "derived_metric"
    return "unclassified"


def build_catalog() -> dict[str, pd.DataFrame]:
    fields_rows, choice_rows, var_rows = [], [], []
    present: dict[str, set[str]] = {}

    for rnd in config.CYCLES:
        form = parse_form(raw_path(rnd.code, "form"))
        by_name = {f["name"]: f for f in form}
        for f in form:
            fields_rows.append({"survey_cycle": rnd.code, "field": f["name"], "section": f["section"],
                                "label": f["label"], "n_choices": len(f["choices"])})
            for c in f["choices"]:
                choice_rows.append({"survey_cycle": rnd.code, "field": f["name"], **c})

        df = read_bronze(rnd.code)
        present[rnd.code] = set(df.columns)
        null_rate = df.isna().mean()
        n_distinct = df.nunique(dropna=True)
        for col in df.columns:
            if col.startswith("_"):
                continue
            kind = classify(col, by_name)
            base = SUFFIX_PATTERN.match(col).group("base") if kind in ("select_multiple_option", "repeat_instance") else col
            f = by_name.get(base, {})
            var_rows.append({"survey_cycle": rnd.code, "variable": col, "kind": kind,
                             "form_field": base if f else None, "section": f.get("section"),
                             "label": f.get("label"), "null_rate": round(float(null_rate[col]), 4),
                             "n_distinct": int(n_distinct[col]), "all_null": bool(null_rate[col] == 1.0)})
        log_event("catalog_cycle", survey_cycle=rnd.code, form_fields=len(form), exported_columns=df.shape[1])

    variables = pd.DataFrame(var_rows)
    for rid, cols in present.items():
        variables[f"in_{rid}"] = variables["variable"].isin(cols)
    return {"meta_form_field": pd.DataFrame(fields_rows),
            "meta_choice_list": pd.DataFrame(choice_rows),
            "meta_variable": variables,
            "meta_silver_variable": silver_variable_catalog(variables)}


def silver_variable_catalog(variables: pd.DataFrame) -> pd.DataFrame:
    """One row per Silver/Gold variable and cycle: which source column feeds it and what it means."""
    vm = load_variable_map()
    long = vm.melt(id_vars=["canonical_name", "dtype", "notes"], value_vars=[c.code for c in config.CYCLES],
                   var_name="survey_cycle", value_name="source_column")
    long["source_column"] = long["source_column"].replace("", None)
    cols = ["survey_cycle", "variable", "kind", "section", "label", "null_rate"]
    return (long.merge(variables[cols], how="left", left_on=["survey_cycle", "source_column"],
                       right_on=["survey_cycle", "variable"])
                .drop(columns="variable")
                .assign(available=lambda d: d.source_column.notna())
                .sort_values(["canonical_name", "survey_cycle"]))


def schema_drift(variables: pd.DataFrame) -> pd.DataFrame:
    """Columns added/removed between consecutive cycles (the 'evolving survey structure')."""
    rows = []
    ids = [r.code for r in config.CYCLES]
    sets = {rid: set(variables.loc[variables.survey_cycle == rid, "variable"]) for rid in ids}
    for prev, cur in zip(ids, ids[1:]):
        rows.append({"from_cycle": prev, "to_cycle": cur,
                     "added": len(sets[cur] - sets[prev]), "removed": len(sets[prev] - sets[cur]),
                     "kept": len(sets[cur] & sets[prev])})
    return pd.DataFrame(rows)
