# RTV household survey pipeline

Turns the three RTV household-survey exports (Baseline, Year 1, Year 2) into a DuckDB warehouse,
checks data quality, and serves a Streamlit dashboard for field operations and program progress.

```
raw → bronze → catalog → silver → warehouse (DuckDB) → quality → tests → dashboard
```

## Run it

Needs Python 3.11+. Put the 3 CSVs and 3 form HTML files in `Assessment/data/` (they are gitignored).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

make pipeline     # every stage, ending with the 20 tests (~17 s)
make dashboard    # http://localhost:8501
```

`make test` runs the tests on their own. Resume from a stage: `python -m pipeline.run --from silver`.
Start over: `make clean`.

### With Docker

```bash
docker compose up --build    # runs the pipeline, then serves the dashboard on :8501
```

`Assessment/data` is mounted read-only; source data is not copied into the image.

## Dashboard

Filters at the top (survey cycles, districts) apply to every view.

| Tab | Shows |
|---|---|
| Field operations | Raw vs deduplicated submissions, submissions per day, interview status mix, duplicate household / missing location / missing GPS rates, average interview duration |
| Program summary | Completion and consent rates, completions by district and month, demographics of completed and consented households, comparison across cycles |
| Longitudinal | Households observed in 1, 2 or 3 cycles; poverty trend for the 504 households seen in every cycle |
| Data quality | All checks, quarantined rows, the variable catalog, recent pipeline runs |

Every chart has a table view underneath. Metric formulas: [docs/METRICS.md](docs/METRICS.md).

## Layout

| Path | Contents |
|---|---|
| `pipeline/` | Stages: `ingest`, `catalog`, `harmonize`, `warehouse`, `quality`, and `run.py` (orchestrator) |
| `sql/` | Warehouse models, run in file order: staging, dimensions, facts, reports |
| `config/config.py` | Paths, survey cycles, thresholds |
| `config/*.csv` | Variable map, label conforming, district → region |
| `utils/` | Helpers, profiling, and the generators for the config CSVs |
| `dashboards/app.py` | Streamlit dashboard |
| `tests/` | Unit tests and integration tests (need a built warehouse) |
| `docs/` | Architecture, metric definitions, generated data-quality report |

## Outputs

- `lake/`: raw copies, Bronze/Silver Parquet, `warehouse.duckdb`
- `docs/DATA_QUALITY_REPORT.md`: regenerated on every run
- `logs/pipeline.jsonl`: one JSON event per line

## Settings

| Environment variable | Default |
|---|---|
| `RTV_DATA_DIR` | `Assessment/data` |
| `RTV_LAKE_DIR` | `lake` |
| `RTV_DUCKDB_MEMORY_LIMIT` | `1GB` |

## Changing the mappings

The variable map and label CSVs are generated as drafts, reviewed, then committed:

```bash
python -m utils.build_variable_map --force    # edit SPEC in the script first
python -m utils.build_label_conform --force   # edit MANUAL in the script first
```

Each prints what needs review.

## Docs

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): design, ELT and DuckDB choice, grain, deduplication,
  cross-cycle alignment, performance, Databricks mapping
- [docs/METRICS.md](docs/METRICS.md): metric formulas and denominators
- [SUBMISSION.md](SUBMISSION.md): assumptions and next steps
