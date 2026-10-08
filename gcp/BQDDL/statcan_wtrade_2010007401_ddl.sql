CREATE TABLE `privatena2.statcan_wtrade_2010007401` (
  REF_DATE                      DATE,
  GEO                           STRING,
  DGUID                         STRING,
  NAICS                         STRING,
  ADJUSTMENTS                   STRING,
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
CLUSTER BY NAICS, GEO, REF_DATE
OPTIONS (
  description = "StatCan Table 20-10-0074-01 Wholesale Trade: estimates of monthly sales and inventory levels for wholesale merchants in Canada, each province and territory. truncate-and-load each run."
);