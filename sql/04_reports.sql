-- Reports used by the dashboard. Formulas and denominators: docs/METRICS.md

-- Field operations. Grain: cycle x submission date x district x interview status, over EVERY Bronze
-- row (kept + quarantined). Columns are additive counts/sums so any roll-up stays correct.
CREATE OR REPLACE TABLE rpt_field_operations AS
SELECT a.survey_cycle,
       a.cycle_order,
       CAST(strftime(a.submitted_at, '%Y%m%d') AS INTEGER)                   AS date_key,
       a.submitted_at::DATE                                                  AS submission_date,
       coalesce(title_case(a.district), 'Missing')                           AS district,
       CASE a.interview_status WHEN 1 THEN 'Found' WHEN 2 THEN 'Moved away' WHEN 3 THEN 'Not found'
            WHEN 4 THEN 'Unavailable' WHEN 5 THEN 'Disability' ELSE 'Missing' END AS interview_status_label,
       count(*)                                                              AS submissions_raw,
       count(*) FILTER (WHERE a.is_kept)                                     AS submissions_deduplicated,
       count(*) FILTER (WHERE a.reject_reason = 'superseded_duplicate')      AS submissions_superseded,
       count(*) FILTER (WHERE a.reject_reason IN ('missing_household_id', 'duplicate_submission_key'))
                                                                             AS submissions_rejected,
       count(*) FILTER (WHERE a.district IS NULL OR a.subcounty IS NULL OR a.parish IS NULL OR a.village IS NULL)
                                                                             AS submissions_missing_location,
       sum(a.interview_duration_sec) / 60.0                                  AS interview_minutes_sum,
       count(a.interview_duration_sec)                                       AS interview_minutes_n
FROM stg_all_submissions a
GROUP BY ALL;

-- Field operations per cycle: the headline rates
CREATE OR REPLACE VIEW rpt_field_operations_cycle AS
WITH ops AS (
  SELECT survey_cycle, cycle_order,
         sum(submissions_raw)              AS submissions_raw,
         sum(submissions_deduplicated)     AS submissions_deduplicated,
         sum(submissions_superseded)       AS submissions_superseded,
         sum(submissions_rejected)         AS submissions_rejected,
         sum(submissions_missing_location) AS submissions_missing_location,
         sum(interview_minutes_sum) / nullif(sum(interview_minutes_n), 0) AS avg_interview_minutes
  FROM rpt_field_operations GROUP BY ALL
), dup AS (
  SELECT survey_cycle,
         count(*)                                         AS households,
         count(*) FILTER (WHERE household_submissions > 1) AS households_with_duplicates,
         median(interview_duration_sec) / 60.0            AS median_interview_minutes
  FROM stg_household_cycle GROUP BY ALL
), gps AS (
  -- GPS was only collected at baseline; for other cycles the rate is undefined (NULL), not 100%
  SELECT a.survey_cycle,
         CASE WHEN bool_or(v.available) THEN avg((a.gps_lat IS NULL)::INT) END AS missing_gps_rate
  FROM stg_all_submissions a
  JOIN meta_silver_variable v ON v.survey_cycle = a.survey_cycle AND v.canonical_name = 'gps_lat'
  GROUP BY ALL
)
SELECT o.survey_cycle, o.cycle_order,
       o.submissions_raw, o.submissions_deduplicated, o.submissions_superseded, o.submissions_rejected,
       1 - o.submissions_deduplicated / o.submissions_raw            AS dedup_reduction_rate,
       d.households_with_duplicates,
       d.households_with_duplicates / d.households                   AS duplicate_household_rate,
       o.submissions_missing_location / o.submissions_raw            AS missing_location_rate,
       g.missing_gps_rate,
       o.avg_interview_minutes,
       d.median_interview_minutes
FROM ops o JOIN dup d USING (survey_cycle) JOIN gps g USING (survey_cycle)
ORDER BY o.cycle_order;

-- Program summary. Grain: cycle x district x month (deduplicated households).
CREATE OR REPLACE TABLE rpt_program_summary AS
SELECT f.survey_cycle, f.cycle_order, g.region_name, g.district, t.year_month,
       count(*)                                          AS households_attempted,
       count(*) FILTER (WHERE f.is_completed)            AS households_completed,
       count(*) FILTER (WHERE f.is_consented)            AS households_consented,
       count(*) FILTER (WHERE f.is_completed) / count(*) AS completion_rate,
       count(*) FILTER (WHERE f.is_consented)
         / nullif(count(*) FILTER (WHERE f.is_completed), 0) AS consent_rate,
       median(f.hhip_usd_day) FILTER (WHERE f.is_consented)  AS median_hhip_usd_day,
       avg(f.meets_target::INT) FILTER (WHERE f.is_consented) AS share_meeting_target
FROM fct_survey_submissions f
JOIN dim_geography g USING (geo_key)
JOIN dim_time t USING (date_key)
GROUP BY ALL;

-- Program summary per cycle, with the change from baseline
CREATE OR REPLACE VIEW rpt_program_cycle AS
WITH c AS (
  SELECT survey_cycle, cycle_order,
         sum(households_attempted) AS households_attempted,
         sum(households_completed) AS households_completed,
         sum(households_consented) AS households_consented
  FROM rpt_program_summary GROUP BY ALL
)
SELECT *,
       households_completed / households_attempted                              AS completion_rate,
       households_consented / nullif(households_completed, 0)                   AS consent_rate,
       completion_rate - first_value(completion_rate) OVER (ORDER BY cycle_order) AS completion_rate_change_vs_baseline,
       consent_rate    - first_value(consent_rate)    OVER (ORDER BY cycle_order) AS consent_rate_change_vs_baseline
FROM c
ORDER BY cycle_order;

-- Demographics of completed AND consented households. Grain: cycle x district x dimension x category.
CREATE OR REPLACE TABLE rpt_program_demographics AS
WITH c AS (
  SELECT f.*, g.district FROM fct_survey_submissions f JOIN dim_geography g USING (geo_key)
  WHERE f.is_completed AND f.is_consented
)
SELECT survey_cycle, cycle_order, district, 'Head of household age' AS dimension, head_age_band AS category, count(*) AS households FROM c GROUP BY ALL
UNION ALL SELECT survey_cycle, cycle_order, district, 'Head of household sex', head_sex_label,   count(*) FROM c GROUP BY ALL
UNION ALL SELECT survey_cycle, cycle_order, district, 'Household size',        hh_size_band,     count(*) FROM c GROUP BY ALL
UNION ALL SELECT survey_cycle, cycle_order, district, 'Respondent',            respondent_label, count(*) FROM c GROUP BY ALL;

-- Longitudinal: households observed in 1, 2 or 3 cycles, and in which combination
CREATE OR REPLACE TABLE rpt_cohort_coverage AS
SELECT n_cycles, cycle_pattern, count(*) AS households
FROM dim_household
GROUP BY ALL
ORDER BY n_cycles DESC, households DESC;

-- Longitudinal: poverty trend for the balanced panel (same households in every cycle)
CREATE OR REPLACE TABLE rpt_panel_poverty AS
SELECT f.survey_cycle, f.cycle_order, g.district,
       count(*)                     AS households,
       median(f.hhip_usd_day)       AS median_hhip_usd_day,
       avg(f.meets_target::INT)     AS share_meeting_target,
       avg(f.is_ultra_poor::INT)    AS share_ultra_poor
FROM fct_survey_submissions f
JOIN dim_household h USING (household_id)
JOIN dim_geography g USING (geo_key)
WHERE h.in_balanced_panel AND f.is_consented
GROUP BY ALL;
