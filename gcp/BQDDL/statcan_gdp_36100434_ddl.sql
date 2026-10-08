CREATE TABLE `privatena2.statcan_gdp_36100434` (
  REF_DATE                      DATE,
  GEO                           STRING,
  DGUID                         STRING,
  SEASONAL_ADJ                  STRING,
  PRICES                        STRING,
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
CLUSTER BY NAICS, PRICES, SEASONAL_ADJ, REF_DATE
OPTIONS (
  description = "StatCan Table 36-10-0434 Basic GDP: Gross domestic product (GDP) at basic prices, by industry, monthly. Full-history file, truncate-and-load each run."
);