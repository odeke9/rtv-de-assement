CREATE OR REPLACE MACRO title_case(s) AS
  array_to_string(list_transform(string_split(lower(trim(s)), ' '), w -> upper(w[1]) || w[2:]), ' ');

-- One row per household per cycle (latest submission), and every row that lost deduplication
CREATE OR REPLACE TABLE stg_household_cycle AS SELECT * FROM read_parquet('{silver}/household_cycle.parquet');
CREATE OR REPLACE TABLE stg_quarantine      AS SELECT * FROM read_parquet('{silver}/quarantine.parquet');

-- Every submission, harmonised: kept + quarantined. Field-operations metrics are computed on this.
-- Rows without a SurveyCTO KEY are blank lines in the export, not submissions, so they are excluded.
CREATE OR REPLACE VIEW stg_all_submissions AS
SELECT survey_cycle, cycle_order, submission_key, household_id, submitted_at, interview_status, consent,
       interview_duration_sec, district, subcounty, parish, village, gps_lat,
       TRUE AS is_kept, NULL::VARCHAR AS reject_reason
FROM stg_household_cycle
UNION ALL
SELECT survey_cycle, cycle_order, submission_key, household_id, submitted_at, interview_status, consent,
       interview_duration_sec, district, subcounty, parish, village, gps_lat,
       FALSE, reject_reason
FROM stg_quarantine
WHERE reject_reason <> 'empty_row';
