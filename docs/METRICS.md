# Metric definitions

Every metric, its formula and denominator, where it is computed, and whether it is comparable across
cycles. "Submission" = one row in an export that has a SurveyCTO `KEY`. "Household" = one deduplicated
household × cycle row in `fct_survey_submissions`.

## Operational (Field operations view)

| Metric | Formula | Denominator | Source |
|---|---|---|---|
| Raw submissions | count of submissions | n/a | `rpt_field_operations.submissions_raw` |
| Deduplicated submissions | submissions kept after deduplication (one per household × cycle) | n/a | `submissions_deduplicated` |
| Superseded submissions | earlier submissions for a household that already has a later one in the cycle | n/a | `submissions_superseded` |
| Deduplication reduction | 1 − deduplicated / raw | raw submissions | `rpt_field_operations_cycle.dedup_reduction_rate` |
| Duplicate household rate | households with > 1 submission / households | deduplicated households in the cycle | `rpt_field_operations_cycle.duplicate_household_rate` |
| Missing location rate | submissions with district, subcounty, parish **or** village missing / submissions | raw submissions | `missing_location_rate` |
| Missing GPS rate | submissions without a GPS latitude / submissions | raw submissions, **baseline only** | `missing_gps_rate` |
| Submissions by status | count of submissions per interview status (Found, Moved away, Not found, Unavailable, Disability) | raw submissions | `rpt_field_operations.interview_status_label` |
| Average interview duration | Σ SurveyCTO `duration` / count with a duration, in minutes | raw submissions with a duration | `interview_minutes_sum / interview_minutes_n` |
| Median interview duration | median `duration` in minutes | deduplicated households | `median_interview_minutes` |
| Submissions over time | raw submissions per `SubmissionDate` day | n/a | `rpt_field_operations.submission_date` |

## Program (Program summary view)

| Metric | Formula | Denominator | Source |
|---|---|---|---|
| Households attempted | deduplicated households | n/a | `rpt_program_summary.households_attempted` |
| Completion rate | households with interview status = 1 (found) / households attempted | households attempted | `completion_rate` |
| Consent rate | households that consented (`consent_1` = 1) / completed households | completed households | `consent_rate` |
| Completions by district and month | completed households grouped by district and `SubmissionDate` month | n/a | `rpt_program_summary` (cycle × district × month) |
| Demographics | share of completed **and** consented households per category | completed and consented households in the cycle (and districts selected) | `rpt_program_demographics` |

Demographic categories:

| Dimension | Categories |
|---|---|
| Head of household age | 15–24, 25–34, 35–44, 45–54, 55–64, 65+; `Unknown` = missing or outside 15–100 |
| Head of household sex | Male, Female (form choice list) |
| Household size | 1–3, 4–6, 7–9, 10+ |
| Respondent | Head of household, Spouse (baseline also offered Other; nobody chose it) |

## Longitudinal

| Metric | Formula | Denominator | Source |
|---|---|---|---|
| Households observed in 1, 2 or 3 cycles | count of households by number (and combination) of cycles they appear in after deduplication | all households ever observed (5,848) | `rpt_cohort_coverage` |
| Change in completion / consent rate vs baseline | rate in cycle − rate at baseline, in percentage points | as above per cycle | `rpt_program_cycle.*_change_vs_baseline` |
| Balanced-panel median income + production per day | median `hhip_usd_day` for households present in all three cycles | 504 panel households (consented) | `rpt_panel_poverty` |
| Share meeting target / ultra-poor | households with `hhip_usd_day` ≥ target (< ultra-poor line) / panel households | panel households | `rpt_panel_poverty` |

## Where a metric isn't consistent across cycles

- **Completion and consent rates are 100% in every cycle.** Every exported submission has status 1
  (household found) and `consent_1` = 1: the exports contain completed, consented interviews only.
  The formulas use the right denominators, so they will move once exports include failed attempts,
  but with this data the change from baseline to Year 2 is 0 points by construction.
- **Missing GPS rate** is defined for baseline only. Year 1 and Year 2 didn't collect GPS, so the rate
  is NULL for them, not 100%.
- **Cross-cycle totals compare different samples** (1,414 / 3,796 / 3,852 households; Rubanda only
  from Year 1). Use the balanced panel for like-for-like change.
- **Income per day** uses the export's derived `HH Income + Consumption + Residues/Day (USD)`, available
  in all cycles; vegetable and VSLA income are only in Year 2, assets and livestock value aren't
  exported at baseline.
- **Interview duration** uses SurveyCTO's `duration` (time the form was open). End − start time is kept
  as `wall_clock_minutes` but not used: some interviews were opened one day and submitted the next.
