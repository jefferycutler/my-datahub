CREATE TABLE privatena2.syslog_events (
    timegenerated       TIMESTAMP,
    timereported        TIMESTAMP NOT NULL,
    relayhost           STRING,
    fromhost_ip         STRING,
    fromhost_name       STRING,
    syslogseverity      INTEGER,
    syslogseverity_text STRING,
    syslogtag           STRING,
    programname         STRING,
    pri                 INTEGER,
    pri_text            STRING,
    syslogfacility_text STRING,
    app_name            STRING,
    msg                 STRING
)
PARTITION BY DATE(timereported)
CLUSTER BY fromhost_name, programname
OPTIONS (
  partition_expiration_days = 180
);