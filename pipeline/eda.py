"""Use Case 2 - Exploratory analysis and visualisation of crime."""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from pipeline.common import DAY_ORDER, MONTH_NAMES, save_chart


def crimes_per_year(df):
    return df.groupby("Year").size().rename("crime_count").reset_index()


def trend_direction(yearly):
    if len(yearly) < 2:
        return "insufficient data (single year)"
    slope = np.polyfit(yearly["Year"], yearly["crime_count"], 1)[0]
    return "rising" if slope > 0 else "decreasing" if slope < 0 else "flat"


def top_categories(df, n=10):
    counts = df["primary_type"].value_counts()
    out = counts.rename("crime_count").to_frame()
    out["percentage"] = np.round(counts / counts.sum() * 100, 2)
    return out.head(n).reset_index().rename(columns={"index": "primary_type"})


def arrest_rate(df):
    return round(float(df["Arrest"].mean() * 100), 2)


def arrest_rate_by_year(df):
    g = df.groupby("Year")["Arrest"].agg(crimes="size", arrests="sum")
    g["arrest_rate_pct"] = np.round(g["arrests"] / g["crimes"] * 100, 2)
    return g.reset_index()


def month_day_pivot(df):
    pivot = df.pivot_table(index="Month", columns="DayOfWeek", values="case_number",
                           aggfunc="count", fill_value=0)
    pivot = pivot.reindex(columns=[d for d in DAY_ORDER if d in pivot.columns])
    pivot.index = [MONTH_NAMES[m - 1] for m in pivot.index]
    return pivot


def top_community_areas(df, n=10):
    out = (df.groupby(["community_code", "community_name"]).size().rename("crime_count")
           .sort_values(ascending=False).head(n).reset_index())
    out["percentage"] = np.round(out["crime_count"] / len(df) * 100, 2)
    return out


def run(df, chart_dir=None):
    charts = {}
    yearly = crimes_per_year(df)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(yearly["Year"], yearly["crime_count"], marker="o", linewidth=2)
    for x, y in zip(yearly["Year"], yearly["crime_count"]):
        ax.annotate(str(y), (x, y), textcoords="offset points", xytext=(0, 6), ha="center")
    ax.set(title="Total Crimes per Year", xlabel="Year", ylabel="Number of crimes")
    ax.set_xticks(yearly["Year"])
    charts["uc2_crimes_per_year"] = save_chart(fig, "uc2_crimes_per_year", chart_dir)

    top10 = top_categories(df)
    fig, ax = plt.subplots(figsize=(9, 5))
    sns.barplot(data=top10, y="primary_type", x="crime_count", ax=ax, hue="primary_type", legend=False)
    for i, (c, p) in enumerate(zip(top10["crime_count"], top10["percentage"])):
        ax.text(c, i, f" {c} ({p}%)", va="center")
    ax.set(title="Top 10 Crime Categories (Primary Type)", xlabel="Crimes", ylabel="")
    ax.set_xlim(0, top10["crime_count"].max() * 1.25)
    charts["uc2_top10_categories"] = save_chart(fig, "uc2_top10_categories", chart_dir)

    rate = arrest_rate(df)
    by_year = arrest_rate_by_year(df)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    axes[0].pie([df["Arrest"].sum(), (~df["Arrest"]).sum()], labels=["Arrest", "No arrest"],
                autopct="%1.1f%%", startangle=90, colors=["#2a9d8f", "#e76f51"])
    axes[0].set_title("Crimes Resulting in Arrest")
    sns.barplot(data=by_year, x="Year", y="arrest_rate_pct", ax=axes[1], color="#2a9d8f")
    for i, (r, n) in enumerate(zip(by_year["arrest_rate_pct"], by_year["crimes"])):
        axes[1].text(i, r, f"{r}%\n(n={n})", ha="center", va="bottom", fontsize=8)
    axes[1].set(title="Arrest Rate by Year", ylabel="Arrest rate (%)", ylim=(0, 115))
    charts["uc2_arrests"] = save_chart(fig, "uc2_arrests", chart_dir)

    pivot = month_day_pivot(df)
    fig, ax = plt.subplots(figsize=(9, 5))
    sns.heatmap(pivot, annot=True, fmt="d", cmap="Reds", ax=ax, linewidths=0.5)
    ax.set(title="Crime Frequency: Month vs Day of Week", xlabel="Day of week", ylabel="Month")
    charts["uc2_month_day_heatmap"] = save_chart(fig, "uc2_month_day_heatmap", chart_dir)

    top_areas = top_community_areas(df)
    fig, ax = plt.subplots(figsize=(9, 5))
    sns.barplot(data=top_areas, y="community_name", x="crime_count", ax=ax, hue="community_name",
                legend=False, palette="rocket")
    ax.set(title="Top 10 Community Areas by Crime Count", xlabel="Crimes", ylabel="")
    charts["uc2_top10_community_areas"] = save_chart(fig, "uc2_top10_community_areas", chart_dir)

    month_counts = df.groupby("Month").size()
    peak_month = int(month_counts.idxmax())
    rates = by_year.set_index("Year")["arrest_rate_pct"]
    big_years = by_year[by_year["crimes"] >= 30]
    answers = {
        "trend": trend_direction(yearly),
        "most_frequent_category": top10.iloc[0]["primary_type"],
        "most_frequent_category_pct": float(top10.iloc[0]["percentage"]),
        "arrest_rate_pct": rate,
        "arrest_rate_consistent": bool(rates.std() < 10) if len(rates) > 1 else True,
        "arrest_rate_std": round(float(rates.std()), 2) if len(rates) > 1 else 0.0,
        "arrest_rate_reliable_years": big_years["Year"].tolist(),
        "peak_month": MONTH_NAMES[peak_month - 1],
        "peak_month_count": int(month_counts.max()),
    }
    return {"charts": charts, "yearly": yearly, "top10": top10, "arrest_by_year": by_year,
            "month_day": pivot, "top_areas": top_areas, "answers": answers}
