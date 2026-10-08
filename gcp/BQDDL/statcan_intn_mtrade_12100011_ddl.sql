CREATE TABLE `privatena2.statcan_intn_mtrade_12100011` (
  REF_DATE                      DATE,
  GEO                           STRING,
  DGUID                         STRING,
  TRADE                         STRING,
  BASIS                         STRING,
  SEASONAL_ADJ                  STRING,
  PARTNER                       STRING,
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
CLUSTER BY PARTNER, TRADE, BASIS, REF_DATE
OPTIONS (
  description = "StatCan Table 12-10-0011-01 International merchandise trade for all countries and by principal trading partners, monthly. truncate-and-load each run."
);
