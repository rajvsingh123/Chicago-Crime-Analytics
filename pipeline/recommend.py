"""Near-real-time crime-prevention recommendations.

Each incident gets a risk weight = severity x recency decay. Weights are aggregated per
community area and police beat to rank hotspots, and a patrol perimeter (centroid +
radius covering 90% of geolocated incidents) is derived for every hotspot.
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Circle

from pipeline.common import save_chart

HALF_LIFE_DAYS = 30
VIOLENT = {"HOMICIDE", "CRIM SEXUAL ASSAULT", "CRIMINAL SEXUAL ASSAULT", "ROBBERY", "ASSAULT",
           "BATTERY", "WEAPONS VIOLATION", "KIDNAPPING", "HUMAN TRAFFICKING", "ARSON"}
EARTH_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_KM * np.arcsin(np.sqrt(a))


def risk_weights(df, as_of=None):
    as_of = pd.Timestamp(as_of) if as_of is not None else df["Date"].max()
    age = (as_of - df["Date"]).dt.days.clip(lower=0)
    recency = np.power(0.5, age / HALF_LIFE_DAYS)
    severity = np.where(df["index_code"] == "I", 2.0, 1.0) * np.where(
        df["primary_type"].isin(VIOLENT), 1.5, 1.0)
    return pd.Series(recency * severity, index=df.index), as_of


def _perimeter(group):
    geo = group.dropna(subset=["latitude", "longitude"])
    if geo.empty:
        return pd.Series({"center_lat": np.nan, "center_lon": np.nan, "patrol_radius_km": np.nan})
    lat, lon = geo["latitude"].mean(), geo["longitude"].mean()
    dist = haversine_km(lat, lon, geo["latitude"].to_numpy(), geo["longitude"].to_numpy())
    return pd.Series({"center_lat": round(lat, 6), "center_lon": round(lon, 6),
                      "patrol_radius_km": round(max(float(np.percentile(dist, 90)), 0.3), 2)})


def _hotspots(df, keys):
    g = df.groupby(keys)
    out = g.agg(risk_score=("risk", "sum"), crime_count=("case_number", "size"),
                arrests=("Arrest", "sum"), recent_7d=("recent", "sum"),
                violent=("is_violent", "sum"))
    out["arrest_rate_pct"] = (out["arrests"] / out["crime_count"] * 100).round(1)
    out["top_crime"] = g["primary_type"].agg(lambda s: s.value_counts().index[0])
    out["peak_day"] = g["DayOfWeek"].agg(lambda s: s.value_counts().index[0])
    out["beats"] = g["beat_num"].agg(lambda s: ", ".join(map(str, s.value_counts().index[:3])))
    perim = df.groupby(keys)[["latitude", "longitude"]].apply(_perimeter)
    out = out.join(perim).sort_values("risk_score", ascending=False)
    out["risk_score"] = out["risk_score"].round(2)
    q1, q3 = np.percentile(out["risk_score"], [25, 75])
    fence = q3 + 1.5 * (q3 - q1)
    rank = np.arange(1, len(out) + 1)
    out["priority"] = np.select([(out["risk_score"] > fence) | (rank <= 3), rank <= 10],
                                ["HIGH", "MEDIUM"], "LOW")
    return out.reset_index()


def _advice(r):
    parts = [f"Increase patrols in {r['community_name']} (beats {r['beats']}), especially on "
             f"{r['peak_day']}s; focus on {r['top_crime'].title()}."]
    if pd.notna(r["patrol_radius_km"]):
        parts.append(f"Set a {r['patrol_radius_km']} km patrol perimeter around "
                     f"({r['center_lat']:.4f}, {r['center_lon']:.4f}).")
    if r["arrest_rate_pct"] < 20:
        parts.append(f"Low arrest rate ({r['arrest_rate_pct']}%) - add investigative follow-up.")
    if r["violent"] >= max(3, 0.4 * r["crime_count"]):
        parts.append("High share of violent crime - deploy tactical units.")
    return " ".join(parts)


def recommend(df, as_of=None, top_n=10):
    df = df.copy()
    df["risk"], as_of = risk_weights(df, as_of)
    df["recent"] = (as_of - df["Date"]).dt.days.between(0, 7)
    df["is_violent"] = df["primary_type"].isin(VIOLENT)
    areas = _hotspots(df, ["community_code", "community_name"])
    areas["recommendation"] = areas.apply(_advice, axis=1)
    beats = _hotspots(df, ["beat_num", "district_code"]).drop(columns="beats")
    return {"as_of": as_of, "areas": areas, "top_areas": areas.head(top_n), "beats": beats.head(top_n)}


def hotspot_map(df, rec, chart_dir=None):
    geo = df.dropna(subset=["latitude", "longitude"])
    fig, ax = plt.subplots(figsize=(7, 9))
    ax.scatter(geo["longitude"], geo["latitude"], s=8, alpha=0.35, c="grey", label="Incidents")
    colors = {"HIGH": "#d62828", "MEDIUM": "#f77f00", "LOW": "#4361ee"}
    for _, r in rec["top_areas"].dropna(subset=["center_lat"]).iterrows():
        km_per_deg_lon = 111.32 * np.cos(np.radians(r["center_lat"]))
        ax.add_patch(Circle((r["center_lon"], r["center_lat"]), r["patrol_radius_km"] / km_per_deg_lon,
                            fill=False, lw=2, color=colors[r["priority"]]))
        ax.annotate(r["community_name"], (r["center_lon"], r["center_lat"]), fontsize=8,
                    ha="center", weight="bold")
    ax.set_aspect(1 / np.cos(np.radians(41.85)))
    ax.set(title="Patrol Hotspots & Perimeters (top 10 community areas)\nred=HIGH, orange=MEDIUM",
           xlabel="Longitude", ylabel="Latitude")
    return save_chart(fig, "rec_hotspot_map", chart_dir)
