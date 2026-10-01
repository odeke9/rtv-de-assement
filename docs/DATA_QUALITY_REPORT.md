# Data quality report

Generated 2026-10-01 10:16 UTC by `python -m pipeline.run`.

## Row counts per cycle

| survey_cycle   |   submissions_raw |   submissions_deduplicated |   submissions_superseded |   submissions_rejected |   duplicate_household_rate |
|:---------------|------------------:|---------------------------:|-------------------------:|-----------------------:|---------------------------:|
| baseline       |              1419 |                       1414 |                        5 |                      0 |                     0.0035 |
| year1          |              3918 |                       3796 |                      122 |                      0 |                     0.0282 |
| year2          |              3897 |                       3852 |                       45 |                      0 |                     0.0114 |

## Checks

| Check | Severity | Result | Failed / total | Detail |
|---|---|---|---|---|
| baseline: identical rows in export (same row hash) | info | INFO | 0 / 1419 |  |
| baseline: hhid_2 equals hhid_2_again | warn | PASS | 0 / 1419 |  |
| baseline: district code maps to one label | warn | PASS | 0 / 3 | 1=Rukungiri; 2=Kanungu; 4=Mitooma |
| baseline: SubmissionDate parses with known formats | error | PASS | 0 / 1419 | %m/%d/%Y, %I:%M:%S %p |
| baseline: duplicate headers in export (pandas '.1' suffix) | info | INFO | 21 / 6722 | Livestock Asset Value.1, Total Savings (Ugx).1, Loan Amount (Ugx).1, Formal Employment (Ugx).1, Personal Business & Self Employment (Ugx).1, Casual Labour (Ugx).1 |
| year1: identical rows in export (same row hash) | info | INFO | 0 / 3920 |  |
| year1: hhid_2 equals hhid_2_again | warn | PASS | 0 / 3920 |  |
| year1: district code maps to one label | warn | PASS | 0 / 4 | 2.0=Kanungu; 3.0=Rukungiri; 5.0=Mitooma; 7.0=Rubanda |
| year1: SubmissionDate parses with known formats | error | PASS | 0 / 3920 | %b %d, %Y %I:%M:%S %p |
| year1: duplicate headers in export (pandas '.1' suffix) | info | INFO | 51 / 4523 | Total Savings (Ugx).1, Loan Amount (Ugx).1, Formal Employment (Ugx).1, Personal Business & Self Employment (Ugx).1, Casual Labour (Ugx).1, Remittances & Gifts (Ugx).1 |
| year2: identical rows in export (same row hash) | info | INFO | 0 / 3897 |  |
| year2: hhid_2 equals hhid_2_again | warn | PASS | 0 / 3897 |  |
| year2: district code maps to one label | warn | PASS | 0 / 4 | 2=Kanungu; 3=Rukungiri; 5=Mitooma; 7=Rubanda |
| year2: SubmissionDate parses with known formats | error | PASS | 0 / 3897 | %Y-%m-%d %H:%M:%S / %Y-%m-%d %H:%M:%S.%f |
| year2: duplicate headers in export (pandas '.1' suffix) | info | INFO | 37 / 5611 | Season1 Vegetable Income (Ugx).1, Season2 Vegetable Income (Ugx).1, Vegetable Income (Ugx).1, Season1 Vegetable Value (Ugx).1, Season2 Vegetable Value (Ugx).1, Seasonal Vegetable Value (Ugx).1 |
| grain_unique_household_cycle | error | PASS | 0 / 9062 |  |
| household_id_format | warn | FAIL | 10 / 9062 |  |
| household_id_needed_normalisation | info | INFO | 243 / 9062 |  |
| hh_size_in_range | warn | PASS | 0 / 9062 |  |
| hhip_not_null | error | PASS | 0 / 9062 |  |
| hhip_plausible_range | warn | PASS | 0 / 9062 |  |
| hhip_daily_reconciles_with_annual | warn | PASS | 0 / 9062 |  |
| income_components_le_total_income | warn | PASS | 0 / 9062 |  |
| village_maps_to_one_parish_within_cycle | warn | FAIL | 12 / 429 |  |
| villages_with_parish_spelling_change_across_cycles | info | INFO | 83 / 153 |  |
| fact_rows_without_geography | error | PASS | 0 / 9062 |  |
| interview_duration_plausible_10min_6h | warn | FAIL | 6 / 9062 |  |
| wall_clock_start_to_end_over_6h | info | INFO | 1861 / 9062 |  |
| head_age_plausible_15_100 | warn | FAIL | 10 / 9062 |  |
| completed_interview_has_consent_answer | warn | PASS | 0 / 9062 |  |
| fact_dates_covered_by_dim_time | error | PASS | 0 / 9062 |  |
| geography_has_region | error | PASS | 0 / 153 |  |
| submitted_after_started | warn | PASS | 0 / 9062 |  |
| district_code_decodes_to_preloaded_label | warn | FAIL | 3 / 11 |  |
| households_changed_district | info | INFO | 0 / 5848 |  |
| baseline_households_missing_a_follow_up_cycle | info | INFO | 910 / 1414 |  |

## Quarantined rows

| survey_cycle   | reject_reason        |   rows |
|:---------------|:---------------------|-------:|
| baseline       | superseded_duplicate |      5 |
| year1          | empty_row            |      2 |
| year1          | superseded_duplicate |    122 |
| year2          | superseded_duplicate |     45 |

## Schema drift between cycles

| from_cycle   | to_cycle   |   added |   removed |   kept |
|:-------------|:-----------|--------:|----------:|-------:|
| baseline     | year1      |    3983 |      6182 |    534 |
| year1        | year2      |    3860 |      2772 |   1745 |

## Exported columns by kind

| survey_cycle   | kind                   |   columns |   all_null |
|:---------------|:-----------------------|----------:|-----------:|
| baseline       | select_multiple_option |      3015 |       2306 |
| baseline       | unclassified           |      2177 |        833 |
| baseline       | repeat_instance        |       958 |        322 |
| baseline       | question               |       274 |         49 |
| baseline       | select_question        |       185 |         11 |
| baseline       | derived_metric         |        99 |          0 |
| baseline       | system                 |         8 |          0 |
| year1          | question               |      1367 |        322 |
| year1          | unclassified           |      1319 |        200 |
| year1          | select_question        |      1194 |        293 |
| year1          | select_multiple_option |       496 |        137 |
| year1          | derived_metric         |       124 |          0 |
| year1          | repeat_instance        |         9 |          4 |
| year1          | system                 |         8 |          0 |
| year2          | unclassified           |      4007 |        688 |
| year2          | question               |       679 |        110 |
| year2          | select_question        |       580 |        139 |
| year2          | select_multiple_option |       172 |          6 |
| year2          | derived_metric         |       147 |          0 |
| year2          | repeat_instance        |        12 |          7 |
| year2          | system                 |         8 |          0 |
