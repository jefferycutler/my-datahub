CREATE TABLE `privatena2.statcan_indpri_1810026501` (
  REF_DATE                      DATE,
  GEO                           STRING,
  DGUID                         STRING,
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
CLUSTER BY NAICS, GEO, REF_DATE
OPTIONS (
  description = "StatCan Table 18-10-0265-01 Industrial product price index, by major product group, monthly. truncate-and-load each run."
);

