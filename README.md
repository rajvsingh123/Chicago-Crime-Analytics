# Chicago Crime Data Analytics (CPD × Accenture Capstone)

End-to-end Python data pipeline and web application that ingests Chicago Police Department
crime data, stores it in a MySQL (or SQLite fallback) data warehouse, analyses it with
Pandas/NumPy, visualises it with Matplotlib/Seaborn, exports reports, and produces
near-real-time patrol recommendations.

## Quick start

```powershell
pip install -r requirements.txt
python run_pipeline.py          # ingest -> warehouse -> analysis -> charts -> reports
python app.py                   # web app at http://127.0.0.1:5000
python -m pytest                # tests
```

### Using MySQL instead of SQLite
SQLite (`data/chicago_crime.db`) is used by default, as allowed by the brief. To use MySQL,
set a connection URL (the database is created automatically). It uses MySQL Connector/Python:

```powershell
$env:CRIME_DB_URL = "mysql+mysqlconnector://root:password@localhost:3306/chicago_crime"
python run_pipeline.py
```

For public repositories, use an environment variable or a local, untracked
configuration for real credentials; do not commit passwords or secrets.

The equivalent MySQL DDL is generated to [sql/schema_mysql.sql](sql/schema_mysql.sql), and all
reporting SQL is in [sql/queries.sql](sql/queries.sql).

## Project layout

| Path | Purpose |
|---|---|
| `config.py` | Paths, DB URL, thresholds |
| `pipeline/ingest.py` | **Use Case 1**: robust CSV load, profiling, cleaning, feature engineering, NumPy missing-value analysis, anomaly detection, warehouse load (full + incremental upsert) |
| `pipeline/db.py` | Warehouse schema (data model with PK/FK), views, engine creation |
| `pipeline/eda.py` | **Use Case 2**: yearly trend, top-10 categories, arrest rate, Month × DayOfWeek heatmap, top community areas |
| `pipeline/stats.py` | **Use Case 3**: hourly distribution, NumPy community statistics, box plot + IQR outliers, correlation heatmap |
| `pipeline/reporting.py` | **Use Case 4**: summary tables loaded via the DB-API connector, SQL queries, `vw_crime_yearly` / `vw_crime_by_category` read into Pandas and plotted |
| `pipeline/recommend.py` | Patrol hotspot ranking (severity × recency) with patrol perimeters |
| `pipeline/report.py` | Exports: HTML report, Excel workbook, CSV extracts |
| `pipeline/runner.py` | Orchestration shared by CLI and web app |
| `run_pipeline.py` | CLI (`--watch` polls `data/incoming/` for new crime CSV batches) |
| `app.py`, `templates/` | Flask web app |
| `data/raw/` | Master + reference CSVs |
| `outputs/charts`, `outputs/reports` | Generated charts and reports |

## Warehouse design

* **Staging (`stg_*`)** – every raw file is stored verbatim (all text) with `batch_id` /
  `loaded_at`, so no data is ever discarded (regulatory / insurance use-cases).
* **Core model** – `chicago_crime` (PK `case_number`) with FKs to `iucr`, `police_beat_info`,
  `district_ps_info`, `ward_office`, `city_community`, plus derived `month`, `day_of_week`, `hour`.
* **`crime_quarantine`** – records that violate constraints (missing keys, unparseable dates,
  older duplicate versions) are kept here with a reason.
* **Views** – `vw_crime_yearly`, `vw_crime_by_category`, `vw_crime_details` (denormalised).
* **Summary tables** – `summary_crime_yearly`, `summary_crime_by_category`,
  `summary_community_area`, `summary_district`.

## Data quality handling

* The crime CSV ends with two rows whose quoted `location` value is never closed; the loader
  repairs these lines so all 498 records are kept.
* IUCR codes are zero-padded (`486` → `0486`) to match `iucr_codes.csv`; FBI codes likewise (`6` → `06`).
* Categorical text is trimmed, whitespace-collapsed and upper-cased; booleans normalised.
* Missing `location_desc` → `UNKNOWN`; missing coordinates (5.8%) stay NULL and are flagged
  (`has_coordinates`), since they cannot be imputed reliably. No column exceeds 50% missing.
* Duplicate ward/beat rows in the reference files are collapsed (most complete row kept) for the PK.
* Lookup keys referenced by crimes but missing from reference files get `UNKNOWN` placeholder rows
  so FK integrity holds without dropping crimes.

## Web application

* **Dashboard** – KPIs, patrol recommendations, key findings (answers to every use-case question), all charts.
* **Warehouse Reports** – the SQL queries with results, views and summary tables.
* **Data Explorer** – filter/search crime records.
* **Ingest Data** – upload a CSV batch or report a single incident; the warehouse is upserted and
  analytics/recommendations refresh immediately (near-real-time).
* **Exports** – HTML report, Excel workbook, cleaned CSV; JSON APIs at `/api/summary` and `/api/recommendations`.

## Known data limitations

* Dates have no time component, so the hourly distribution (Use Case 3.1) is degenerate (all at 00:00);
  the code handles timestamped data when available.
* 490 of 498 records are from Apr–May 2016; earlier years contain only late-reported cases, so
  year-over-year trends and per-year arrest rates for 2012–2015 are not statistically meaningful.
