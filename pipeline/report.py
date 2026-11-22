"""Export analytical results: Excel workbook, CSV extracts and a self-contained HTML report."""
import base64
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

import config

TEMPLATE_DIR = config.BASE_DIR / "templates"


def _sheets(results):
    uc1, uc2, uc3, uc4, rec = (results.get(k) for k in ("uc1", "uc2", "uc3", "uc4", "rec"))
    sheets = {}
    if uc1:
        sheets["UC1_missing_pct"] = uc1["missing_pct"].reset_index().rename(columns={"index": "column"})
        sheets["UC1_anomalies"] = uc1["anomalies"]
        sheets["UC1_schema"] = uc1["profile"]["dtypes"].reset_index().rename(columns={"index": "column"})
    sheets.update({
        "UC2_crimes_per_year": uc2["yearly"],
        "UC2_top10_categories": uc2["top10"],
        "UC2_arrest_by_year": uc2["arrest_by_year"],
        "UC2_month_vs_day": uc2["month_day"].reset_index().rename(columns={"index": "Month"}),
        "UC2_top10_areas": uc2["top_areas"],
        "UC3_crimes_by_hour": uc3["hourly"].reset_index(),
        "UC3_community_counts": uc3["community_counts"],
        "UC3_outliers": uc3["outliers"],
        "UC3_correlation": uc3["corr"].round(3).reset_index().rename(columns={"index": "feature"}),
        **{f"UC4_{k}"[:31]: v for k, v in uc4["queries"].items()},
        **{k[:31]: v for k, v in uc4["views"].items()},
        **{k[:31]: v for k, v in uc4["summaries"].items()},
        "REC_area_hotspots": rec["areas"],
        "REC_beat_hotspots": rec["beats"],
    })
    return sheets


def _img(path):
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def all_charts(results):
    charts = {}
    for key in ("uc2", "uc3", "uc4"):
        charts.update(results[key]["charts"])
    charts["rec_hotspot_map"] = results["rec"]["chart"]
    return charts


def _table(df, n=None):
    return (df.head(n) if n else df).to_html(index=False, classes="table", border=0, na_rep="")


def export_all(results, report_dir=None):
    report_dir = Path(report_dir or config.REPORT_DIR)
    report_dir.mkdir(parents=True, exist_ok=True)
    sheets = _sheets(results)

    xlsx = report_dir / "chicago_crime_report.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)

    csv_dir = report_dir / "csv"
    csv_dir.mkdir(exist_ok=True)
    for name, df in sheets.items():
        df.to_csv(csv_dir / f"{name}.csv", index=False)

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"]))
    uc1 = results.get("uc1")
    html = env.get_template("report.html").render(
        r=results, uc1=uc1, insights=results.get("insights", {}),
        charts={k: _img(v) for k, v in all_charts(results).items()},
        head10=_table(uc1["profile"]["head"]) if uc1 else "",
        tables={
            "anomalies": _table(uc1["anomalies"]) if uc1 else "",
            "top10": _table(results["uc2"]["top10"]),
            "arrest_by_year": _table(results["uc2"]["arrest_by_year"]),
            "top_areas": _table(results["uc2"]["top_areas"]),
            "outliers": _table(results["uc3"]["outliers"]),
            "rec": _table(results["rec"]["top_areas"][["priority", "community_name", "risk_score",
                                                       "crime_count", "arrest_rate_pct", "top_crime",
                                                       "patrol_radius_km", "recommendation"]]),
            **{k: _table(v) for k, v in results["uc4"]["queries"].items()},
            **{k: _table(v) for k, v in results["uc4"]["views"].items()},
        })
    html_path = report_dir / "chicago_crime_report.html"
    html_path.write_text(html, encoding="utf-8")
    return {"excel": xlsx, "html": html_path, "csv_dir": csv_dir}
