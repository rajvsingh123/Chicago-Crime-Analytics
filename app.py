"""Flask web application for the CPD crime analytics platform.

    python app.py   ->  http://127.0.0.1:5000
"""
import os
from datetime import datetime

import pandas as pd
from flask import (Flask, abort, flash, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)
from sqlalchemy import inspect, text

import config
from pipeline import db, ingest, report, runner
from pipeline.report import all_charts
from pipeline.reporting import QUERIES

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(16).hex())
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

STATE = {"results": None}


def engine():
    if "engine" not in STATE:
        STATE["engine"] = db.get_engine()
    return STATE["engine"]


def results():
    if STATE["results"] is None:
        eng = engine()
        if inspect(eng).has_table("chicago_crime") and runner._load_uc1_snapshot() is not None:
            res = runner.analyse(eng, runner._load_uc1_snapshot())
            res["exports"] = report.export_all(res)
            STATE["results"] = res
        else:
            STATE["results"] = runner.run_all(eng)
    return STATE["results"]


def _tbl(df, n=None):
    return (df.head(n) if n else df).to_html(index=False, classes="table", border=0, na_rep="")


@app.route("/")
def dashboard():
    r = results()
    df = r["df"]
    kpis = {
        "Total crimes": f"{len(df):,}",
        "Arrest rate": f"{r['uc2']['answers']['arrest_rate_pct']}%",
        "Crime types": df["primary_type"].nunique(),
        "Most common": r["uc2"]["answers"]["most_frequent_category"].title(),
        "Top hotspot": r["rec"]["top_areas"].iloc[0]["community_name"],
        "Domestic": f"{df['Domestic'].mean() * 100:.1f}%",
    }
    rec = r["rec"]["top_areas"][["priority", "community_name", "risk_score", "crime_count",
                                 "recent_7d", "arrest_rate_pct", "top_crime", "peak_day",
                                 "patrol_radius_km", "recommendation"]]
    return render_template("dashboard.html", r=r, kpis=kpis, rec=rec.to_dict(orient="records"),
                           insights=r.get("insights", {}), charts=sorted(all_charts(r)))


@app.route("/sql")
def sql_reports():
    r = results()
    sections = [(name, QUERIES[name].strip(), _tbl(df)) for name, df in r["uc4"]["queries"].items()]
    views = [(name, _tbl(df)) for name, df in r["uc4"]["views"].items()]
    summaries = [(name, _tbl(df.sort_values(df.columns[2], ascending=False) if "community" in name
                             else df)) for name, df in r["uc4"]["summaries"].items()]
    return render_template("sql.html", r=r, sections=sections, views=views, summaries=summaries)


@app.route("/data")
def data_explorer():
    r = results()
    df = r["df"]
    f = {k: request.args.get(k, "") for k in ("primary_type", "community", "arrest", "q")}
    view = df
    if f["primary_type"]:
        view = view[view["primary_type"] == f["primary_type"]]
    if f["community"]:
        view = view[view["community_name"] == f["community"]]
    if f["arrest"] in ("1", "0"):
        view = view[view["Arrest"] == (f["arrest"] == "1")]
    if f["q"]:
        q = f["q"].upper()
        view = view[view["block"].str.contains(q, na=False, regex=False)
                    | view["case_number"].str.contains(q, na=False, regex=False)
                    | view["description"].str.contains(q, na=False, regex=False)]
    cols = ["case_number", "date", "block", "primary_type", "description", "location_desc", "arrest",
            "domestic", "beat_num", "district_name", "community_name", "latitude", "longitude"]
    out = view.sort_values("date", ascending=False)[cols]
    return render_template("data.html", r=r, f=f, count=len(out), table=_tbl(out, 200),
                           types=sorted(df["primary_type"].unique()),
                           communities=sorted(df["community_name"].dropna().unique()))


@app.route("/ingest", methods=["GET", "POST"])
def ingest_page():
    iucr = pd.read_sql("SELECT iucr_code, primary_type, description FROM iucr ORDER BY primary_type, iucr_code",
                       engine())
    if request.method == "POST":
        try:
            if request.form.get("mode") == "file":
                upload = request.files.get("file")
                if not upload or not upload.filename.lower().endswith(".csv"):
                    raise ValueError("Please choose a .csv file")
                raw = ingest.read_csv_robust(upload.read())
            else:
                raw = _form_to_frame(request.form)
            res = runner.ingest_batch(raw, engine())
            STATE["results"] = res
            log = res["batch_log"]
            flash(f"Batch {log['batch_id']}: {log['inserted']} inserted, {log['updated']} updated, "
                  f"{log['quarantined']} quarantined. Recommendations refreshed - top hotspot is "
                  f"{res['rec']['top_areas'].iloc[0]['community_name']}.", "success")
            return redirect(url_for("dashboard"))
        except Exception as exc:
            flash(f"Ingestion failed: {exc}", "error")
    return render_template("ingest.html", r=STATE["results"] or results(), iucr=iucr.to_dict(orient="records"),
                           columns=ingest.CRIME_COLUMNS, today=datetime.now().strftime("%Y-%m-%d"))


def _form_to_frame(form):
    required = ["case_number", "date", "iucr_code", "beat_num", "district_code", "ward_no", "community_code"]
    missing = [k for k in required if not form.get(k, "").strip()]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
    date = datetime.strptime(form["date"], "%Y-%m-%d")
    lat, lon = form.get("latitude", "").strip(), form.get("longitude", "").strip()
    with engine().connect() as conn:
        next_id = conn.execute(text("SELECT COALESCE(MAX(id), 0) + 1 FROM chicago_crime")).scalar()
    row = {
        "id": str(next_id), "case_number": form["case_number"], "date": date.strftime("%m/%d/%Y"),
        "block": form.get("block", ""), "iucr_code": form["iucr_code"],
        "location_desc": form.get("location_desc", ""),
        "arrest": "TRUE" if form.get("arrest") else "FALSE",
        "domestic": "TRUE" if form.get("domestic") else "FALSE",
        "beat_num": form["beat_num"], "district_code": form["district_code"], "ward_no": form["ward_no"],
        "community_code": form["community_code"], "fbi_code": form.get("fbi_code", ""),
        "x_coordinate": "", "y_coordinate": "", "year": str(date.year),
        "date_of_update": datetime.now().strftime("%m/%d/%Y"), "latitude": lat, "longitude": lon,
        "location": f"({lat}, {lon})" if lat and lon else "",
    }
    return pd.DataFrame([row], columns=ingest.CRIME_COLUMNS).replace("", pd.NA)


@app.route("/rebuild", methods=["POST"])
def rebuild():
    STATE["results"] = runner.run_all(engine())
    flash("Warehouse rebuilt from the master CSV files and all reports regenerated.", "success")
    return redirect(url_for("dashboard"))


@app.route("/charts/<name>.png")
def chart(name):
    return send_from_directory(config.CHART_DIR, f"{name}.png", max_age=0)


@app.route("/download/<kind>")
def download(kind):
    files = {"html": "chicago_crime_report.html", "excel": "chicago_crime_report.xlsx"}
    if kind in files:
        return send_from_directory(config.REPORT_DIR, files[kind], as_attachment=True)
    if kind == "crimes":
        path = config.REPORT_DIR / "chicago_crime_clean.csv"
        results()["df"].drop(columns=["Date"]).to_csv(path, index=False)
        return send_from_directory(config.REPORT_DIR, path.name, as_attachment=True)
    abort(404)


@app.route("/api/summary")
def api_summary():
    return jsonify(runner.summary_json(results()))


@app.route("/api/recommendations")
def api_recommendations():
    rec = results()["rec"]
    return jsonify({"as_of": str(rec["as_of"].date()),
                    "areas": rec["top_areas"].astype(object).where(rec["top_areas"].notna(), None)
                    .to_dict(orient="records")})


if __name__ == "__main__":
    results()
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", 5000)), debug=False)
