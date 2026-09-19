"""
Airflow DAG: StatsCan CPI (table 18-10-0004) monthly full-table download.

Fetches the latest "full table" bulk export for Statistics Canada table
18-10-0004 (Consumer Price Index, monthly) via the WDS
`getFullTableDownloadCSV` endpoint and saves the raw archive, unmodified,
to the NFS-backed "datafiles" PV mounted into worker pods at
/opt/airflow/datafiles (see k8s/charts/airflow/values.yaml ->
workers.kubernetes.extraVolumeMounts, backed by nfs-datafiles.yaml).

The zip is then unpacked and the data CSV reshaped for BigQuery (REF_DATE
"YYYY-MM" -> "YYYY-MM-01", load_date appended), and truncate-loaded into
cutlernet-datahub.privatena2.statcan_cpi_1810000401 (DDL in
gcp/BQDDL/statcan_cpi_1810000401_ddl.sql). Credentials come from the
`google_cloud_default` Airflow connection (see k8s/charts/airflow/values.yaml).

Note: the WDS full-table endpoint returns a ZIP archive (not gzip)
containing the data CSV plus a separate "...MetaData.csv" file. See:
https://www.statcan.gc.ca/en/developers/wds/user-guide
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests
from airflow.sdk import dag, task

logger = logging.getLogger(__name__)

# StatsCan product ID for table 18-10-0004 (dashes stripped, first 8 digits,
# no "-01" suffix -- that's the default view, not part of the product ID).
PRODUCT_ID = "18100004"
LANGUAGE = "en"
WDS_API_URL = (
    "https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/"
    f"{PRODUCT_ID}/{LANGUAGE}"
)

# NFS PV mount path, per k8s/charts/airflow/values.yaml
DATA_ROOT = Path("/opt/airflow/datafiles")
OUTPUT_DIR = DATA_ROOT / "statscan" / "18-10-0004-CPI"

# Data CSV inside the zip (the other member is "18100004_MetaData.csv").
DATA_CSV_NAME = f"{PRODUCT_ID}.csv"
SOURCE_COLUMNS = [
    "REF_DATE", "GEO", "DGUID", "Products and product groups", "UOM",
    "UOM_ID", "SCALAR_FACTOR", "SCALAR_ID", "VECTOR", "COORDINATE", "VALUE",
    "STATUS", "SYMBOL", "TERMINATED", "DECIMALS",
]

# BigQuery target -- schema mirrors gcp/BQDDL/statcan_cpi_1810000401_ddl.sql,
# in the same column order as the transformed CSV.
GCP_CONN_ID = "google_cloud_default"
GCP_PROJECT = "cutlernet-datahub"
BQ_LOCATION = "northamerica-northeast2"
BQ_TABLE = f"{GCP_PROJECT}.privatena2.statcan_cpi_1810000401"
BQ_SCHEMA = [
    ("REF_DATE", "DATE"),
    ("GEO", "STRING"),
    ("DGUID", "STRING"),
    ("PRODUCT_GROUP", "STRING"),
    ("UOM", "STRING"),
    ("UOM_ID", "INT64"),
    ("SCALAR_FACTOR", "STRING"),
    ("SCALAR_ID", "INT64"),
    ("VECTOR", "STRING"),
    ("COORDINATE", "STRING"),
    ("VALUE", "NUMERIC"),
    ("STATUS", "STRING"),
    ("SYMBOL", "STRING"),
    ("TERMINATED", "STRING"),
    ("DECIMALS", "INT64"),
    ("load_date", "DATE"),
]
BQ_CLUSTER_FIELDS = ["GEO", "PRODUCT_GROUP", "REF_DATE"]

default_args = {
    "retries": 2,
    "retry_delay": 300,  # seconds
}


@dag(
    dag_id="statscan_cpi_18100004_monthly",
    description="Download StatsCan CPI (table 18-10-0004) monthly and load to BigQuery",
    schedule="@monthly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["statscan", "cpi", "ingestion", "bigquery"],
)
def statscan_cpi_dag():

    @task
    def download_full_table() -> str:
        """Resolve the current download URL and save the raw zip as-is."""
        resp = requests.get(WDS_API_URL, timeout=30)
        resp.raise_for_status()
        payload = resp.json()

        if payload.get("status") != "SUCCESS":
            raise RuntimeError(f"WDS API returned non-success status: {payload}")

        zip_url = payload["object"]
        logger.info("Resolved full-table download URL: %s", zip_url)

        zip_resp = requests.get(zip_url, timeout=120)
        zip_resp.raise_for_status()

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        run_stamp = datetime.utcnow().strftime("%Y%m%d")
        dest = OUTPUT_DIR / f"18100004_{run_stamp}.zip"
        dest.write_bytes(zip_resp.content)

        logger.info("Wrote CPI archive to %s", dest)
        return str(dest)

    @task
    def extract_csv(zip_path: str) -> str:
        """Stream the data CSV out of the zip, reshaped to match the BQ table."""
        zip_file = Path(zip_path)
        dest = zip_file.with_name(f"{zip_file.stem}_bq.csv")
        load_date = datetime.now(timezone.utc).date().isoformat()
        rows = 0

        with zipfile.ZipFile(zip_file) as zf, zf.open(DATA_CSV_NAME) as raw, \
                dest.open("w", newline="", encoding="utf-8") as out:
            # StatCan CSVs start with a UTF-8 BOM
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            header = next(reader)
            if header != SOURCE_COLUMNS:
                raise ValueError(f"Unexpected CSV header in {zip_path}: {header}")

            writer = csv.writer(out)
            writer.writerow([name for name, _ in BQ_SCHEMA])
            for row in reader:
                if not row:
                    continue
                if len(row[0]) != 7:
                    raise ValueError(f"Unexpected REF_DATE {row[0]!r} at data row {rows + 1}")
                row[0] = f"{row[0]}-01"  # monthly "YYYY-MM" -> DATE
                row.append(load_date)
                writer.writerow(row)
                rows += 1

        logger.info("Wrote %d rows to %s", rows, dest)
        return str(dest)

    @task
    def load_to_bigquery(csv_path: str) -> int:
        """Truncate-and-load the transformed CSV into the BQ table."""
        # Imported here to keep DAG-file parsing fast on the scheduler
        from airflow.providers.google.cloud.hooks.bigquery import BigQueryHook
        from google.cloud import bigquery

        hook = BigQueryHook(gcp_conn_id=GCP_CONN_ID, location=BQ_LOCATION)
        client = hook.get_client(project_id=GCP_PROJECT, location=BQ_LOCATION)

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            schema=[bigquery.SchemaField(name, type_) for name, type_ in BQ_SCHEMA],
            clustering_fields=BQ_CLUSTER_FIELDS,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        with open(csv_path, "rb") as fh:
            job = client.load_table_from_file(fh, BQ_TABLE, job_config=job_config)
            job.result()  # raises on load errors

        logger.info("Load job %s loaded %s rows into %s", job.job_id, job.output_rows, BQ_TABLE)

        # Raw zip stays on NFS as the archive; the reshaped CSV is disposable.
        Path(csv_path).unlink(missing_ok=True)
        return job.output_rows

    load_to_bigquery(extract_csv(download_full_table()))


statscan_cpi_dag()