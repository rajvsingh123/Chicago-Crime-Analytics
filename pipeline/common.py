"""Shared helpers for analysis modules."""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402

import config  # noqa: E402

DAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

sns.set_theme(style="whitegrid", palette="deep")


def load_crime_frame(engine):
    """Read the denormalised crime view from the warehouse into an analysis-ready frame."""
    df = pd.read_sql("SELECT * FROM vw_crime_details", engine)
    df["Date"] = pd.to_datetime(df["date"])
    df["Year"] = df["Date"].dt.year
    df["Month"] = df["Date"].dt.month
    df["DayOfWeek"] = df["Date"].dt.day_name()
    df["Hour"] = df["Date"].dt.hour
    df["Arrest"] = df["arrest"].astype(bool)
    df["Domestic"] = df["domestic"].astype(bool)
    return df


def save_chart(fig, name, chart_dir=None):
    chart_dir = Path(chart_dir or config.CHART_DIR)
    chart_dir.mkdir(parents=True, exist_ok=True)
    path = chart_dir / f"{name}.png"
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
