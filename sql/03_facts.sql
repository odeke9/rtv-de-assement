-- Which cycle's choice list decodes each cycle's codes
CREATE OR REPLACE TABLE meta_cycle_choice_source AS
SELECT * FROM (VALUES {choice_sources}) AS t(survey_cycle, choice_cycle);

-- Conformed labels: one spelling per concept across cycles (brackets, casing, renamed options)
CREATE OR REPLACE TABLE meta_choice_conformed AS
SELECT c.survey_cycle, c.field, c.code, c.label AS raw_label,
       coalesce(m.conformed_label, trim(regexp_replace(c.label, '[\[\]]', '', 'g'))) AS label
FROM meta_choice_list c
LEFT JOIN read_csv('{config_dir}/label_conform.csv', header = true) m
       ON m.field = c.field AND m.raw_label = trim(regexp_replace(c.label, '[\[\]]', '', 'g'));

-- NOTE: a macro's subquery is inlined into the caller. Two traps (both hit while building this):
--   1. an alias like "s" inside the macro silently binds to the CALLER's table "s" → use unusual aliases;
--   2. pass QUALIFIED arguments (t.survey_cycle), or "survey_cycle" becomes ambiguous inside the macro.
CREATE OR REPLACE MACRO choice_label(rid, fld, cd) AS (
  SELECT min(_cc.label) FROM meta_choice_conformed _cc
  JOIN meta_cycle_choice_source _rcs ON _rcs.choice_cycle = _cc.survey_cycle
  WHERE _rcs.survey_cycle = rid AND _cc.field = fld AND _cc.code = CAST(cd AS VARCHAR));

-- Fact: grain = one household per survey cycle, after deduplication (latest submission wins).
-- Includes households that were attempted but not completed/consented, flagged by is_completed /
-- is_consented, so completion and consent rates have a real denominator. Survey answers are NULL
-- for those rows.
CREATE OR REPLACE TABLE fct_survey_submissions AS
SELECT
  s.household_id,
  s.survey_cycle,
  s.cycle_order,
  md5(lower(trim(s.district)) || '|' || lower(trim(s.village))) AS geo_key,
  CAST(strftime(s.submitted_at, '%Y%m%d') AS INTEGER)            AS date_key,
  s.submission_key, s.submitted_at, s.started_at, s.ended_at, s.enumerator, s.form_version,
  s.household_submissions,
  s._row_hash AS row_hash,
  -- outcome
  s.interview_status,
  CASE s.interview_status WHEN 1 THEN 'Found' WHEN 2 THEN 'Moved away' WHEN 3 THEN 'Not found'
       WHEN 4 THEN 'Unavailable' WHEN 5 THEN 'Disability' ELSE 'Missing' END AS interview_status_label,
  s.consent, s.is_completed, s.is_consented,
  s.interview_duration_sec / 60.0                                 AS interview_duration_min,
  s.interview_minutes                                             AS wall_clock_minutes,
  -- demographics
  s.hh_size,
  CASE WHEN s.hh_size IS NULL THEN 'Unknown' WHEN s.hh_size <= 3 THEN '1-3' WHEN s.hh_size <= 6 THEN '4-6'
       WHEN s.hh_size <= 9 THEN '7-9' ELSE '10+' END              AS hh_size_band,
  s.head_age,
  CASE WHEN s.head_age IS NULL OR s.head_age < 15 OR s.head_age > 100 THEN 'Unknown'
       WHEN s.head_age < 25 THEN '15-24' WHEN s.head_age < 35 THEN '25-34' WHEN s.head_age < 45 THEN '35-44'
       WHEN s.head_age < 55 THEN '45-54' WHEN s.head_age < 65 THEN '55-64' ELSE '65+' END AS head_age_band,
  s.head_sex,      coalesce(choice_label(s.survey_cycle, 'hhh_sex', s.head_sex), 'Unknown')       AS head_sex_label,
  s.respondent,    coalesce(choice_label(s.survey_cycle, 'respondent', s.respondent), 'Unknown') AS respondent_label,
  s.head_education, s.head_literate,
  -- poverty measures
  s.hhip_usd_day, s.hhip_usd_ppp_day, s.hhip_usd_year, s.ppi_score, s.wealth_quartile,
  s.hhip_usd_day < {ultra_poor}                                  AS is_ultra_poor,
  s.hhip_usd_day >= {target}                                     AS meets_target,
  s.hhip_usd_day / nullif(s.hh_size, 0)                           AS hhip_usd_day_per_capita,
  -- income composition (annual, nominal USD)
  s.hh_income_usd_year, s.consumption_residues_usd_year,
  s.inc_seasonal_crops_usd, s.inc_perennial_crops_usd, s.inc_livestock_usd, s.inc_casual_labour_usd,
  s.inc_formal_employment_usd, s.inc_business_usd, s.inc_remittances_usd, s.inc_rent_usd,
  s.inc_vsla_profits_usd, s.inc_vegetables_usd,
  -- assets
  s.assets_usd, s.livestock_asset_usd, s.savings_ugx, s.loan_amount_ugx, s.owns_land, s.land_owned_acres,
  -- living standards (labels resolved per cycle because code lists changed between cycles)
  s.roof_material,   choice_label(s.survey_cycle, 'Material_roof', s.roof_material)                          AS roof_material_label,
  s.water_source,    choice_label(s.survey_cycle, 'Main_source_of_water_for_consumption', s.water_source)    AS water_source_label,
  s.toilet_type,     choice_label(s.survey_cycle, 'Type_of_Toilet_Facility', s.toilet_type)                  AS toilet_type_label,
  s.cooking_fuel,    choice_label(s.survey_cycle, 'Fuel_source_cooking', s.cooking_fuel)                     AS cooking_fuel_label,
  s.lighting_source, choice_label(s.survey_cycle, 'Lighting_source', s.lighting_source)                      AS lighting_source_label,
  s.all_members_have_shoes, s.water_litres_day, s.satisfied_quality_of_life,
  s.gps_lat, s.gps_lon
FROM stg_household_cycle s
ORDER BY s.cycle_order, s.household_id;
