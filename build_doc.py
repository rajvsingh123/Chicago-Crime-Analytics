"""Build the case-study submission Word document using only the Python standard library."""
import struct
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path("/root/Chicago-Crime-Analytics")
CHARTS = REPO / "outputs" / "charts"
SHOTS = Path("/tmp/shots")
OUT = Path("/root/.copilot/session-state/d918bc70fc564991b557dfc0e4e7ed4e/files/Chicago_Crime_Case_Study_Submission.docx")
REPO_URL = "https://github.com/rajvsingh123/Chicago-Crime-Analytics"

body, media, rels = [], [], []


def run(text, bold=False, italic=False, color=None, size=None):
    props = ""
    if bold:
        props += "<w:b/>"
    if italic:
        props += "<w:i/>"
    if color:
        props += f'<w:color w:val="{color}"/>'
    if size:
        props += f'<w:sz w:val="{size}"/>'
    rpr = f"<w:rPr>{props}</w:rPr>" if props else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def para(parts, style=None, align=None, page_break_before=False):
    if isinstance(parts, str):
        parts = [run(parts)]
    ppr = ""
    if style:
        ppr += f'<w:pStyle w:val="{style}"/>'
    if page_break_before:
        ppr += "<w:pageBreakBefore/>"
    if align:
        ppr += f'<w:jc w:val="{align}"/>'
    body.append(f"<w:p><w:pPr>{ppr}</w:pPr>{''.join(parts)}</w:p>")


def heading(text, level=1, new_page=False):
    para([run(text)], style=f"Heading{level}", page_break_before=new_page)


def bullet(text, bold_prefix=None):
    parts = [run(bold_prefix, bold=True)] if bold_prefix else []
    parts.append(run(text))
    para(parts, style="ListBullet")


def qa(question, answer):
    para([run("Q: ", bold=True, color="0B2545"), run(question, bold=True)], style="Question")
    para([run("Insight: ", bold=True, color="E63946"), run(answer)], style="Answer")


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def image(path, caption=None, max_width_in=6.3):
    path = Path(path)
    idx = len(media) + 1
    rid = f"rIdImg{idx}"
    name = f"image{idx}.png"
    media.append((name, path.read_bytes()))
    rels.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>')
    w, h = png_size(path)
    width_in = min(max_width_in, w / 110)
    cx = int(width_in * 914400)
    cy = int(cx * h / w)
    max_cy = int(8.4 * 914400)
    if cy > max_cy:
        cx, cy = int(cx * max_cy / cy), max_cy
    body.append(f"""<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:drawing>
<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{idx}" name="Picture {idx}"/>
<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>
<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:pic><pic:nvPicPr><pic:cNvPr id="{idx}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>""")
    if caption:
        para([run(caption, italic=True)], style="Caption", align="center")


STATUS_COLORS = {"Met": "D8F3DC", "Partially met": "FFF3BF", "Not met": "FFE5E5", "Pending": "E7ECF5"}


def table(header, rows, widths=None, status_col=None):
    widths = widths or [int(9000 / len(header))] * len(header)
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)

    def cell(text, w, head=False, fill=None):
        shade = f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else ""
        paras = "".join(
            f'<w:p><w:pPr><w:spacing w:before="20" w:after="20"/></w:pPr>{run(line, bold=head, color="FFFFFF" if head else None, size=18)}</w:p>'
            for line in str(text).split("\n"))
        return f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/>{shade}</w:tcPr>{paras}</w:tc>'

    xml = [f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr><w:tblGrid>{grid}</w:tblGrid>']
    xml.append('<w:tr><w:trPr><w:tblHeader/></w:trPr>' + "".join(cell(h, w, True, "13315C") for h, w in zip(header, widths)) + "</w:tr>")
    for r in rows:
        cells = []
        for i, (v, w) in enumerate(zip(r, widths)):
            fill = STATUS_COLORS.get(v) if i == status_col else None
            cells.append(cell(v, w, fill=fill))
        xml.append("<w:tr>" + "".join(cells) + "</w:tr>")
    xml.append("</w:tbl>")
    body.append("".join(xml))
    para("")


# =========================================================================== content
para([run("Case Study Implementation", bold=True, size=48, color="0B2545")], align="center")
para([run("Chicago Police Department - Crime Data Analytics", bold=True, size=32, color="E63946")], align="center")
para([run("Web application, data pipeline, data warehouse and analytics (Use Cases 1 - 5)", italic=True)], align="center")
para("")
table(["Item", "Details"], [
    ["Email ID", "<enter your email ID here>"],
    ["Repository", REPO_URL],
    ["Web framework", "Flask 3 (app.py) served by Gunicorn in production (render.yaml)"],
    ["Frontend", "HTML (Jinja2 templates in templates/)"],
    ["Database", "SQLite3 file data/chicago_crime.db, accessed through SQLAlchemy 2 (pipeline/db.py) "
                 "and the sqlite3 DB-API connector (pipeline/reporting.py)"],
    ["Analysis stack", "Pandas, NumPy, Matplotlib, Seaborn; exports to HTML, Excel and CSV"],
    ["Source data", "1 master crime file + 5 reference (dimension) files in data/raw/"],
], widths=[2200, 6800])

# --------------------------------------------------------------------------- checklist
heading("1. Requirements Checklist", new_page=True)
para("Each requirement from the case-study brief was checked against the repository "
     f"({REPO_URL}, branch main). Status legend: Met / Partially met / Not met / Pending.")
table(["#", "Requirement", "Status", "Evidence / gap"], [
    ["1", "5 source files", "Met",
     "data/raw/: iucr_codes.csv, chicago_ward_offices.csv, chicago_police_beat_info.csv, "
     "chicago_district_ps_info.csv, chicago_city_community.csv (+ master chicago_crime_dataset.csv). "
     "Loaded by pipeline/ingest.py into staging (stg_*) and dimension tables."],
    ["2", "Web app - Flask or FastAPI", "Met", "Flask app in app.py (FastAPI not used - either is acceptable)."],
    ["3", "Frontend - HTML or Streamlit", "Met", "Server-rendered HTML pages in templates/ (Streamlit not used)."],
    ["4", "DB - sqlite3, SQLAlchemy 2", "Met",
     "data/chicago_crime.db (SQLite3). SQLAlchemy>=2.1 Core schema with PK/FKs in pipeline/db.py; "
     "summary tables loaded via sqlite3 DB-API cursor in pipeline/reporting.py."],
    ["5", "Dashboard - all graphs from UC4/UC5 with insights (static)", "Partially met",
     "Dashboard route '/' shows every chart (UC2, UC3, UC4 x3, UC5 hotspot map) as static PNGs, KPIs, the "
     "patrol-recommendation table and 'Key Findings'. Gap: Key Findings cover UC1-3 and recommendations only - "
     "there is no written insight for the three UC4 charts, and charts have no per-graph captions."],
    ["6", "Data pipeline to load data into any dimension table", "Not met",
     "Dimension tables are only loaded by the full rebuild from data/raw (ingest.load_full / 'Rebuild warehouse'). "
     "The upload pipeline (/ingest) loads only the crime fact table; dimensions get auto 'UNKNOWN' placeholders."],
    ["7", "CRUD - PUT / POST / PATCH / DELETE", "Not met",
     "app.py exposes GET routes plus form POSTs for /ingest and /rebuild. There are no PUT, PATCH or DELETE "
     "endpoints and no create/update/delete for dimension tables."],
    ["8", "Share all .py code files for all use cases", "Met",
     "UC1 pipeline/ingest.py, UC2 pipeline/eda.py, UC3 pipeline/stats.py, UC4 pipeline/reporting.py, "
     "UC5 pipeline/recommend.py; plus db.py, report.py, runner.py, common.py, config.py, app.py, run_pipeline.py, "
     "tests/test_pipeline.py."],
    ["9", "Share DB file", "Met",
     "data/chicago_crime.db is committed (498 crimes; 5 dimension tables; staging, quarantine, 3 views, "
     "4 summary tables)."],
    ["10", "Word doc - app screenshots (Dashboard, CRUD)", "Pending",
     "Dashboard screenshot must be captured from the running app (see section 2). A CRUD screenshot cannot be "
     "produced until requirement 7 is implemented."],
    ["11", "Word doc - all use cases: questions, output screen print, insights", "Met",
     "Sections 3-7 of this document (outputs taken from the committed run in outputs/)."],
], widths=[400, 2300, 1300, 5000], status_col=2)

heading("Recommended actions to close the gaps", 2)
bullet(" add REST endpoints for the five dimension tables, e.g. GET/POST /api/dimensions/<table> and "
       "GET/PUT/PATCH/DELETE /api/dimensions/<table>/<key> (DELETE should return 409 if crimes still reference "
       "the key), plus an HTML 'Dimensions' page that calls them.", "CRUD:")
bullet(" add a CSV upload that cleans a batch with the existing ingest.clean_* functions, archives it in "
       "stg_<dimension> and upserts it into the chosen dimension table.", "Dimension pipeline:")
bullet(" add a written insight under each UC4 graph (vw_crime_yearly, vw_crime_by_category, summary_district) "
       "and label the hotspot map as Use Case 5. Suggested text is in sections 6 and 7 of this document.",
       "Dashboard:")
bullet(" run the app, then paste the Dashboard and CRUD screenshots into section 2.", "Screenshots:")
para([run("Assumption: ", bold=True), run("'Use Case 5' is the near-real-time patrol recommendation module "
     "(pipeline/recommend.py), the only analysis in the repository after Use Case 4.")])

# --------------------------------------------------------------------------- app
heading("2. The Application", new_page=True)
para("Run locally:")
for cmd in ["pip install -r requirements.txt",
            "python run_pipeline.py      # ingest -> warehouse -> analysis -> charts -> reports",
            "python app.py               # http://127.0.0.1:5000",
            "python -m pytest            # tests"]:
    para([run(cmd)], style="Code")
table(["Page / endpoint", "Method", "Purpose"], [
    ["/  (Dashboard)", "GET", "KPIs, patrol recommendations, key findings and all charts (UC2-UC5)"],
    ["/sql  (Warehouse Reports)", "GET", "UC4 SQL queries with results, views and summary tables"],
    ["/data  (Data Explorer)", "GET", "Filter / search crime records"],
    ["/ingest  (Ingest Data)", "GET, POST", "Upload a crime CSV batch or report one incident (fact table upsert)"],
    ["/rebuild", "POST", "Rebuild the warehouse from the master CSV files"],
    ["/download/<html|excel|crimes>", "GET", "Export the HTML report, Excel workbook or cleaned CSV"],
    ["/api/summary, /api/recommendations", "GET", "JSON APIs"],
], widths=[3000, 1300, 4700])

heading("2.1 Dashboard screenshot", 2)
para([run("[Paste a screenshot of http://127.0.0.1:5000/ here after running 'python app.py'.]",
          italic=True, color="9D0208")])
para("The dashboard displays the following static charts, reproduced from the committed run "
     "(outputs/charts). The UC4 and UC5 graphs with their insights are in sections 6 and 7.")

heading("2.2 CRUD screenshot", 2)
para([run("[Paste a screenshot of the CRUD (PUT / POST / PATCH / DELETE) screen here. Note: this feature is "
          "not yet implemented in the repository - see requirement 7.]", italic=True, color="9D0208")])

# --------------------------------------------------------------------------- UC1
heading("3. Use Case 1 - Load, Clean and Store the Data", new_page=True)
para([run("Code: ", bold=True), run("pipeline/ingest.py, pipeline/db.py")])
heading("Questions and insights", 2)
qa("How many rows and columns are there?",
   "498 rows x 20 columns in chicago_crime_dataset.csv. 2 lines with an unterminated quoted location were "
   "repaired so no record was lost; 498 rows were loaded and 0 quarantined.")
qa("Are there columns with more than 50% missing values - can they be dropped?",
   "None. The highest missing share is 5.82% (location, x/y_coordinate, latitude, longitude), followed by "
   "location_desc at 0.8%, so no column is dropped. Missing location_desc becomes UNKNOWN; missing coordinates "
   "stay NULL and are excluded only from geo analysis.")
qa("How many unique crime types exist?", "23 primary crime types across 97 distinct IUCR codes.")
qa("Are there anomalies in date formats or obvious outliers?",
   "No unparseable dates, no year/date mismatches, no updates before the incident date and no coordinates "
   "outside Chicago. 59 reporting-lag outliers (incidents from 2012-2016 updated in 2016, lag > 7 days) and 29 "
   "records without coordinates. Dates carry no time component, so Hour defaults to 0.")
heading("Output (screen print)", 2)
image(SHOTS / "uc1.png", "UC1 output - profile, first 10 rows and anomaly checks")

# --------------------------------------------------------------------------- UC2
heading("4. Use Case 2 - Exploratory Analysis", new_page=True)
para([run("Code: ", bold=True), run("pipeline/eda.py")])
heading("Questions and insights", 2)
qa("Is the crime rate rising or decreasing?",
   "Recorded crimes rise (2012: 2, 2013: 1, 2014: 1, 2015: 4, 2016: 490). Caveat: 490 of 498 records are from "
   "Apr-May 2016; earlier years only contain late-reported cases, so the trend reflects the extract, not the city.")
qa("Which crime category is most frequent?", "THEFT - 105 crimes (21.08%), followed by BATTERY (17.07%) "
   "and CRIMINAL DAMAGE (9.84%).")
qa("What percentage of crimes result in an arrest?", "24.9% (124 of 498).")
qa("Is the arrest rate consistent across years?",
   "No - std dev 44.84 points (2012: 100%, 2013: 100%, 2014: 0%, 2015: 50%, 2016: 24.29%). Only 2016 has >= 30 "
   "records, so 24.29% is the only statistically meaningful yearly rate.")
qa("Which month has the highest crime frequency?",
   "May (447 crimes); Tuesday and Wednesday in May account for 445 of them.")
qa("Which community areas have the most crime?", "Austin (34, 6.83%), Near North Side (20) and Humboldt Park (20).")
heading("Output (screen print)", 2)
image(SHOTS / "uc2.png", "UC2 output - top 10 categories, arrest rate by year, top 10 community areas")
for name, cap in [("uc2_crimes_per_year", "Total crimes per year"),
                  ("uc2_top10_categories", "Top 10 crime categories"),
                  ("uc2_arrests", "Arrest share and arrest rate by year"),
                  ("uc2_month_day_heatmap", "Month vs day-of-week heatmap"),
                  ("uc2_top10_community_areas", "Top 10 community areas")]:
    image(CHARTS / f"{name}.png", f"UC2 - {cap}")

# --------------------------------------------------------------------------- UC3
heading("5. Use Case 3 - Statistical Insights", new_page=True)
para([run("Code: ", bold=True), run("pipeline/stats.py")])
heading("Questions and insights", 2)
qa("What is the hourly distribution of crime?",
   "All 498 incidents fall at hour 0 because source dates have no time component - time-of-day patrol planning "
   "needs timestamped data.")
qa("What is the mean crime count per community area (NumPy)?",
   "Mean 6.47, median 5.0, IQR 2.0-9.0, upper fence 19.5.")
qa("Which community areas are extreme outliers (box plot / IQR)?",
   "Austin (34), Near North Side (20) and Humboldt Park (20) - all above the 19.5 upper fence.")
qa("Which features are most strongly correlated?",
   "Community~Latitude r = -0.735, District~Ward r = 0.721, Ward~Latitude r = 0.697 (geographic coding). "
   "Arrest has only weak correlations (IndexCrime r = -0.21: index crimes are less likely to end in arrest). "
   "Hour was excluded as constant.")
heading("Output (screen print)", 2)
image(SHOTS / "uc3.png", "UC3 output - IQR outlier community areas")
for name, cap in [("uc3_crimes_by_hour", "Crimes per hour of day"),
                  ("uc3_community_outliers", "Crimes per community area - box plot and outliers"),
                  ("uc3_correlation_heatmap", "Correlation matrix of numeric crime features")]:
    image(CHARTS / f"{name}.png", f"UC3 - {cap}")

# --------------------------------------------------------------------------- UC4
heading("6. Use Case 4 - Data Warehouse Reporting and Integration", new_page=True)
para([run("Code: ", bold=True), run("pipeline/reporting.py, pipeline/db.py, sql/queries.sql, sql/schema_mysql.sql")])
heading("Questions and insights", 2)
qa("Create summary tables and load them through the database connector.",
   "summary_crime_yearly (5 rows), summary_crime_by_category, summary_community_area (77) and summary_district (22) "
   "are created and filled with the sqlite3 DB-API cursor (executemany).")
qa("SQL: what is the crime count per year?", "2012: 2, 2013: 1, 2014: 1, 2015: 4, 2016: 490 (98.4% of all records).")
qa("SQL: what are the top 5 crime types?",
   "THEFT 105 (21.08%), BATTERY 85 (17.07%), CRIMINAL DAMAGE 49 (9.84%), OTHER OFFENSE 39 (7.83%), "
   "DECEPTIVE PRACTICE 38 (7.63%) - together 63.45% of all crimes.")
qa("SQL: what is the arrest count per year?", "2012: 2, 2013: 1, 2014: 0, 2015: 2, 2016: 119 - 124 arrests in total.")
qa("Create views vw_crime_yearly and vw_crime_by_category, read them into Pandas and visualise.",
   "Both views are read with pandas.read_sql and plotted below.")
heading("Output (screen print)", 2)
image(SHOTS / "uc4.png", "UC4 output - SQL query results and vw_crime_yearly")
heading("Graphs and insights", 2)
image(CHARTS / "uc4_vw_crime_yearly.png", "UC4 - vw_crime_yearly: crimes vs arrests per year")
para([run("Insight: ", bold=True, color="E63946"), run(
    "2016 holds 490 of 498 crimes with 119 arrests (24.3%). 2012-2015 contain 1-4 late-reported cases each, so their "
    "0-100% arrest rates are not meaningful; about 1 in 4 crimes leads to an arrest.")])
image(CHARTS / "uc4_vw_crime_by_category.png", "UC4 - top 5 crime types and vw_crime_by_category")
para([run("Insight: ", bold=True, color="E63946"), run(
    "The top 5 types make up 63% of crime. Arrest rates depend on how the crime is detected: NARCOTICS (100%) and "
    "CRIMINAL TRESPASS (88%) are mostly found by officers on the spot, while THEFT (9.5%), CRIMINAL DAMAGE (4.1%), "
    "BURGLARY and MOTOR VEHICLE THEFT (0%) are reported after the fact. Theft is the most common crime and has one "
    "of the lowest clearance rates, so it needs more investigative follow-up.")])
image(CHARTS / "uc4_summary_district.png", "UC4 - summary_district: crimes per police district")
para([run("Insight: ", bold=True, color="E63946"), run(
    "Harrison (district 11) has the most crime (40) and the most arrests (17). Gresham, Englewood and Chicago Lawn "
    "follow with 30 each. Lincoln (7), Shakespeare (10) and Morgan Park (13) have the least. Crime is spread over "
    "22 districts but is concentrated on the west and south sides.")])

# --------------------------------------------------------------------------- UC5
heading("7. Use Case 5 - Near-Real-Time Patrol Recommendations", new_page=True)
para([run("Code: ", bold=True), run("pipeline/recommend.py (refreshed after every ingest via pipeline/runner.py)")])
heading("Questions and insights", 2)
qa("How are hotspots ranked?",
   "Each incident gets a risk weight: severity (index crime x2, violent x1.5) x recency decay (30-day half-life), "
   "as of 2016-05-04. Weights are summed per community area and per beat. Areas above the IQR fence or in the top 3 "
   "are HIGH; ranks 4-10 are MEDIUM.")
qa("Which locality needs more patrols?",
   "Austin - risk score 43.79, 34 crimes, arrest rate 38.2%. Increase patrols on beats 1523, 2531 and 1533, "
   "especially on Wednesdays, focus on Battery, and use a 2.63 km patrol perimeter around (41.8882, -87.7594).")
qa("Which areas are high priority?", "Austin, Near North Side (Theft, 1.08 km perimeter) and Humboldt Park "
   "(Narcotics, 1.42 km perimeter).")
qa("Where is investigative follow-up needed?",
   "Chicago Lawn and West Englewood have a 7.7% arrest rate. Roseland and West Englewood have a high share of "
   "violent crime, so tactical units should be deployed there.")
heading("Output (screen print)", 2)
image(SHOTS / "uc5.png", "UC5 output - top 10 patrol recommendations")
heading("Graph and insight", 2)
image(CHARTS / "rec_hotspot_map.png", "UC5 - patrol hotspots and perimeters (top 10 community areas)", max_width_in=4.8)
para([run("Insight: ", bold=True, color="E63946"), run(
    "The HIGH-priority perimeters are on the West Side (Austin, Humboldt Park) and in the Near North Side. MEDIUM "
    "hotspots cluster on the South Side (Englewood, Chicago Lawn, Auburn Gresham, Roseland, South Shore). Perimeters "
    "range from 0.74 km (Loop) to 2.63 km (Austin), which sets the size of each patrol zone.")])

# --------------------------------------------------------------------------- files
heading("8. Submitted Files", new_page=True)
table(["File", "Purpose"], [
    ["pipeline/ingest.py", "UC1 - robust CSV load, profiling, cleaning, anomaly detection, warehouse load"],
    ["pipeline/eda.py", "UC2 - exploratory analysis and charts"],
    ["pipeline/stats.py", "UC3 - NumPy statistics, IQR outliers, correlation"],
    ["pipeline/reporting.py", "UC4 - summary tables, SQL queries, views, charts"],
    ["pipeline/recommend.py", "UC5 - patrol hotspot ranking and perimeters"],
    ["pipeline/db.py", "SQLAlchemy 2 schema (PK/FK), views, engine"],
    ["pipeline/report.py, pipeline/runner.py, pipeline/common.py", "Exports, orchestration, helpers"],
    ["app.py, templates/*.html", "Flask web application (HTML frontend)"],
    ["run_pipeline.py, config.py", "CLI entry point and configuration"],
    ["tests/test_pipeline.py", "Automated tests"],
    ["data/chicago_crime.db", "SQLite3 database file"],
    ["data/raw/*.csv", "Master crime file + 5 reference source files"],
    ["outputs/", "Charts, HTML / Excel / CSV reports"],
], widths=[3800, 5200])

# =========================================================================== package
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')

document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>'
            + "".join(body)
            + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1080" w:right="1080" w:bottom="1080" '
              'w:left="1080" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr></w:body></w:document>')


def style(sid, name, ppr="", rpr="", based="Normal"):
    return (f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/><w:basedOn w:val="{based}"/>'
            f'<w:qFormat/><w:pPr>{ppr}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>')


styles = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/><w:sz w:val="21"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="100" w:line="264" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>
{style("Heading1", "heading 1", '<w:keepNext/><w:spacing w:before="240" w:after="120"/><w:pBdr><w:bottom w:val="single" w:sz="8" w:space="2" w:color="E63946"/></w:pBdr><w:outlineLvl w:val="0"/>', '<w:b/><w:color w:val="0B2545"/><w:sz w:val="32"/>')}
{style("Heading2", "heading 2", '<w:keepNext/><w:spacing w:before="200" w:after="80"/><w:outlineLvl w:val="1"/>', '<w:b/><w:color w:val="13315C"/><w:sz w:val="26"/>')}
{style("Caption", "caption", '<w:spacing w:after="200"/>', '<w:i/><w:color w:val="5C677D"/><w:sz w:val="18"/>')}
{style("Question", "Question", '<w:keepNext/><w:spacing w:before="120" w:after="20"/>')}
{style("Answer", "Answer", '<w:ind w:left="360"/><w:spacing w:after="80"/>')}
{style("ListBullet", "List Bullet", '<w:ind w:left="360" w:hanging="200"/>')}
{style("Code", "Code", '<w:shd w:val="clear" w:color="auto" w:fill="EEF1F6"/><w:spacing w:after="0"/>', '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="18"/>')}
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders>
<w:top w:val="single" w:sz="4" w:color="C9D2E0"/><w:left w:val="single" w:sz="4" w:color="C9D2E0"/>
<w:bottom w:val="single" w:sz="4" w:color="C9D2E0"/><w:right w:val="single" w:sz="4" w:color="C9D2E0"/>
<w:insideH w:val="single" w:sz="4" w:color="C9D2E0"/><w:insideV w:val="single" w:sz="4" w:color="C9D2E0"/>
</w:tblBorders><w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr></w:style>
</w:styles>"""

content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""

root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""

doc_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            + "".join(rels) + "</Relationships>")

core = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>Chicago Crime Analytics - Case Study Implementation</dc:title><dc:creator>rajvsingh123</dc:creator>
</cp:coreProperties>"""

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", content_types)
    z.writestr("_rels/.rels", root_rels)
    z.writestr("word/document.xml", document)
    z.writestr("word/styles.xml", styles)
    z.writestr("word/_rels/document.xml.rels", doc_rels)
    z.writestr("docProps/core.xml", core)
    for name, data in media:
        z.writestr(f"word/media/{name}", data)
print(OUT, OUT.stat().st_size, "bytes,", len(media), "images")
