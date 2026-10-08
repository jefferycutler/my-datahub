CREATE TABLE `privatena2.statcan_rail_loads_23100216` (
  REF_DATE                      DATE,
  GEO                           STRING,
  DGUID                         STRING,
  RAIL_COMPONENT                STRING,
  ESTIMATES                     STRING,
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
CLUSTER BY RAIL_COMPONENT, ESTIMATES, REF_DATE
OPTIONS (
  description = "StatCan Table 23-10-0216-01 Railway carloadings statistics, by total tonnage transported, monthly. truncate-and-load each run."
);
