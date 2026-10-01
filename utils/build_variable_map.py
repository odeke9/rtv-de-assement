"""Draft config/variable_map.csv from Bronze headers.

Each canonical variable lists candidate source names; per cycle the first exact match wins,
then a match ignoring case and punctuation. The output is a draft: review it, then commit it.

    python -m utils.build_variable_map            # writes only if the file does not exist
    python -m utils.build_variable_map --force
"""
from __future__ import annotations

import re
import sys

import pandas as pd

from config import config
from pipeline.ingest import bronze_columns

SPEC: list[tuple[str, str, list[str], str]] = [
    ("submission_key", "string", ["KEY"], ""),
    ("submitted_at", "timestamp", ["SubmissionDate"], ""),
    ("started_at", "timestamp", ["starttime"], ""),
    ("ended_at", "timestamp", ["endtime"], ""),
    ("interview_duration_sec", "float", ["duration"], "SurveyCTO time the form was open; robust to overnight start/end gaps"),
    ("form_version", "string", ["formdef_version"], ""),
    ("enumerator", "string", ["enumerator"], ""),
    ("household_id", "string", ["hhid_2"], ""),
    ("household_id_confirm", "string", ["hhid_2_again"], ""),
    ("interview_status", "int", ["status"], "1 = in field and found household; 'Status' is a constant org tag"),
    ("consent", "int", ["consent_1"], "consent_2 is consent to future follow-up, not to this survey"),
    ("district_code", "int", ["district"], "code lists differ by cycle; use district label for geography"),
    ("district", "string", ["pre_district"], ""),
    ("subcounty", "string", ["pre_subcounty"], ""),
    ("parish", "string", ["pre_parish"], ""),
    ("cluster", "string", ["pre_cluster"], ""),
    ("village", "string", ["pre_village"], ""),
    ("cohort", "string", ["pre_cohort"], "year2 only"),
    ("wealth_quartile", "string", ["Quartile"], ""),
    ("respondent", "int", ["respondent"], ""),
    ("hh_size", "int", ["hh_size"], ""),
    ("head_sex", "int", ["hhh_sex"], ""),
    ("head_age", "int", ["hhh_age"], ""),
    ("head_education", "int", ["hhh_educ_level"], ""),
    ("head_literate", "int", ["hhh_read_write"], ""),
    ("ppi_score", "float", ["PPI Score"], ""),
    ("hhip_usd_day", "float", ["HH Income + Consumption + Residues/Day (USD)"], ""),
    ("hhip_usd_ppp_day", "float", ["HH Income + Consumption + Residues/Day (USD_PPP)"], ""),
    ("hhip_usd_year", "float", ["HH Income + Consumption + Residues (USD)"], ""),
    ("hh_income_usd_year", "float", ["HH Income (USD)"], ""),
    ("consumption_residues_usd_year", "float", ["Consumption + Residues (USD)", "Consumption (USD)"],
     "baseline 'Consumption (USD)' already includes residues (income + it = total)"),
    ("inc_seasonal_crops_usd", "float", ["Seasonal Crops Income (USD)"], ""),
    ("inc_perennial_crops_usd", "float", ["Perenial Crops Income (USD)"], ""),
    ("inc_livestock_usd", "float", ["Livestock Income (USD)"], ""),
    ("inc_casual_labour_usd", "float", ["Casual Labour (USD)"], ""),
    ("inc_formal_employment_usd", "float", ["Formal Employment (USD)"], ""),
    ("inc_business_usd", "float", ["Personal Business & Self Employment (USD)"], ""),
    ("inc_remittances_usd", "float", ["Remittances & Gifts (USD)"], ""),
    ("inc_rent_usd", "float", ["Rent Income (Property & Land) (USD)"], ""),
    ("inc_vsla_profits_usd", "float", ["VSLA_Profits (USD)"], "year2 only"),
    ("inc_vegetables_usd", "float", ["Vegetable Income (USD)"], "year2 only"),
    ("assets_usd", "float", ["Assets (USD)"], "not exported at baseline"),
    ("livestock_asset_usd", "float", ["Livestock Asset Value (USD)"], "baseline only has USD_Cons_rate/PPP variants"),
    ("savings_ugx", "float", ["Total Savings (Ugx)"], "the '.1' duplicate column differs; first occurrence used"),
    ("loan_amount_ugx", "float", ["Loan Amount (Ugx)"], "the '.1' duplicate column differs; first occurrence used"),
    ("owns_land", "int", ["Does_your_Household_own_any_Land"], ""),
    ("land_owned_acres", "float", ["Size_land_owned"], ""),
    ("roof_material", "int", ["Material_roof"], ""),
    ("water_source", "int", ["Main_source_of_water_for_consumption"], ""),
    ("toilet_type", "int", ["Type_of_Toilet_Facility"], ""),
    ("cooking_fuel", "int", ["Fuel_source_cooking"], ""),
    ("lighting_source", "int", ["Lighting_source"], ""),
    ("all_members_have_shoes", "int", ["Every_Member_at_least_ONE_Pair_of_Shoes"], ""),
    ("water_litres_day", "float", ["Average_Water_Consumed_Per_Day"], "form unit is jerry cans per day, not litres"),
    ("satisfied_quality_of_life", "int", ["satisfied_quality_of_life"], ""),
    ("gps_lat", "float", ["GPS-Latitude"], "baseline only"),
    ("gps_lon", "float", ["GPS-Longitude"], "baseline only"),
]


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def resolve(candidates: list[str], columns: list[str]) -> tuple[str, str]:
    present = set(columns)
    for c in candidates:
        if c in present:
            return c, "exact"
    by_key = {}
    for col in columns:
        by_key.setdefault(_key(col), col)  # first occurrence, so 'x' wins over pandas' 'x.1'
    for c in candidates:
        if _key(c) in by_key:
            return by_key[_key(c)], "fuzzy"
    return "", "missing"


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = {c.code: bronze_columns(c.code) for c in config.CYCLES}
    rows, report = [], []
    for name, dtype, candidates, note in SPEC:
        row = {"canonical_name": name, "dtype": dtype}
        for code, cols in columns.items():
            row[code], how = resolve(candidates, cols)
            report.append({"canonical_name": name, "survey_cycle": code, "source": row[code], "match": how})
        row["notes"] = note
        rows.append(row)
    return pd.DataFrame(rows), pd.DataFrame(report)


if __name__ == "__main__":
    vm, report = build()
    review = report[report.match != "exact"]
    print(review.to_string(index=False) if len(review) else "all mappings are exact matches")
    if config.VARIABLE_MAP.exists() and "--force" not in sys.argv:
        sys.exit(f"{config.VARIABLE_MAP} exists; rerun with --force to overwrite")
    vm.to_csv(config.VARIABLE_MAP, index=False)
    print(f"wrote {len(vm)} variables to {config.VARIABLE_MAP}")
