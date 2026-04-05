CREATE TABLE `cutlernet-datahub.publicna2.envsensor`
(
  sensor            STRING    NOT NULL OPTIONS(description="Sensor identifier, e.g. office, backyard"),
  sensor_timestamp  TIMESTAMP NOT NULL OPTIONS(description="Timestamp reported by the sensor"),
  measurements      JSON OPTIONS(description="Flexible set of sensor readings, e.g. {temperature, humidity, co2}")
)
PARTITION BY DATE(sensor_timestamp)
CLUSTER BY sensor
OPTIONS (
  partition_expiration_days = 3650  -- 10 years, adjust to taste
);