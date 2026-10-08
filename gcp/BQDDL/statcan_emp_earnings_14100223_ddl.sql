CREATE TABLE `privatena2.statcan_emp_earnings_14100223` (
  REF_DATE                      DATE,
  GEO                           STRING,
  DGUID                         STRING,
  ESTIMATE                      STRING,
  NAICS                         STRING,
  UOM                           STRING,
  UOM_ID                        INT64,
  SCALAR_FACTOR                 STRING,
  SCALAR_ID                     INT64,
  VECTOR                        STRING,
  COORDINATE                    STRING,
  VALUE                         NUMERIC,
  STATUS                        STRING,
  SYMBOL                        STRING,
  TERMINATED                    STRING,
  DECIMALS                      INT64,
  load_date                     DATE
)
CLUSTER BY NAICS, GEO, ESTIMATE, REF_DATE
OPTIONS (
  description = "StatCan Table 14-10-0223-01 Employment and average weekly earnings (including overtime) for all employees by province and territory, monthly, seasonally adjusted. truncate-and-load each run."
);
