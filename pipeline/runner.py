"""End-to-end orchestration used by both the CLI and the web application."""
import json
import threading
from datetime import datetime
from pathlib import Path

import pandas as pd

import config
from pipeline import db, eda, ingest, recommend, reporting, stats
from pipeline.common import load_crime_frame

_lock = threading.Lock()


def build_insights(uc1, uc2, uc3, uc4, rec):
    a = uc2["answers"]
    out = uc3["outliers"]
    yearly = uc2["arrest_by_year"]
    reliable = yearly[yearly["Year"].isin(a["arrest_rate_reliable_years"])]
    top = rec["top_areas"].iloc[0]
    corr = uc3["strongest_correlations"]
    corr_txt = "; ".join(f"{r.feature_a}~{r.feature_b} r={r.r}" for r in corr.head(3).itertuples())
    return {
        "Use Case 1 - Load & Clean": [
            ("How many rows and columns are there?",
             f"{uc1['profile']['rows']} rows x {uc1['profile']['columns']} columns in chicago_crime_dataset.csv "
             f"({uc1['log']['repaired_lines']} truncated lines repaired so no record was lost)."),
            ("Columns with > 50% missing - can they be dropped?",
             "None. Highest missing share is "
             f"{uc1['missing_pct'].iloc[0]}% ({', '.join(uc1['missing_pct'][uc1['missing_pct'] == uc1['missing_pct'].iloc[0]].index)}), "
             "so no column is dropped." if not uc1["drop_candidates"] else
             f"Yes: {uc1['drop_candidates']} exceed 50% (dropped from analysis, retained in staging)."),
            ("How many unique crime types exist?",
             f"{uc1['unique_crime_types']} primary crime types across {uc1['unique_iucr_codes']} distinct IUCR codes."),
            ("Are there anomalies in date formats or obvious outliers?",
             "; ".join(f"{r.check}: {r.count}" + (f" ({r.note})" if r.note else "")
                       for r in uc1["anomalies"].itertuples())),
        ],
        "Use Case 2 - Exploratory Analysis": [
            ("Is the crime rate rising or decreasing?",
             f"Recorded crimes are {a['trend']} ({', '.join(f'{y}: {c}' for y, c in uc2['yearly'].itertuples(index=False))}). "
             "Caveat: the extract is dominated by Apr-May 2016 records; earlier years only contain late-reported cases."),
            ("Which crime category is most frequent?",
             f"{a['most_frequent_category']} ({a['most_frequent_category_pct']}% of all crimes)."),
            ("What percentage of crimes result in arrest?", f"{a['arrest_rate_pct']}%."),
            ("Is the arrest rate consistent across years?",
             f"No - it varies widely (std dev {a['arrest_rate_std']} pts: "
             + ", ".join(f"{r.Year}: {r.arrest_rate_pct}% of {r.crimes}" for r in yearly.itertuples())
             + "). Only years with >=30 records are statistically meaningful: "
             + ", ".join(f"{r.Year} ({r.arrest_rate_pct}%)" for r in reliable.itertuples()) + "."
             if not a["arrest_rate_consistent"] else f"Yes (std dev {a['arrest_rate_std']} pts)."),
            ("Which month has the highest crime frequency?", f"{a['peak_month']} ({a['peak_month_count']} crimes)."),
        ],
        "Use Case 3 - Statistical Insights": [
            ("Hourly distribution",
             "Source dates carry no time component, so all incidents fall at hour 0 - "
             "time-of-day patrol planning needs timestamped data." if uc3["hourly"].astype(bool).sum() <= 1
             else f"Peak hour: {int(uc3['hourly'].idxmax())}:00."),
            ("Mean crime per community area (NumPy)",
             f"Mean {uc3['iqr_stats']['mean']}, median {uc3['iqr_stats']['median']}, "
             f"IQR {uc3['iqr_stats']['q1']}-{uc3['iqr_stats']['q3']}, upper fence {uc3['iqr_stats']['upper_fence']}."),
            ("Extreme outlier community areas (IQR)",
             ", ".join(f"{r.community_name} ({r.crime_count})" for r in out.itertuples()) or "None"),
            ("Strongest correlations", corr_txt + (f". Constant features excluded: {uc3['constant_features']}"
                                                   if uc3["constant_features"] else "")),
        ],
        "Recommendations": [
            ("Which locality needs more patrols?",
             f"{top['community_name']} (risk score {top['risk_score']}, {top['crime_count']} crimes, "
             f"arrest rate {top['arrest_rate_pct']}%). {top['recommendation']}"),
            ("High-priority areas", ", ".join(rec["areas"].query("priority == 'HIGH'")["community_name"])),
        ],
    }


def _write_sql_artifacts():
    sql_dir = config.BASE_DIR / "sql"
    sql_dir.mkdir(exist_ok=True)
    (sql_dir / "schema_mysql.sql").write_text(db.mysql_ddl(), encoding="utf-8")
    body = "\n\n".join(f"-- {name}\n{sql.strip()};" for name, sql in reporting.QUERIES.items())
    body += "\n\n" + "\n\n".join(f"-- {n}\n{s['ddl'].strip()};\nINSERT INTO {n}\n{s['select'].strip()};"
                                 for n, s in reporting.SUMMARY_TABLES.items())
    (sql_dir / "queries.sql").write_text(body + "\n", encoding="utf-8")


def analyse(engine, uc1=None, chart_dir=None):
    """Run use cases 2-4 + recommendations against the current warehouse contents."""
    df = load_crime_frame(engine)
    communities = pd.read_sql("SELECT community_code, community_name FROM city_community", engine)
    uc2 = eda.run(df, chart_dir)
    uc3 = stats.run(df, communities, chart_dir)
    uc4 = reporting.run(engine, chart_dir)
    rec = recommend.recommend(df)
    rec["chart"] = recommend.hotspot_map(df, rec, chart_dir)
    results = {"uc1": uc1, "uc2": uc2, "uc3": uc3, "uc4": uc4, "rec": rec, "df": df,
               "generated_at": datetime.now().isoformat(timespec="seconds"),
               "backend": engine.dialect.name}
    if uc1 is not None:
        results["insights"] = build_insights(uc1, uc2, uc3, uc4, rec)
    return results


def run_all(engine=None, data_dir=None):
    from pipeline import report
    with _lock:
        engine = engine or db.get_engine()
        uc1 = ingest.run(engine, data_dir)
        results = analyse(engine, uc1)
        _write_sql_artifacts()
        results["exports"] = report.export_all(results)
        _save_uc1_snapshot(uc1)
        return results


def ingest_batch(raw_df, engine=None):
    """Near-real-time path: upsert new crime records and refresh analytics/recommendations."""
    from pipeline import report
    with _lock:
        engine = engine or db.get_engine()
        log = ingest.load_incremental(engine, raw_df)
        uc1 = _load_uc1_snapshot()
        results = analyse(engine, uc1)
        results["exports"] = report.export_all(results)
        results["batch_log"] = log
        return results


# UC1 profiling relates to the original master file; persist it so the web app can show it
# after incremental batches without re-reading the raw files.
_SNAPSHOT = config.OUTPUT_DIR / "uc1_snapshot.pkl"


def _save_uc1_snapshot(uc1):
    _SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    pd.to_pickle(uc1, _SNAPSHOT)


def _load_uc1_snapshot():
    return pd.read_pickle(_SNAPSHOT) if Path(_SNAPSHOT).exists() else None


def summary_json(results):
    df = results["df"]
    return json.loads(json.dumps({
        "generated_at": results["generated_at"],
        "total_crimes": int(len(df)),
        "arrest_rate_pct": results["uc2"]["answers"]["arrest_rate_pct"],
        "unique_crime_types": int(df["primary_type"].nunique()),
        "most_frequent_category": results["uc2"]["answers"]["most_frequent_category"],
        "yearly": results["uc4"]["views"]["vw_crime_yearly"].to_dict(orient="records"),
    }, default=float))
