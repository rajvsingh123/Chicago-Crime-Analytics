"""Use Case 3 - Statistical insights and pattern detection."""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from pipeline.common import DAY_ORDER, save_chart


def crimes_by_hour(df):
    return df.groupby("Hour").size().reindex(range(24), fill_value=0).rename("crime_count")


def community_counts(df, communities=None):
    counts = df.groupby("community_code").size()
    if communities is not None:
        counts = counts.reindex(communities["community_code"], fill_value=0)
        names = communities.set_index("community_code")["community_name"]
    else:
        names = df.drop_duplicates("community_code").set_index("community_code")["community_name"]
    out = counts.rename("crime_count").to_frame()
    out["community_name"] = names.reindex(out.index).values
    return out.reset_index()


def iqr_outliers(counts):
    """Return (stats, outlier_mask) using NumPy for mean / quartiles."""
    values = counts.to_numpy(dtype=float)
    q1, median, q3 = np.percentile(values, [25, 50, 75])
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    stats = {"mean": round(float(np.mean(values)), 2), "median": float(median),
             "std": round(float(np.std(values, ddof=1)), 2), "q1": float(q1), "q3": float(q3),
             "iqr": float(iqr), "lower_fence": float(lower), "upper_fence": float(upper)}
    return stats, (values < lower) | (values > upper)


def correlation_frame(df):
    num = pd.DataFrame({
        "Year": df["Year"], "Month": df["Month"],
        "DayOfWeek": df["DayOfWeek"].map({d: i for i, d in enumerate(DAY_ORDER)}),
        "Hour": df["Hour"], "Arrest": df["Arrest"].astype(int), "Domestic": df["Domestic"].astype(int),
        "IndexCrime": (df["index_code"] == "I").astype(int),
        "District": df["district_code"], "Ward": df["ward_no"], "Community": df["community_code"],
        "Latitude": df["latitude"], "Longitude": df["longitude"],
    })
    constant = [c for c in num.columns if num[c].nunique(dropna=True) <= 1]
    return num.drop(columns=constant).corr(), constant


def run(df, communities=None, chart_dir=None):
    charts = {}
    hourly = crimes_by_hour(df)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(hourly.index, hourly.values, marker="o")
    ax.set(title="Crimes per Hour of Day", xlabel="Hour of day", ylabel="Crimes", xticks=range(24))
    if df["Hour"].nunique() <= 1:
        ax.text(0.5, 0.6, "Source dates carry no time component -\nall incidents recorded at 00:00",
                transform=ax.transAxes, ha="center", color="firebrick")
    charts["uc3_crimes_by_hour"] = save_chart(fig, "uc3_crimes_by_hour", chart_dir)

    comm = community_counts(df, communities)
    stats, mask = iqr_outliers(comm["crime_count"])
    comm["is_outlier"] = mask
    outliers = comm[comm["is_outlier"]].sort_values("crime_count", ascending=False)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), gridspec_kw={"width_ratios": [1, 2]})
    sns.boxplot(y=comm["crime_count"], ax=axes[0], color="#8ecae6")
    axes[0].axhline(stats["upper_fence"], color="red", ls="--", label=f"Upper fence {stats['upper_fence']:.1f}")
    axes[0].axhline(stats["mean"], color="green", ls=":", label=f"Mean {stats['mean']:.1f}")
    axes[0].legend(fontsize=8)
    axes[0].set(title="Crimes per Community Area", ylabel="Crimes")
    for count, names in outliers.groupby("crime_count")["community_name"]:
        axes[0].annotate(", ".join(names), (0, count), xytext=(8, 0),
                         textcoords="offset points", fontsize=8)
    ranked = comm.sort_values("crime_count", ascending=False).head(25)
    sns.barplot(data=ranked, x="community_name", y="crime_count", hue="is_outlier",
                palette={True: "#d62828", False: "#8ecae6"}, ax=axes[1], dodge=False)
    axes[1].axhline(stats["upper_fence"], color="red", ls="--")
    axes[1].set(title="Top 25 Community Areas (red = IQR outlier)", xlabel="", ylabel="Crimes")
    axes[1].tick_params(axis="x", rotation=75, labelsize=8)
    charts["uc3_community_outliers"] = save_chart(fig, "uc3_community_outliers", chart_dir)

    corr, constant = correlation_frame(df)
    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", center=0, vmin=-1, vmax=1, ax=ax)
    ax.set_title("Correlation Matrix of Numeric Crime Features")
    charts["uc3_correlation_heatmap"] = save_chart(fig, "uc3_correlation_heatmap", chart_dir)

    pairs = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1)).stack()
    strongest = pairs.reindex(pairs.abs().sort_values(ascending=False).index).head(5)
    return {"charts": charts, "hourly": hourly, "community_counts": comm, "iqr_stats": stats,
            "outliers": outliers, "corr": corr, "constant_features": constant,
            "strongest_correlations": strongest.round(3).rename("r").reset_index()
            .rename(columns={"level_0": "feature_a", "level_1": "feature_b"})}
