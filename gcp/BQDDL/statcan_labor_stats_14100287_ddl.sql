CREATE TABLE `privatena2.statcan_labor_stats_14100287` (
  REF_DATE                      DATE,
  GEO                           STRING,
  DGUID                         STRING,
  LABOUR_FORCE_CHAR             STRING,
  GENDER                        STRING,
  AGE_GROUP                     STRING,
  STATISTICS                    STRING,
  DATA_TYPE                     STRING,
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
CLUSTER BY GEO, LABOUR_FORCE_CHAR, GENDER, REF_DATE
OPTIONS (
  description = "StatCan Table 14-10-0287-01 Labour force characteristics, monthly, seasonally adjusted and trend-cycle. truncate-and-load each run."
);
