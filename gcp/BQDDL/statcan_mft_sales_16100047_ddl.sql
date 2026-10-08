CREATE TABLE `privatena2.statcan_mft_sales_16100047` (
  REF_DATE                      DATE,
  GEO                           STRING,
  DGUID                         STRING,
  PRINCIPAL_STATISTICS          STRING,
  SEASONAL_ADJ                  STRING,
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
CLUSTER BY NAICS, PRINCIPAL_STATISTICS, SEASONAL_ADJ, REF_DATE
OPTIONS (
  description = "StatCan Table 16-10-0047-01 Manufacturers' sales, inventories, orders and inventory to sales ratios, by industry, monthly. truncate-and-load each run."
);
