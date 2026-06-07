# envsense Fluent Bit Pipelines

Pod Deployment for receiving environmental sensor data from various edge devices that report temperature, humidity, and CO2 levels.  The data is saved to a Kafka topic which is read by the second pod, the BQ writer.  We use kafka as a local storage buffer in case of cloud or internet outage.

```
Edge Devices (z01/z02)
       │  TCP :25000
       ▼
[envsense-receiver pod]  →  Kafka: envsensor-pr
       ▼
[envsense-bq-writer pod] →  BigQuery: cutlernet-datahub.production.temp_humid_co2
```

## Folder Structure

```
k8s/fluentbit-etl/envsense/
├── README.md
├── receiver/
│   ├── configmap.yaml   # Fluent Bit TCP→Kafka config
│   ├── deployment.yaml
│   └── service.yaml     # LoadBalancer on :25000
└── bq-writer/
    ├── configmap.yaml   # Fluent Bit Kafka→BigQuery config
    └── deployment.yaml
```

## Deployment Steps

### 1. Create the GCP credentials Secret (one-time, never committed to git)
These credentials are for the service account.  The service account key is for a GCP service account that is restricted to saving data to BigQuery only.

```bash
kubectl create secret generic gcp-bq-credentials \
  --namespace fluentbit-etl \
  --from-file=credentials.json=/path/to/gcpSvcAcct.json
```

### 2. Apply the Kafka topic (if not already created on the PR cluster)

```bash
/opt/kafka/bin/kafka-topics.sh --create \
  --topic envsensor-pr \
  --partitions 3 \
  --replication-factor 3 \
  --bootstrap-server kf01:9092
```

### 3. Deploy both pipelines

```bash
kubectl apply -f k8s/fluentbit-etl/envsense/receiver/
kubectl apply -f k8s/fluentbit-etl/envsense/bq-writer/
```

### 4. Get the receiver's external IP and point your edge devices at it

```bash
kubectl get svc envsense-receiver -n fluentbit-etl
# Point z01/z02 at <EXTERNAL-IP>:25000 with JSON payloads
```