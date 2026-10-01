CREATE OR REPLACE TABLE dim_survey_cycle AS
SELECT c.survey_cycle, c.cycle_order, c.cycle_label, c.source_file, c.form_file, c.choice_list_cycle,
       year(min(s.submitted_at))   AS survey_year,
       min(s.submitted_at)::DATE   AS fieldwork_start,
       max(s.submitted_at)::DATE   AS fieldwork_end
FROM (VALUES {cycle_values}) AS c(survey_cycle, cycle_order, cycle_label, source_file, form_file, choice_list_cycle)
LEFT JOIN stg_all_submissions s USING (survey_cycle)
GROUP BY ALL
ORDER BY c.cycle_order;

-- Calendar spine covering every submission date (including quarantined rows)
CREATE OR REPLACE TABLE dim_time AS
WITH days AS (
  SELECT unnest(generate_series(min(submitted_at)::DATE::TIMESTAMP, max(submitted_at)::DATE::TIMESTAMP,
                                INTERVAL 1 DAY))::DATE AS d
  FROM stg_all_submissions
)
SELECT CAST(strftime(d, '%Y%m%d') AS INTEGER) AS date_key,
       d                                     AS date,
       year(d)                               AS year,
       quarter(d)                            AS quarter,
       month(d)                              AS month,
       monthname(d)                          AS month_name,
       strftime(d, '%Y-%m')                  AS year_month,
       weekofyear(d)                         AS iso_week,
       isodow(d)                             AS day_of_week,
       dayname(d)                            AS day_name,
       isodow(d) >= 6                        AS is_weekend
FROM days;

-- Geographic hierarchy: region > district > subcounty > parish > cluster > village.
-- The forms only carry district and below (as preloaded labels); region comes from
-- config/district_regions.csv. District CODES are not used: their numbering differs per cycle.
-- Names are not consistent across cycles (baseline parish 'KAYO-BUJENGWE' vs 'Bujengwe' later), so:
--   * the conformed key is (district, village), normalised: stable across cycles
--   * the conformed hierarchy comes from the LATEST cycle in which the village appears
--   * every raw spelling is kept in dim_geography_name_history
CREATE OR REPLACE TABLE dim_geography_name_history AS
SELECT DISTINCT
       md5(lower(trim(district)) || '|' || lower(trim(village))) AS geo_key,
       survey_cycle, district, subcounty, parish, cluster, village
FROM stg_household_cycle;

CREATE OR REPLACE TABLE dim_geography AS
WITH g AS (
  SELECT geo_key,
         arg_max(title_case(district),  cycle_order) AS district,
         arg_max(title_case(subcounty), cycle_order) AS subcounty,
         arg_max(title_case(parish),    cycle_order) AS parish,
         arg_max(title_case(cluster),   cycle_order) FILTER (WHERE cluster IS NOT NULL) AS cluster,
         arg_max(title_case(village),   cycle_order) AS village,
         count(DISTINCT survey_cycle)                AS cycles_seen,
         count(DISTINCT lower(parish))               AS parish_spellings_seen
  FROM (SELECT md5(lower(trim(district)) || '|' || lower(trim(village))) AS geo_key, * FROM stg_household_cycle)
  GROUP BY geo_key
)
SELECT g.geo_key, r.region_code, r.region_name, r.sub_region,
       g.district, g.subcounty, g.parish, g.cluster, g.village, g.cycles_seen, g.parish_spellings_seen
FROM g
LEFT JOIN read_csv('{config_dir}/district_regions.csv', header = true) r ON lower(r.district) = lower(g.district);

-- Household dimension: panel membership across cycles
CREATE OR REPLACE TABLE dim_household AS
SELECT household_id,
       min(cycle_order)                                             AS first_cycle_order,
       count(DISTINCT survey_cycle)                                 AS n_cycles,
       string_agg(survey_cycle, ' + ' ORDER BY cycle_order)         AS cycle_pattern,
       count(DISTINCT survey_cycle) = {n_cycles}                    AS in_balanced_panel,
       bool_or(survey_cycle = 'baseline')                           AS has_baseline,
       arg_min(wealth_quartile, cycle_order)                        AS first_wealth_quartile,
       coalesce(max(cohort), '2021')                                AS cohort,   -- only captured in year2
       arg_min(head_sex, cycle_order)                               AS head_sex_first_seen,
       count(DISTINCT district) > 1                                 AS moved_district
FROM stg_household_cycle
GROUP BY household_id;
