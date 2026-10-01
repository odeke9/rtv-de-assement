# Submission

| |                                         |
|---|-----------------------------------------|
| Hours spent | about 5 hours                           |
| Commit evaluated | c58008835ccdd24638093db4de07fafc098a21bd                                        |
| Run it | `make pipeline` then `make dashboard` (or `docker compose up --build`); see [README](README.md) |

## What's delivered

- **Pipeline:** raw → Bronze → catalog → Silver → Gold → quality → tests from one command
  (`python -m pipeline.run`), 17 s on a laptop.
- **Bronze:** write-once Parquet per cycle and source version, every source column, with `_ingested_at`,
  `_source_file`, `_survey_cycle`, `_source_sha256`, `_source_row` and `_row_hash`.
- **Gold (DuckDB):** `fct_survey_submissions`, `dim_geography`, `dim_time`, `dim_survey_cycle`,
  `rpt_field_operations`, `rpt_program_summary`, plus supporting `dim_household` and `rpt_*` tables.
- **Dashboard (Streamlit):** Field operations, Program summary, Longitudinal and Data quality views.
- **Quality:** 36 checks with a generated report (`docs/DATA_QUALITY_REPORT.md`) and 20 automated tests.
- **Docs:** [ARCHITECTURE.md](docs/ARCHITECTURE.md) (design, ELT and warehouse choice, grain, deduplication,
  cross-cycle alignment, performance, Databricks mapping), [METRICS.md](docs/METRICS.md) (formulas and
  denominators).

## Assumptions

1. **Household identifier** is `hhid_2`, upper-cased with whitespace removed. It is the preloaded
   tracking ID and is confirmed by `hhid_2_again` in every row.
2. **Deduplication** keeps the latest `SubmissionDate` per household and cycle; ties go to the
   completed and consented submission, then the lowest `KEY`.
3. **Completion** = interview status 1 ("found the respondent"); **consent** = `consent_1` = 1 ("agree
   to take part"). `consent_2` is consent to future follow-up and is not used.
4. **Completion and consent are 100%** in the exports, which therefore appear to contain completed
   interviews only. Rates are built on the full attempted denominator so they work when failed attempts
   are exported.
5. **Region** isn't in the forms. All four districts are in Uganda's Western Region (ISO 3166-2 `UG-W`);
   Kigezi sub-region except Mitooma (Ankole). Kept in `config/district_regions.csv`.
6. **Geography** uses the preloaded district/village labels, because district codes are renumbered
   between cycles.
7. **Year 1 choice codes** are decoded with the Year 2 form's lists, which is proven for district.
8. **Interview duration** is SurveyCTO's `duration` field, not end − start time.
9. **Poverty thresholds** (`TARGET_USD_DAY` = 2, `ULTRA_POOR_USD_DAY` = 1, household income + production
   per day) are placeholders pending RTV's definitions; they only affect the Longitudinal poverty view.
10. Two blank rows at the end of the Year 1 export are not submissions (no `KEY`) and are quarantined.

## Production next steps

1. Move to Databricks: Bronze as append-only Delta tables loaded by Auto Loader into Unity Catalog, the
   SQL models as Databricks SQL or dbt, the orchestrator as a Workflow; mapping in ARCHITECTURE.md §12.
2. Pull exports from the SurveyCTO API on a schedule instead of manual CSV drops; keep the hash-based
   versioning so reruns stay idempotent.
3. Export failed attempts (status ≠ 1, no consent) so completion and consent rates become informative.
4. Confirm the poverty thresholds and the Year 1 water-source code list with the programme team.
5. Move `variable_map.csv` and `label_conform.csv` reviews into pull requests with an owner per survey.
6. Mask or drop personal data (names, phone numbers, attachment URLs) in Silver, and restrict Bronze
   access; Unity Catalog column masks would do this in production.
7. Alert on failed runs and on quality-check regressions (for example a duplicate household rate above a
   threshold) instead of only reporting them.
