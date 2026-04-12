# syslog Fluent Bit Pipeline

Reads security-relevant syslog events from Kafka and writes them to BigQuery.
Events are forwarded to Kafka by rsyslog on all managed hosts via the
Setup_SyslogForward.yaml and Setup_SyslogRelay.yaml Ansible playbooks.

## Prerequisites

### 1. GCP credentials secret
The same `gcp-bq-credentials` secret used by the envsense pipeline works here
provided the service account has BigQuery write access to `privatena2`.
If you used a separate SA, create a new secret:

```bash
kubectl create secret generic gcp-bq-credentials \
  --namespace fluentbit-etl \
  --from-file=credentials.json=/path/to/gcpSvcAcct.json
```

### 2. BigQuery table
Ensure the table exists — DDL is in `gcp/BQDDL/privatena2.syslog_events_ddl.sql`:

```bash
bq query --use_legacy_sql=false < gcp/BQDDL/privatena2.syslog_events_ddl.sql
```

### 3. Kafka topic
Should already exist from the rsyslog relay setup. Verify:

```bash
/opt/kafka/bin/kafka-topics.sh --describe \
  --topic syslog-ingest-pr \
  --bootstrap-server kf01:9092
```

## Deployment

```bash
kubectl apply -f k8s/fluentbit-etl/syslog/bq-writer/
```

## Verification

Check pod is running:
```bash
kubectl get pods -n fluentbit-etl -l app=syslog-bq-writer
kubectl logs -n fluentbit-etl -l app=syslog-bq-writer --tail=50
```

Trigger a test event on any managed host and query BigQuery:
```sql
SELECT timegenerated, fromhost_name, programname, syslogfacility_text, msg
FROM `cutlernet-datahub.privatena2.syslog_events`
WHERE DATE(timereported) = CURRENT_DATE()
ORDER BY timegenerated DESC
LIMIT 20;
```