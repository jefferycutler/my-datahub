CREATE TABLE `privatena2.statcan_rtrade_20100056` (
  REF_DATE                      DATE,
  GEO                           STRING,
  DGUID                         STRING,
  NAICS                         STRING,
  SALES                         STRING,
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
  description = "StatCan Table 20-10-0056-01 Monthly retail trade sales by province and territory. truncate-and-load each run."
);
