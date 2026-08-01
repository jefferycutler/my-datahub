CREATE TABLE `privatena2.statcan_cpi_1810000401` (
  REF_DATE                      DATE,
  GEO                           STRING,
  DGUID                         STRING,
  PRODUCT_GROUP                 STRING,
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
CLUSTER BY GEO, PRODUCT_GROUP, REF_DATE
OPTIONS (
  description = "StatCan Table 18-10-0004-01: Consumer Price Index, monthly, not seasonally adjusted. Full-history file, truncate-and-load each run."
);