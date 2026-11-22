"""Command-line entry point.

    python run_pipeline.py            # full build: ingest -> warehouse -> analysis -> reports
    python run_pipeline.py --watch    # also poll data/incoming/ for new crime CSV batches
"""
import argparse
import shutil
import time

import pandas as pd

import config
from pipeline import db, ingest, runner


def print_summary(results):
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    uc1 = results["uc1"]
    print("=" * 80)
    print(f"Warehouse backend: {results['backend']}  |  DB: {db.get_engine().url.render_as_string(hide_password=True)}")
    if uc1:
        print(f"\n[UC1] Shape: {uc1['profile']['rows']} rows x {uc1['profile']['columns']} columns")
        print("\nFirst 10 rows:\n", uc1["profile"]["head"].to_string())
        print("\nSchema / dtypes:\n", uc1["profile"]["dtypes"].T.to_string())
        print("\nMissing % per column (NumPy):\n", uc1["missing_pct"].to_string())
        print("\nAnomaly checks:\n", uc1["anomalies"].to_string(index=False))
    print("\n[UC4] SQL query results:")
    for name, df in results["uc4"]["queries"].items():
        print(f"\n-- {name}\n{df.to_string(index=False)}")
    print("\n[REC] Top patrol recommendations:")
    print(results["rec"]["top_areas"][["priority", "community_name", "risk_score", "crime_count",
                                       "arrest_rate_pct", "patrol_radius_km"]].to_string(index=False))
    print("\nKEY FINDINGS")
    for section, qa in results.get("insights", {}).items():
        print(f"\n## {section}")
        for q, a in qa:
            print(f" - {q}\n     {a}")
    ex = results["exports"]
    print(f"\nReports: {ex['html']}\n         {ex['excel']}\n         {ex['csv_dir']}")
    print(f"Charts:  {config.CHART_DIR}")


def watch(interval):
    config.INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    processed = config.INCOMING_DIR / "processed"
    processed.mkdir(exist_ok=True)
    print(f"Watching {config.INCOMING_DIR} every {interval}s for new crime CSV files (Ctrl+C to stop)")
    while True:
        for path in sorted(config.INCOMING_DIR.glob("*.csv")):
            try:
                res = runner.ingest_batch(ingest.read_csv_robust(path))
                log = res["batch_log"]
                print(f"{path.name}: +{log['inserted']} new, {log['updated']} updated, "
                      f"{log['quarantined']} quarantined. Top hotspot: "
                      f"{res['rec']['top_areas'].iloc[0]['community_name']}")
                shutil.move(str(path), processed / path.name)
            except Exception as exc:  # keep watching even if a file is malformed
                print(f"{path.name}: FAILED - {exc}")
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Chicago crime data pipeline")
    parser.add_argument("--watch", action="store_true", help="poll data/incoming for new batches")
    parser.add_argument("--interval", type=int, default=10)
    args = parser.parse_args()
    print_summary(runner.run_all())
    if args.watch:
        watch(args.interval)


if __name__ == "__main__":
    main()
