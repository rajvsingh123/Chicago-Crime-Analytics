-- crime_count_per_year
SELECT year, COUNT(*) AS crime_count
        FROM chicago_crime
        GROUP BY year
        ORDER BY year;

-- top5_crime_types
SELECT i.primary_type,
               COUNT(*) AS crime_count,
               ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM chicago_crime), 2) AS crime_pct
        FROM chicago_crime c
        JOIN iucr i ON c.iucr_code = i.iucr_code
        GROUP BY i.primary_type
        ORDER BY crime_count DESC
        LIMIT 5;

-- arrest_count_per_year
SELECT year, SUM(CASE WHEN arrest THEN 1 ELSE 0 END) AS arrest_count, COUNT(*) AS crime_count
        FROM chicago_crime
        GROUP BY year
        ORDER BY year;

-- summary_crime_yearly
CREATE TABLE summary_crime_yearly (
                    year INT PRIMARY KEY,
                    crime_count INT NOT NULL,
                    arrest_count INT NOT NULL,
                    domestic_count INT NOT NULL,
                    arrest_rate_pct DECIMAL(6,2));
INSERT INTO summary_crime_yearly
SELECT year, COUNT(*),
                        SUM(CASE WHEN arrest THEN 1 ELSE 0 END),
                        SUM(CASE WHEN domestic THEN 1 ELSE 0 END),
                        ROUND(100.0 * SUM(CASE WHEN arrest THEN 1 ELSE 0 END) / COUNT(*), 2)
                     FROM chicago_crime GROUP BY year;

-- summary_crime_by_category
CREATE TABLE summary_crime_by_category (
                    primary_type VARCHAR(64) PRIMARY KEY,
                    crime_count INT NOT NULL,
                    crime_pct DECIMAL(6,2),
                    arrest_count INT NOT NULL,
                    arrest_rate_pct DECIMAL(6,2));
INSERT INTO summary_crime_by_category
SELECT i.primary_type, COUNT(*),
                        ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM chicago_crime), 2),
                        SUM(CASE WHEN c.arrest THEN 1 ELSE 0 END),
                        ROUND(100.0 * SUM(CASE WHEN c.arrest THEN 1 ELSE 0 END) / COUNT(*), 2)
                     FROM chicago_crime c JOIN iucr i ON c.iucr_code = i.iucr_code
                     GROUP BY i.primary_type;

-- summary_community_area
CREATE TABLE summary_community_area (
                    community_code INT PRIMARY KEY,
                    community_name VARCHAR(64),
                    population INT,
                    crime_count INT NOT NULL,
                    arrest_count INT NOT NULL,
                    crimes_per_10k DECIMAL(10,2));
INSERT INTO summary_community_area
SELECT cc.community_code, cc.community_name, cc.population, COUNT(c.case_number),
                        SUM(CASE WHEN c.arrest THEN 1 ELSE 0 END),
                        ROUND(10000.0 * COUNT(c.case_number) / NULLIF(cc.population, 0), 2)
                     FROM city_community cc
                     LEFT JOIN chicago_crime c ON c.community_code = cc.community_code
                     GROUP BY cc.community_code, cc.community_name, cc.population;

-- summary_district
CREATE TABLE summary_district (
                    district_code INT PRIMARY KEY,
                    district_name VARCHAR(64),
                    crime_count INT NOT NULL,
                    arrest_count INT NOT NULL,
                    domestic_count INT NOT NULL);
INSERT INTO summary_district
SELECT d.district_code, d.district_name, COUNT(c.case_number),
                        SUM(CASE WHEN c.arrest THEN 1 ELSE 0 END),
                        SUM(CASE WHEN c.domestic THEN 1 ELSE 0 END)
                     FROM district_ps_info d
                     LEFT JOIN chicago_crime c ON c.district_code = d.district_code
                     GROUP BY d.district_code, d.district_name;
