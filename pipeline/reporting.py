"""Use Case 4 - Warehouse reporting & integration.

Summary tables are created and loaded through the raw DB-API connector
(MySQL Connector/Python when running on MySQL, sqlite3 otherwise).
"""
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from pipeline import db
from pipeline.common import save_chart

QUERIES = {
    "crime_count_per_year": """
        SELECT year, COUNT(*) AS crime_count
        FROM chicago_crime
        GROUP BY year
        ORDER BY year""",
    "top5_crime_types": """
        SELECT i.primary_type,
               COUNT(*) AS crime_count,
               ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM chicago_crime), 2) AS crime_pct
        FROM chicago_crime c
        JOIN iucr i ON c.iucr_code = i.iucr_code
        GROUP BY i.primary_type
        ORDER BY crime_count DESC
        LIMIT 5""",
    "arrest_count_per_year": """
        SELECT year, SUM(CASE WHEN arrest THEN 1 ELSE 0 END) AS arrest_count, COUNT(*) AS crime_count
        FROM chicago_crime
        GROUP BY year
        ORDER BY year""",
}

SUMMARY_TABLES = {
    "summary_crime_yearly": {
        "ddl": """CREATE TABLE summary_crime_yearly (
                    year INT PRIMARY KEY,
                    crime_count INT NOT NULL,
                    arrest_count INT NOT NULL,
                    domestic_count INT NOT NULL,
                    arrest_rate_pct DECIMAL(6,2))""",
        "select": """SELECT year, COUNT(*),
                        SUM(CASE WHEN arrest THEN 1 ELSE 0 END),
                        SUM(CASE WHEN domestic THEN 1 ELSE 0 END),
                        ROUND(100.0 * SUM(CASE WHEN arrest THEN 1 ELSE 0 END) / COUNT(*), 2)
                     FROM chicago_crime GROUP BY year""",
    },
    "summary_crime_by_category": {
        "ddl": """CREATE TABLE summary_crime_by_category (
                    primary_type VARCHAR(64) PRIMARY KEY,
                    crime_count INT NOT NULL,
                    crime_pct DECIMAL(6,2),
                    arrest_count INT NOT NULL,
                    arrest_rate_pct DECIMAL(6,2))""",
        "select": """SELECT i.primary_type, COUNT(*),
                        ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM chicago_crime), 2),
                        SUM(CASE WHEN c.arrest THEN 1 ELSE 0 END),
                        ROUND(100.0 * SUM(CASE WHEN c.arrest THEN 1 ELSE 0 END) / COUNT(*), 2)
                     FROM chicago_crime c JOIN iucr i ON c.iucr_code = i.iucr_code
                     GROUP BY i.primary_type""",
    },
    "summary_community_area": {
        "ddl": """CREATE TABLE summary_community_area (
                    community_code INT PRIMARY KEY,
                    community_name VARCHAR(64),
                    population INT,
                    crime_count INT NOT NULL,
                    arrest_count INT NOT NULL,
                    crimes_per_10k DECIMAL(10,2))""",
        "select": """SELECT cc.community_code, cc.community_name, cc.population, COUNT(c.case_number),
                        SUM(CASE WHEN c.arrest THEN 1 ELSE 0 END),
                        ROUND(10000.0 * COUNT(c.case_number) / NULLIF(cc.population, 0), 2)
                     FROM city_community cc
                     LEFT JOIN chicago_crime c ON c.community_code = cc.community_code
                     GROUP BY cc.community_code, cc.community_name, cc.population""",
    },
    "summary_district": {
        "ddl": """CREATE TABLE summary_district (
                    district_code INT PRIMARY KEY,
                    district_name VARCHAR(64),
                    crime_count INT NOT NULL,
                    arrest_count INT NOT NULL,
                    domestic_count INT NOT NULL)""",
        "select": """SELECT d.district_code, d.district_name, COUNT(c.case_number),
                        SUM(CASE WHEN c.arrest THEN 1 ELSE 0 END),
                        SUM(CASE WHEN c.domestic THEN 1 ELSE 0 END)
                     FROM district_ps_info d
                     LEFT JOIN chicago_crime c ON c.district_code = d.district_code
                     GROUP BY d.district_code, d.district_name""",
    },
}


def build_summary_tables(engine):
    """Create and populate summary tables using the DB-API cursor."""
    ph = db.placeholder(engine)
    conn = engine.raw_connection()
    loaded = {}
    try:
        cur = conn.cursor()
        for name, spec in SUMMARY_TABLES.items():
            cur.execute(f"DROP TABLE IF EXISTS {name}")
            cur.execute(spec["ddl"])
            cur.execute(spec["select"])
            rows = [tuple(r) for r in cur.fetchall()]
            if rows:
                marks = ", ".join([ph] * len(rows[0]))
                cur.executemany(f"INSERT INTO {name} VALUES ({marks})", rows)
            loaded[name] = len(rows)
        conn.commit()
        cur.close()
    finally:
        conn.close()
    return loaded


def run_queries(engine):
    return {name: pd.read_sql(sql, engine) for name, sql in QUERIES.items()}


def read_views(engine):
    return {
        "vw_crime_yearly": pd.read_sql("SELECT * FROM vw_crime_yearly ORDER BY year", engine),
        "vw_crime_by_category": pd.read_sql(
            "SELECT * FROM vw_crime_by_category ORDER BY crime_count DESC", engine),
    }


def run(engine, chart_dir=None):
    db.create_views(engine)
    loaded = build_summary_tables(engine)
    queries = run_queries(engine)
    views = read_views(engine)
    charts = {}

    yearly = views["vw_crime_yearly"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    x = range(len(yearly))
    ax.bar([i - 0.2 for i in x], yearly["crime_count"], width=0.4, label="Crimes", color="#457b9d")
    ax.bar([i + 0.2 for i in x], yearly["arrest_count"], width=0.4, label="Arrests", color="#e63946")
    ax.set_xticks(list(x), yearly["year"].astype(str))
    ax.set(title="vw_crime_yearly: Crimes vs Arrests per Year", ylabel="Count", xlabel="Year")
    ax.legend()
    charts["uc4_vw_crime_yearly"] = save_chart(fig, "uc4_vw_crime_yearly", chart_dir)

    top5 = queries["top5_crime_types"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].pie(top5["crime_pct"], labels=top5["primary_type"], autopct="%1.1f%%", startangle=140)
    axes[0].set_title("Top 5 Crime Types (share of all crimes)")
    cat = views["vw_crime_by_category"]
    sns.barplot(data=cat, y="primary_type", x="crime_count", ax=axes[1], color="#a8dadc")
    sns.barplot(data=cat, y="primary_type", x="arrest_count", ax=axes[1], color="#1d3557")
    axes[1].set(title="vw_crime_by_category: Crimes (light) vs Arrests (dark)", xlabel="Count", ylabel="")
    axes[1].tick_params(axis="y", labelsize=7)
    charts["uc4_vw_crime_by_category"] = save_chart(fig, "uc4_vw_crime_by_category", chart_dir)

    summaries = {name: pd.read_sql(f"SELECT * FROM {name}", engine) for name in SUMMARY_TABLES}
    district = summaries["summary_district"].sort_values("crime_count", ascending=False)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    sns.barplot(data=district, x="district_name", y="crime_count", ax=ax, color="#f4a261")
    ax.tick_params(axis="x", rotation=60)
    ax.set(title="summary_district: Crimes per Police District", xlabel="", ylabel="Crimes")
    charts["uc4_summary_district"] = save_chart(fig, "uc4_summary_district", chart_dir)

    return {"charts": charts, "summary_rows": loaded, "queries": queries, "views": views,
            "summaries": summaries}
