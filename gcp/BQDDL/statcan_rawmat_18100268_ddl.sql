CREATE TABLE `privatena2.statcan_rawmat_18100268` (
  REF_DATE                      DATE,
  GEO                           STRING,
  DGUID                         STRING,
  NAPCS                         STRING,
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
CLUSTER BY NAPCS, GEO, REF_DATE
OPTIONS (
  description = "StatCan Table 18-10-0268-01 Raw materials price index, monthly, by North American Product Classification System (NAPCS). truncate-and-load each run."
);
