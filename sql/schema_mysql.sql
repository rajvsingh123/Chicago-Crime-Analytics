CREATE TABLE iucr (
	iucr_code VARCHAR(4) NOT NULL, 
	primary_type VARCHAR(64) NOT NULL, 
	description VARCHAR(128), 
	index_code VARCHAR(1), 
	PRIMARY KEY (iucr_code)
);

CREATE TABLE police_beat_info (
	beat_num INTEGER NOT NULL, 
	district INTEGER, 
	sector INTEGER, 
	beat INTEGER, 
	PRIMARY KEY (beat_num)
);

CREATE TABLE district_ps_info (
	district_code INTEGER NOT NULL, 
	district_name VARCHAR(64), 
	address VARCHAR(128), 
	city VARCHAR(64), 
	state VARCHAR(8), 
	zip VARCHAR(10), 
	website VARCHAR(255), 
	phone VARCHAR(32), 
	fax VARCHAR(32), 
	tty VARCHAR(32), 
	x_coordinate FLOAT, 
	y_coordinate FLOAT, 
	latitude FLOAT, 
	longitude FLOAT, 
	location VARCHAR(64), 
	PRIMARY KEY (district_code)
);

CREATE TABLE ward_office (
	ward_no INTEGER NOT NULL, 
	alderman VARCHAR(128), 
	address VARCHAR(255), 
	city VARCHAR(64), 
	state VARCHAR(8), 
	zipcode VARCHAR(10), 
	ward_phone VARCHAR(64), 
	ward_fax VARCHAR(64), 
	email VARCHAR(128), 
	website VARCHAR(255), 
	location VARCHAR(128), 
	city_hall_address VARCHAR(255), 
	city_hall_city VARCHAR(64), 
	city_hall_state VARCHAR(8), 
	city_hall_zipcode VARCHAR(10), 
	city_hall_phone VARCHAR(64), 
	PRIMARY KEY (ward_no)
);

CREATE TABLE city_community (
	community_code INTEGER NOT NULL, 
	community_name VARCHAR(64) NOT NULL, 
	population INTEGER, 
	area_sqmile FLOAT, 
	area_sqkm FLOAT, 
	density_per_sqmi FLOAT, 
	density_per_sqkm FLOAT, 
	PRIMARY KEY (community_code)
);

CREATE TABLE chicago_crime (
	id INTEGER NOT NULL, 
	case_number VARCHAR(16) NOT NULL, 
	date DATETIME NOT NULL, 
	block VARCHAR(128), 
	iucr_code VARCHAR(4) NOT NULL, 
	location_desc VARCHAR(128), 
	arrest BOOL NOT NULL, 
	domestic BOOL NOT NULL, 
	beat_num INTEGER, 
	district_code INTEGER, 
	ward_no INTEGER, 
	community_code INTEGER, 
	fbi_code VARCHAR(4), 
	x_coordinate FLOAT, 
	y_coordinate FLOAT, 
	year INTEGER NOT NULL, 
	month INTEGER NOT NULL, 
	day_of_week VARCHAR(10) NOT NULL, 
	hour INTEGER NOT NULL, 
	date_of_update DATETIME, 
	latitude FLOAT, 
	longitude FLOAT, 
	location VARCHAR(64), 
	PRIMARY KEY (case_number), 
	UNIQUE (id), 
	FOREIGN KEY(iucr_code) REFERENCES iucr (iucr_code), 
	FOREIGN KEY(beat_num) REFERENCES police_beat_info (beat_num), 
	FOREIGN KEY(district_code) REFERENCES district_ps_info (district_code), 
	FOREIGN KEY(ward_no) REFERENCES ward_office (ward_no), 
	FOREIGN KEY(community_code) REFERENCES city_community (community_code)
);

CREATE VIEW vw_crime_details AS
        SELECT c.*, i.primary_type, i.description, i.index_code,
               cc.community_name, d.district_name
        FROM chicago_crime c
        JOIN iucr i ON c.iucr_code = i.iucr_code
        LEFT JOIN city_community cc ON c.community_code = cc.community_code
        LEFT JOIN district_ps_info d ON c.district_code = d.district_code;

CREATE VIEW vw_crime_yearly AS
        SELECT year,
               COUNT(*) AS crime_count,
               SUM(CASE WHEN arrest THEN 1 ELSE 0 END) AS arrest_count,
               ROUND(100.0 * SUM(CASE WHEN arrest THEN 1 ELSE 0 END) / COUNT(*), 2) AS arrest_rate_pct
        FROM chicago_crime
        GROUP BY year;

CREATE VIEW vw_crime_by_category AS
        SELECT i.primary_type,
               COUNT(*) AS crime_count,
               ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM chicago_crime), 2) AS crime_pct,
               SUM(CASE WHEN c.arrest THEN 1 ELSE 0 END) AS arrest_count
        FROM chicago_crime c
        JOIN iucr i ON c.iucr_code = i.iucr_code
        GROUP BY i.primary_type;
