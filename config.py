"""Central configuration for the Chicago Crime Analytics pipeline.

The warehouse defaults to SQLite (per the brief: "In case MySQL is not available use
SQLite3"). To use MySQL set the CRIME_DB_URL environment variable, e.g.

    set CRIME_DB_URL=mysql+mysqlconnector://<user>:<password>@localhost:3306/chicago_crime

The database is created automatically if it does not exist.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("CRIME_DATA_DIR", BASE_DIR / "data" / "raw"))
INCOMING_DIR = Path(os.getenv("CRIME_INCOMING_DIR", BASE_DIR / "data" / "incoming"))
OUTPUT_DIR = Path(os.getenv("CRIME_OUTPUT_DIR", BASE_DIR / "outputs"))
CHART_DIR = OUTPUT_DIR / "charts"
REPORT_DIR = OUTPUT_DIR / "reports"

DB_URL = os.getenv("CRIME_DB_URL", f"sqlite:///{(BASE_DIR / 'data' / 'chicago_crime.db').as_posix()}")

FILES = {
    "crime": "chicago_crime_dataset.csv",
    "iucr": "iucr_codes.csv",
    "ward": "chicago_ward_offices.csv",
    "beat": "chicago_police_beat_info.csv",
    "district": "chicago_district_ps_info.csv",
    "community": "chicago_city_community.csv",
}

# Columns whose missing values must be handled during cleaning.
KEY_FIELDS = ["id", "case_number", "date", "iucr_code", "beat_num", "district_code",
              "ward_no", "community_code", "arrest", "domestic"]

MISSING_DROP_THRESHOLD = 50.0  # percent

# Approximate bounding box of the City of Chicago, used for outlier detection.
CHICAGO_BOUNDS = {"lat": (41.64, 42.03), "lon": (-87.95, -87.52)}
