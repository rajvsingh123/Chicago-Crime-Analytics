"""Use Case 1 - Load, clean and store Chicago crime data.

Raw files are preserved untouched in staging tables (stg_*), cleaned data is loaded into
the normalised warehouse schema, and any record that cannot satisfy warehouse
constraints is kept in the crime_quarantine table, so no data is ever discarded.
"""
import io
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import bindparam, text

import config
from pipeline import db

CRIME_COLUMNS = ["id", "case_number", "date", "block", "iucr_code", "location_desc", "arrest",
                 "domestic", "beat_num", "district_code", "ward_no", "community_code", "fbi_code",
                 "x_coordinate", "y_coordinate", "year", "date_of_update", "latitude",
                 "longitude", "location"]

DATE_FORMATS = ["%m/%d/%Y", "%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M",
                "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"]

BOOL_MAP = {"TRUE": True, "T": True, "Y": True, "YES": True, "1": True,
            "FALSE": False, "F": False, "N": False, "NO": False, "0": False}


# --------------------------------------------------------------------------- reading
def read_csv_robust(source):
    """Read a CSV (path, text or bytes) as strings, repairing lines with an unterminated quote.

    The supplied crime extract ends with rows whose quoted ``location`` value is never
    closed; a naive parser would merge or drop those rows.
    """
    if isinstance(source, Path) or (isinstance(source, str) and "\n" not in source):
        raw_text = Path(source).read_text(encoding="utf-8-sig", errors="replace")
    else:
        raw_text = source.decode("utf-8-sig", errors="replace") if isinstance(source, bytes) else source
    lines = [ln for ln in raw_text.splitlines() if ln.strip()]
    repaired = 0
    fixed = []
    for ln in lines:
        if ln.count('"') % 2:
            ln += '"'
            repaired += 1
        fixed.append(ln)
    df = pd.read_csv(io.StringIO("\n".join(fixed)), dtype=str, keep_default_na=False,
                     na_values=["", "NA", "N/A", "NULL", "null", "NaN", "nan"])
    df.columns = [c.strip() for c in df.columns]
    df.attrs["repaired_lines"] = repaired
    return df


def load_raw_files(data_dir=None):
    data_dir = Path(data_dir or config.DATA_DIR)
    return {key: read_csv_robust(data_dir / name) for key, name in config.FILES.items()}


# --------------------------------------------------------------------------- profiling
def inspect_dataframe(df, n=10):
    return {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "head": df.head(n),
        "dtypes": df.dtypes.astype(str).rename("dtype").to_frame(),
    }


def missing_percentage(df):
    """Percentage of missing values per column, computed with NumPy."""
    values = df.to_numpy(dtype=object)
    mask = pd.isna(values) | np.char.equal(np.char.strip(values.astype(str)), "")
    pct = np.round(mask.sum(axis=0) / max(len(df), 1) * 100, 2)
    return pd.Series(pct, index=df.columns, name="missing_pct").sort_values(ascending=False)


def columns_above_missing_threshold(missing_pct, threshold=config.MISSING_DROP_THRESHOLD):
    return missing_pct[missing_pct > threshold].index.tolist()


# --------------------------------------------------------------------------- cleaning helpers
def _std_text(s, upper=True):
    s = s.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
    s = s.mask(s == "")
    return s.str.upper() if upper else s


def _to_number(s):
    return pd.to_numeric(s.astype("string").str.replace(",", "", regex=False).str.strip(), errors="coerce")


def _to_int(s):
    return _to_number(s).astype("Int64")


def parse_dates(s):
    s = s.astype("string").str.strip()
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    for fmt in DATE_FORMATS:
        todo = out.isna() & s.notna()
        if not todo.any():
            break
        out[todo] = pd.to_datetime(s[todo], format=fmt, errors="coerce")
    return out


def normalise_iucr(s):
    return _std_text(s).str.zfill(4)


def normalise_fbi(s):
    s = _std_text(s)
    # FBI codes are two-digit with optional suffix, e.g. "6" -> "06", "4B" -> "04B".
    return s.str.replace(r"^(\d)([A-Z]?)$", r"0\1\2", regex=True)


def _to_bool(s):
    return _std_text(s).map(BOOL_MAP)


# --------------------------------------------------------------------------- dimension cleaning
def clean_iucr(raw):
    df = raw.rename(columns=lambda c: c.strip().lower().replace(" ", "_"))
    out = pd.DataFrame({
        "iucr_code": normalise_iucr(df["iucr"]),
        "primary_type": _std_text(df["primary_type"]),
        "description": _std_text(df["description"]),
        "index_code": _std_text(df["index_code"]),
    })
    return out.dropna(subset=["iucr_code"]).drop_duplicates("iucr_code")


def clean_beat(raw):
    df = raw.rename(columns=str.lower)
    out = pd.DataFrame({c: _to_int(df[c]) for c in ["beat_num", "district", "sector", "beat"]})
    return out.dropna(subset=["beat_num"]).drop_duplicates("beat_num")


def clean_district(raw):
    df = raw.rename(columns=str.lower)
    out = pd.DataFrame({
        "district_code": _to_int(df["district_code"]),
        "district_name": _std_text(df["district_name"], upper=False),
        **{c: _std_text(df[c], upper=False) for c in
           ["address", "city", "state", "zip", "website", "phone", "fax", "tty", "location"]},
        **{c: _to_number(df[c]) for c in ["x_coordinate", "y_coordinate", "latitude", "longitude"]},
    })
    return out.dropna(subset=["district_code"]).drop_duplicates("district_code")


def clean_ward(raw):
    df = raw.copy()
    cols = ["alderman", "address", "city", "state", "zipcode", "ward_phone", "ward_fax", "email",
            "website", "location", "city_hall_address", "city_hall_city", "city_hall_state",
            "city_hall_zipcode", "city_hall_phone"]
    out = pd.DataFrame({"ward_no": _to_int(df["ward"]),
                        **{c: _std_text(df[c], upper=False) for c in cols}})
    # The source file lists some wards twice; keep the most complete record per ward.
    out["_filled"] = out.notna().sum(axis=1)
    out = out.sort_values(["ward_no", "_filled"], ascending=[True, False])
    return out.drop(columns="_filled").dropna(subset=["ward_no"]).drop_duplicates("ward_no")


def clean_community(raw):
    out = pd.DataFrame({
        "community_code": _to_int(raw["community_code"]),
        "community_name": _std_text(raw["community_name"], upper=False),
        "population": _to_int(raw["population"]),
        **{c: _to_number(raw[c]) for c in
           ["area_sqmile", "area_sqkm", "density_per_sqmi", "density_per_sqkm"]},
    })
    return out.dropna(subset=["community_code"]).drop_duplicates("community_code")


# --------------------------------------------------------------------------- crime cleaning
def clean_crime(raw):
    """Return (clean_df, quarantine_df, log) for the crime master data."""
    missing = [c for c in CRIME_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"Crime file is missing required columns: {missing}")
    df = raw[CRIME_COLUMNS].copy()
    log = {}

    out = pd.DataFrame(index=df.index)
    out["id"] = _to_int(df["id"])
    out["case_number"] = _std_text(df["case_number"])
    out["date"] = parse_dates(df["date"])
    out["block"] = _std_text(df["block"])
    out["iucr_code"] = normalise_iucr(df["iucr_code"])
    out["location_desc"] = _std_text(df["location_desc"])
    out["arrest"] = _to_bool(df["arrest"])
    out["domestic"] = _to_bool(df["domestic"])
    for c in ["beat_num", "district_code", "ward_no", "community_code"]:
        out[c] = _to_int(df[c])
    out["fbi_code"] = normalise_fbi(df["fbi_code"])
    for c in ["x_coordinate", "y_coordinate", "latitude", "longitude"]:
        out[c] = _to_number(df[c])
    out["year"] = _to_int(df["year"])
    out["date_of_update"] = parse_dates(df["date_of_update"])
    out["location"] = _std_text(df["location"], upper=False)

    log["missing_before"] = out.isna().sum().to_dict()

    # Missing-value handling for key / descriptive fields.
    out["location_desc"] = out["location_desc"].fillna("UNKNOWN")
    out["arrest"] = out["arrest"].fillna(False).astype(bool)
    out["domestic"] = out["domestic"].fillna(False).astype(bool)
    out["year"] = out["year"].fillna(out["date"].dt.year.astype("Int64"))
    no_loc = out["location"].isna() & out["latitude"].notna() & out["longitude"].notna()
    out.loc[no_loc, "location"] = ("(" + out.loc[no_loc, "latitude"].astype(str) + ", "
                                   + out.loc[no_loc, "longitude"].astype(str) + ")")
    # Coordinates cannot be reliably imputed; they stay NULL and are flagged instead.
    out["has_coordinates"] = out[["latitude", "longitude"]].notna().all(axis=1)

    # Feature engineering.
    out["Year"] = out["date"].dt.year
    out["Month"] = out["date"].dt.month
    out["DayOfWeek"] = out["date"].dt.day_name()
    out["Hour"] = out["date"].dt.hour

    # Records that cannot satisfy warehouse constraints are quarantined, never dropped.
    reasons = pd.Series("", index=out.index, dtype="string")
    reasons[out["case_number"].isna()] += "missing case_number;"
    reasons[out["id"].isna()] += "missing id;"
    reasons[out["date"].isna()] += "unparseable date;"
    reasons[out["iucr_code"].isna()] += "missing iucr_code;"
    dup = out["case_number"].notna() & out.sort_values("date_of_update").duplicated(
        "case_number", keep="last").reindex(out.index)
    reasons[dup] += "duplicate case_number (older version);"
    bad = reasons != ""
    quarantine = raw.loc[bad].copy()
    quarantine["reason"] = reasons[bad].str.rstrip(";")
    clean = out.loc[~bad].copy()
    clean["Year"] = clean["Year"].astype(int)
    clean["Month"] = clean["Month"].astype(int)
    clean["Hour"] = clean["Hour"].astype(int)

    log["missing_after"] = clean.isna().sum().to_dict()
    log["quarantined"] = int(bad.sum())
    log["rows_in"] = int(len(raw))
    log["rows_clean"] = int(len(clean))
    log["repaired_lines"] = int(raw.attrs.get("repaired_lines", 0))
    return clean, quarantine, log


def detect_anomalies(clean, raw=None):
    """Identify date-format anomalies and obvious outliers."""
    findings = []
    if raw is not None:
        parsed = parse_dates(raw["date"])
        n_bad = int((parsed.isna() & raw["date"].notna()).sum())
        findings.append(("Unparseable date values", n_bad, "Checked against known CPD date formats"))
        n_time = int(raw["date"].astype("string").str.contains(":", na=False).sum())
        findings.append(("Dates carrying a time component", n_time,
                         "Dates are day-level only; Hour defaults to 0 and hourly analysis is limited"
                         if n_time == 0 else "Time component available"))
    mismatch = clean["year"].notna() & (clean["year"] != clean["Year"])
    findings.append(("'year' column disagrees with date", int(mismatch.sum()), ""))
    late = clean["date_of_update"].notna() & (clean["date_of_update"] < clean["date"])
    findings.append(("Updated before the incident date", int(late.sum()), ""))
    lag_days = (clean["date_of_update"] - clean["date"]).dt.days
    q1, q3 = np.nanpercentile(lag_days, [25, 75])
    upper = q3 + 1.5 * (q3 - q1)
    lag_out = clean.loc[lag_days > upper]
    findings.append(("Reporting-lag outliers (IQR on date_of_update - date)", int(len(lag_out)),
                     f"Incidents from {sorted(lag_out['Year'].unique().tolist())} reported/updated in "
                     f"{sorted(clean['date_of_update'].dt.year.dropna().unique().astype(int).tolist())}; "
                     f"lag > {upper:.0f} days"))
    lat, lon = config.CHICAGO_BOUNDS["lat"], config.CHICAGO_BOUNDS["lon"]
    geo = clean["has_coordinates"] & ~(clean["latitude"].between(*lat) & clean["longitude"].between(*lon))
    findings.append(("Coordinates outside Chicago bounds", int(geo.sum()), ""))
    findings.append(("Records without coordinates", int((~clean["has_coordinates"]).sum()),
                     "Kept with NULL coordinates (excluded only from geo analysis)"))
    return pd.DataFrame(findings, columns=["check", "count", "note"])


def placeholder_dimensions(clean, dims):
    """Add 'UNKNOWN' dimension members for keys referenced by crimes but missing in lookups."""
    dims = {k: v.copy() for k, v in dims.items()}
    specs = [("iucr", "iucr_code", {"primary_type": "UNKNOWN", "description": "UNKNOWN"}),
             ("beat", "beat_num", {}), ("district", "district_code", {"district_name": "Unknown"}),
             ("ward", "ward_no", {}), ("community", "community_code", {"community_name": "Unknown"})]
    added = {}
    for key, col, defaults in specs:
        missing = sorted(set(clean[col].dropna()) - set(dims[key][col].dropna()))
        if missing:
            extra = pd.DataFrame({col: missing, **defaults})
            dims[key] = pd.concat([dims[key], extra], ignore_index=True)
        added[key] = missing
    return dims, added


def clean_all(raws):
    dims = {
        "iucr": clean_iucr(raws["iucr"]),
        "beat": clean_beat(raws["beat"]),
        "district": clean_district(raws["district"]),
        "ward": clean_ward(raws["ward"]),
        "community": clean_community(raws["community"]),
    }
    crime, quarantine, log = clean_crime(raws["crime"])
    dims, added = placeholder_dimensions(crime, dims)
    log["placeholder_dimension_keys"] = added
    return crime, dims, quarantine, log


# --------------------------------------------------------------------------- loading
DIM_TABLE = {"iucr": "iucr", "beat": "police_beat_info", "district": "district_ps_info",
             "ward": "ward_office", "community": "city_community"}


def _crime_rows(clean):
    cols = [c.name for c in db.chicago_crime.columns]
    out = clean.rename(columns={"Month": "month", "DayOfWeek": "day_of_week", "Hour": "hour"})
    for c in cols:
        if c not in out.columns:
            out[c] = None
    return out[cols]


def _to_sql(df, name, engine, if_exists="append"):
    df.to_sql(name, engine, if_exists=if_exists, index=False, chunksize=500)


def write_staging(engine, raws, batch_id, replace):
    loaded_at = datetime.now().isoformat(timespec="seconds")
    for key, raw in raws.items():
        stg = raw.copy().astype(object)
        stg["batch_id"], stg["loaded_at"] = batch_id, loaded_at
        _to_sql(stg, f"stg_{key}", engine, "replace" if replace else "append")


def write_quarantine(engine, quarantine, batch_id, replace):
    q = quarantine.copy().astype(object)
    q["batch_id"] = batch_id
    if replace or len(q):
        _to_sql(q if len(q) else pd.DataFrame(columns=CRIME_COLUMNS + ["reason", "batch_id"]),
                "crime_quarantine", engine, "replace" if replace else "append")


def load_full(engine, crime, dims, quarantine, raws):
    """Full (re)build of the warehouse."""
    batch_id = uuid.uuid4().hex[:12]
    db.reset_schema(engine)
    for key in ["iucr", "beat", "district", "ward", "community"]:
        _to_sql(dims[key], DIM_TABLE[key], engine)
    _to_sql(_crime_rows(crime), "chicago_crime", engine)
    write_staging(engine, raws, batch_id, replace=True)
    write_quarantine(engine, quarantine, batch_id, replace=True)
    db.create_views(engine)
    return batch_id


def _existing_keys(engine, table, col):
    with engine.connect() as conn:
        return {r[0] for r in conn.execute(text(f"SELECT {col} FROM {table}"))}


def load_incremental(engine, raw_crime):
    """Upsert a new batch of crime records (near-real-time ingestion)."""
    batch_id = uuid.uuid4().hex[:12]
    crime, quarantine, log = clean_crime(raw_crime)
    dims = {k: pd.read_sql(f"SELECT * FROM {t}", engine) for k, t in DIM_TABLE.items()}
    full_dims, added = placeholder_dimensions(crime, dims)
    for key, keys in added.items():
        if keys:
            col = {"iucr": "iucr_code", "beat": "beat_num", "district": "district_code",
                   "ward": "ward_no", "community": "community_code"}[key]
            _to_sql(full_dims[key][full_dims[key][col].isin(keys)], DIM_TABLE[key], engine)
    existing = _existing_keys(engine, "chicago_crime", "case_number")
    updates = crime[crime["case_number"].isin(existing)]
    if len(updates):
        stmt = text("DELETE FROM chicago_crime WHERE case_number IN :keys").bindparams(
            bindparam("keys", expanding=True))
        with engine.begin() as conn:
            conn.execute(stmt, {"keys": updates["case_number"].tolist()})
    _to_sql(_crime_rows(crime), "chicago_crime", engine)
    write_staging(engine, {"crime": raw_crime}, batch_id, replace=False)
    write_quarantine(engine, quarantine, batch_id, replace=False)
    log.update({"batch_id": batch_id, "inserted": int(len(crime) - len(updates)),
                "updated": int(len(updates)), "placeholder_dimension_keys": added})
    return log


def run(engine, data_dir=None):
    """Execute Use Case 1 end-to-end and return all artefacts for reporting."""
    raws = load_raw_files(data_dir)
    raw_crime = raws["crime"]
    profile = inspect_dataframe(raw_crime)
    missing_pct = missing_percentage(raw_crime)
    drop_candidates = columns_above_missing_threshold(missing_pct)
    crime, dims, quarantine, log = clean_all(raws)
    # Columns above the threshold are dropped from the analytical frame only; the raw values
    # remain in staging. Key fields are never dropped.
    log["dropped_columns"] = [c for c in drop_candidates if c not in config.KEY_FIELDS]
    crime = crime.drop(columns=log["dropped_columns"], errors="ignore")
    anomalies = detect_anomalies(crime, raw_crime)
    batch_id = load_full(engine, crime, dims, quarantine, raws)
    dims_iucr = dims["iucr"]
    unique_types = crime.merge(dims_iucr, on="iucr_code")["primary_type"].nunique()
    return {
        "profile": profile, "missing_pct": missing_pct, "drop_candidates": drop_candidates,
        "log": log, "anomalies": anomalies, "batch_id": batch_id,
        "unique_crime_types": int(unique_types),
        "unique_iucr_codes": int(crime["iucr_code"].nunique()),
        "dimension_rows": {k: int(len(v)) for k, v in dims.items()},
        "raw_dimension_rows": {k: int(len(v)) for k, v in raws.items() if k != "crime"},
    }
