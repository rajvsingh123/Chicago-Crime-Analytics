import pandas as pd
import pytest
from sqlalchemy import text

import config
from pipeline import db, ingest, runner


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("run")
    config.CHART_DIR = tmp / "charts"
    config.REPORT_DIR = tmp / "reports"
    runner._SNAPSHOT = tmp / "uc1.pkl"
    engine = db.get_engine(f"sqlite:///{(tmp / 'test.db').as_posix()}")
    return engine, runner.run_all(engine)


def test_read_csv_repairs_unterminated_quotes():
    csv = 'a,b\n1,"(1, 2)"\n2,"(3, 4)\n3,"(5, 6)\n'
    df = ingest.read_csv_robust(csv)
    assert len(df) == 3
    assert df["b"].tolist() == ["(1, 2)", "(3, 4)", "(5, 6)"]
    assert df.attrs["repaired_lines"] == 2


def test_code_normalisation():
    assert ingest.normalise_iucr(pd.Series([" 486", "41a", "0820"])).tolist() == ["0486", "041A", "0820"]
    assert ingest.normalise_fbi(pd.Series(["6", "4b", "08B", "24"])).tolist() == ["06", "04B", "08B", "24"]


def test_full_build_keeps_every_record(built):
    engine, res = built
    with engine.connect() as conn:
        crimes = conn.execute(text("SELECT COUNT(*) FROM chicago_crime")).scalar()
        staged = conn.execute(text("SELECT COUNT(*) FROM stg_crime")).scalar()
        wards = conn.execute(text("SELECT COUNT(*) FROM ward_office")).scalar()
        yearly = conn.execute(text("SELECT SUM(crime_count) FROM vw_crime_yearly")).scalar()
    assert crimes == staged == yearly == 498
    assert wards == 50  # duplicate ward rows collapsed for the PK, raw copies kept in staging
    assert res["uc1"]["unique_crime_types"] == 23
    assert res["exports"]["excel"].exists() and res["exports"]["html"].exists()


def test_incremental_upsert_and_quarantine(built):
    engine, _ = built
    raw = ingest.read_csv_robust(config.DATA_DIR / config.FILES["crime"]).head(2).copy()
    raw.loc[0, "arrest"] = "TRUE" if raw.loc[0, "arrest"] == "FALSE" else "FALSE"  # update
    raw.loc[1, ["id", "case_number"]] = ["99999999", "ZZ000001"]  # new
    bad = raw.iloc[[1]].assign(case_number="ZZ000002", date="not-a-date")
    res = runner.ingest_batch(pd.concat([raw, bad], ignore_index=True), engine)
    log = res["batch_log"]
    assert (log["inserted"], log["updated"], log["quarantined"]) == (1, 1, 1)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM chicago_crime")).scalar() == 499
        assert conn.execute(text(
            "SELECT COUNT(*) FROM crime_quarantine WHERE case_number = 'ZZ000002'")).scalar() == 1


def test_web_routes(built, monkeypatch):
    import app as webapp
    engine, res = built
    webapp.STATE.update(engine=engine, results=res)
    client = webapp.app.test_client()
    for path in ["/", "/sql", "/data?primary_type=THEFT", "/ingest", "/api/summary",
                 "/api/recommendations", "/download/excel"]:
        assert client.get(path).status_code == 200, path
