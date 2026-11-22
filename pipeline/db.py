"""Database layer: engine creation and the warehouse schema (MySQL or SQLite)."""
from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer, MetaData,
                        String, Table, create_engine, event, text)
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateTable

import config

metadata = MetaData()

iucr = Table(
    "iucr", metadata,
    Column("iucr_code", String(4), primary_key=True),
    Column("primary_type", String(64), nullable=False),
    Column("description", String(128)),
    Column("index_code", String(1)),
)

police_beat_info = Table(
    "police_beat_info", metadata,
    Column("beat_num", Integer, primary_key=True, autoincrement=False),
    Column("district", Integer),
    Column("sector", Integer),
    Column("beat", Integer),
)

district_ps_info = Table(
    "district_ps_info", metadata,
    Column("district_code", Integer, primary_key=True, autoincrement=False),
    Column("district_name", String(64)),
    Column("address", String(128)),
    Column("city", String(64)),
    Column("state", String(8)),
    Column("zip", String(10)),
    Column("website", String(255)),
    Column("phone", String(32)),
    Column("fax", String(32)),
    Column("tty", String(32)),
    Column("x_coordinate", Float),
    Column("y_coordinate", Float),
    Column("latitude", Float),
    Column("longitude", Float),
    Column("location", String(64)),
)

ward_office = Table(
    "ward_office", metadata,
    Column("ward_no", Integer, primary_key=True, autoincrement=False),
    Column("alderman", String(128)),
    Column("address", String(255)),
    Column("city", String(64)),
    Column("state", String(8)),
    Column("zipcode", String(10)),
    Column("ward_phone", String(64)),
    Column("ward_fax", String(64)),
    Column("email", String(128)),
    Column("website", String(255)),
    Column("location", String(128)),
    Column("city_hall_address", String(255)),
    Column("city_hall_city", String(64)),
    Column("city_hall_state", String(8)),
    Column("city_hall_zipcode", String(10)),
    Column("city_hall_phone", String(64)),
)

city_community = Table(
    "city_community", metadata,
    Column("community_code", Integer, primary_key=True, autoincrement=False),
    Column("community_name", String(64), nullable=False),
    Column("population", Integer),
    Column("area_sqmile", Float),
    Column("area_sqkm", Float),
    Column("density_per_sqmi", Float),
    Column("density_per_sqkm", Float),
)

chicago_crime = Table(
    "chicago_crime", metadata,
    Column("id", Integer, nullable=False, unique=True),
    Column("case_number", String(16), primary_key=True),
    Column("date", DateTime, nullable=False),
    Column("block", String(128)),
    Column("iucr_code", String(4), ForeignKey("iucr.iucr_code"), nullable=False),
    Column("location_desc", String(128)),
    Column("arrest", Boolean, nullable=False),
    Column("domestic", Boolean, nullable=False),
    Column("beat_num", Integer, ForeignKey("police_beat_info.beat_num")),
    Column("district_code", Integer, ForeignKey("district_ps_info.district_code")),
    Column("ward_no", Integer, ForeignKey("ward_office.ward_no")),
    Column("community_code", Integer, ForeignKey("city_community.community_code")),
    Column("fbi_code", String(4)),
    Column("x_coordinate", Float),
    Column("y_coordinate", Float),
    Column("year", Integer, nullable=False),
    Column("month", Integer, nullable=False),
    Column("day_of_week", String(10), nullable=False),
    Column("hour", Integer, nullable=False),
    Column("date_of_update", DateTime),
    Column("latitude", Float),
    Column("longitude", Float),
    Column("location", String(64)),
)

# Load order respects foreign keys (dimensions first).
CORE_TABLES = [iucr, police_beat_info, district_ps_info, ward_office, city_community, chicago_crime]

VIEW_DDL = {
    "vw_crime_details": """
        CREATE VIEW vw_crime_details AS
        SELECT c.*, i.primary_type, i.description, i.index_code,
               cc.community_name, d.district_name
        FROM chicago_crime c
        JOIN iucr i ON c.iucr_code = i.iucr_code
        LEFT JOIN city_community cc ON c.community_code = cc.community_code
        LEFT JOIN district_ps_info d ON c.district_code = d.district_code""",
    "vw_crime_yearly": """
        CREATE VIEW vw_crime_yearly AS
        SELECT year,
               COUNT(*) AS crime_count,
               SUM(CASE WHEN arrest THEN 1 ELSE 0 END) AS arrest_count,
               ROUND(100.0 * SUM(CASE WHEN arrest THEN 1 ELSE 0 END) / COUNT(*), 2) AS arrest_rate_pct
        FROM chicago_crime
        GROUP BY year""",
    "vw_crime_by_category": """
        CREATE VIEW vw_crime_by_category AS
        SELECT i.primary_type,
               COUNT(*) AS crime_count,
               ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM chicago_crime), 2) AS crime_pct,
               SUM(CASE WHEN c.arrest THEN 1 ELSE 0 END) AS arrest_count
        FROM chicago_crime c
        JOIN iucr i ON c.iucr_code = i.iucr_code
        GROUP BY i.primary_type""",
}


def _ensure_mysql_database(url):
    server_url = url.set(database=None)
    eng = create_engine(server_url)
    with eng.begin() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{url.database}` "
                          "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
    eng.dispose()


def get_engine(db_url=None):
    url = make_url(db_url or config.DB_URL)
    if url.get_backend_name() == "mysql":
        _ensure_mysql_database(url)
        return create_engine(url, pool_pre_ping=True)
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return engine


def is_mysql(engine):
    return engine.dialect.name == "mysql"


def placeholder(engine):
    """DB-API parameter marker: %s for MySQL Connector, ? for sqlite3."""
    return "%s" if is_mysql(engine) else "?"


def drop_views(engine):
    with engine.begin() as conn:
        for name in VIEW_DDL:
            conn.execute(text(f"DROP VIEW IF EXISTS {name}"))


def create_views(engine):
    drop_views(engine)
    with engine.begin() as conn:
        for ddl in VIEW_DDL.values():
            conn.execute(text(ddl))


def reset_schema(engine):
    drop_views(engine)
    metadata.drop_all(engine)
    metadata.create_all(engine)


def mysql_ddl():
    """Render the warehouse DDL for MySQL (written to sql/schema_mysql.sql)."""
    from sqlalchemy.dialects import mysql
    parts = [str(CreateTable(t).compile(dialect=mysql.dialect())).strip() + ";" for t in CORE_TABLES]
    parts += [v.strip() + ";" for v in VIEW_DDL.values()]
    return "\n\n".join(parts) + "\n"
