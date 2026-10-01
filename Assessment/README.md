# RTV Data Engineer Technical Assessment

## About Us

At Raising The Village (RTV), we are dedicated to eradicating ultra-poverty in Sub-Saharan Africa. As a dynamic, rapidly growing international development organization, we've assembled a team of over 250 passionate individuals in Uganda, alongside an additional 17 professionals in North America and 15 in Rwanda. Together, we are committed to elevating communities out of ultra-poverty by implementing innovative solutions and leveraging advanced data analytics to drive impact.

To date, our holistic approach has positively impacted over 2 million lives across Uganda, Rwanda, Tanzania, and the Democratic Republic of Congo since 2012, and we're poised to achieve even greater milestones, aiming to assist 1 million individuals annually by 2027. Our growth and success are fueled by the invaluable support of global partners who share our vision of sustainable change. Learn more about our impactful programs at [www.raisingthevillage.org](https://www.raisingthevillage.org)

The **VENN department** is the data and technology backbone of our organization, connecting advanced analytics and custom software tools with field implementation to ensure data-informed decision-making at every level.

## Assessment Overview

- **Time**: 5 Hours
- **Points**: 100
- For any follow-up questions or extension requests please contact - [nakagujje.kiberu@raisingthevillage.org](mailto:nakagujje.kiberu@raisingthevillage.org)

This assessment evaluates your proficiency in designing and implementing end-to-end data engineering solutions using RTV longitudinal household survey data. You will demonstrate expertise in data architecture, ETL/ELT processes, data warehousing, and analytical visualization.

## Submission Instructions

**Required Deliverables**

- **Source Code**: Complete, executable codebase with clear README
- **Documentation**: Architecture diagrams, setup instructions, and design rationale
- **Dashboard**: Simple dashboard with insights
- **Submission Note**: `SUBMISSION.md` at the repository root with hours spent, assumptions, and the commit SHA to be evaluated

**Submission Format**

- GitHub repository with organized folder structure
- Provide clear instructions for running your solution on a clean machine

## Technical Challenge

**Primary Objective**: Design and build a complete data pipeline and analytical dashboard that enables RTV to track household survey progress and field operations over time using our three-wave SurveyCTO cohort data.

**Dataset Overview**

The artifacts (data and data collection tools) to use are in the folder `data`.

For simplicity, you will work with the cohort spanning 3 survey cycles:

- Baseline Survey - `01_baseline.csv`
- Year 1 Follow-up - `02_year_one.csv`
- Year 2 Follow-up - `03_year_two.csv`

The corresponding collection tools for the datasets are labeled as follows:

- `ahs_2021_baseline.html`
- `ahs_2021_year1.html`
- `ahs_2021_year2.html`

Each CSV is a wide SurveyCTO export with 1,000-7,000+ variables. Schemas differ across survey cycles. Use the collection tool for each cycle as its data dictionary for field names, labels, and coded choices.

Treat all files as confidential. Exports may include attachment URLs or other sensitive metadata. Do not commit secrets, tokens, or credentials.

## Deliverables

### 1. Data Pipeline Architecture

Design and implement a modern data pipeline solution that addresses longitudinal household survey data challenges:

**Core Components**:

- **Data Lake Foundation**: Immutable Bronze layer per survey cycle with all source columns preserved (local filesystem, MinIO, AWS S3, GCS, Azure Blob)
- **Data Ingestion**: Repeatable load of all 3 CSV exports with ingest metadata (`ingested_at`, `source_file`, `survey_cycle`, row hash)
- **ELT vs ETL**: Justify your transformation strategy choice
- **Schema Management**: Handle evolving survey structures and variable changes across cycles
- **Data Quality**: Profiling, validation, and a minimum of 5 automated tests
- **Orchestration**: Single entrypoint running Bronze, Silver, Gold, tests, and reports in dependency order
- **Monitoring & Observability**: Row counts per cycle, pipeline health, error handling

**Technology Options**:

- **Local**: Python/pandas, Apache Spark, dbt Core, Dagster, Airflow, DuckDB, PostgreSQL
- **Commercial/Cloud**: Databricks, Snowflake, BigQuery
- **Hybrid**: Mix local and cloud components

**Deliverable**: Executable code, architecture diagram, design document explaining technology choices

### 2. Data Warehouse & Transformation Strategy

Implement a warehouse solution optimized for analytical workloads on longitudinal survey data:

**Key Considerations**:

- **Warehouse Selection**: Choose and justify technology for wide, multi-file survey data (DuckDB, PostgreSQL, Databricks, Snowflake, BigQuery)
- **ELT Implementation**: Transformation logic within the warehouse (SQL, dbt, PySpark)
- **Schema Design**: Conformed Silver layer and dimensional Gold layer
- **Household Grain**: Defensible household identifier for within-cycle deduplication and cross-cycle linkage
- **Performance Optimization**: Column pruning, partitioning, indexing for high-dimensional exports
- **Variable Cataloging**: Metadata for fields used in Silver and Gold and their source cycle

**Transformation Challenges**:

- Within-cycle deduplication to the latest submission per household with documented tie-breakers
- Variable normalization across cycles with changing names/definitions
- Multi-level geographic hierarchy from coded form values (region, district)
- Derived metrics and business logic for completion, consent, and cross-cycle comparison

**Required Gold Objects**:

- **`fct_survey_submissions`**: Fact table at a documented grain (one row per household per cycle after deduplication, or an equivalent you justify)
- **`dim_geography`**: District, region name, region code
- **`dim_time`**: Calendar attributes for submission date
- **`dim_survey_cycle`**: Baseline, Year 1, Year 2
- **`rpt_field_operations`**: Operational metrics
- **`rpt_program_summary`**: Program and longitudinal metrics

**Deliverable**: Complete warehouse implementation with transformation logic, schema documentation, performance analysis

### 3. Analytical Dashboard

Build a dashboard enabling stakeholders to explore insights from the data warehouse. Focus on visualizations valuable for RTV's poverty-fighting mission.

**Required Views**:

- **Field Operations**: Submission volumes over time, interview status mix, missing location rate, deduplication impact by cycle
- **Program Summary**: Completion and consent rates by district and month, demographics of completed and consented households, comparison across survey cycles

**Required Metrics**:

- **Operational**: Raw and deduplicated submission counts per cycle, duplicate household rate, missing location rate, submissions by status, average interview duration
- **Program**: Completion rate, consent rate, completions by district and month, demographics of completed and consented households (age bands you define)
- **Longitudinal**: At least 1 metric you define across cycles (households observed in 1, 2, or 3 cycles; change in completion or consent rate from baseline to Year 2)

Document metric formulas and denominators. Where a metric cannot be defined consistently across cycles, state why.

**Visualization Options**:

- **Local**: Streamlit, Plotly Dash, Jupyter notebooks, Grafana, Metabase, Apache Superset
- **Commercial**: Tableau, Power BI, Looker, Hex, Observable
- **Custom**: web applications

**Deliverable**: Simple dashboard with user documentation

### 4. Technical Documentation

**Required**:

- README with setup and execution instructions
- Architecture document covering three-cycle ingest, grains, deduplication, cross-cycle alignment, and ELT choice
- `SUBMISSION.md` with hours spent, assumptions, commit SHA, and production next steps
- Code documentation and inline comments
- Data quality assessment and validation results
- Performance considerations and scalability notes
- Automated testing frameworks

## Infrastructure Options

Choose the approach that best demonstrates your skills:

**Local Development**

- Containerized stack using Docker Compose for easy evaluation
- Object storage simulation with MinIO or local filesystem
- PostgreSQL, DuckDB, or ClickHouse as warehouse
- Include setup scripts and clear documentation

**Cloud/Commercial**

- Managed services (Snowflake, BigQuery, Databricks, etc.)
- Document costs and provide screenshots/demos for evaluation

**Hybrid**

- Combine local orchestration with cloud warehouse
- Balance cost-effectiveness with feature requirements

RTV production runs on Databricks, Delta Lake, and Unity Catalog. A short section on how your design would map to that platform is welcome.

Data Sources - `[data/](data/)`