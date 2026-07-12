"""
Airflow DAG: StatsCan CPI (table 18-10-0004) monthly full-table download.

Fetches the latest "full table" bulk export for Statistics Canada table
18-10-0004 (Consumer Price Index, monthly) via the WDS
`getFullTableDownloadCSV` endpoint and saves the raw archive, unmodified,
to the NFS-backed "datafiles" PV mounted into worker pods at
/opt/airflow/datafiles (see k8s/charts/airflow/values.yaml ->
workers.kubernetes.extraVolumeMounts, backed by nfs-datafiles.yaml).

Downstream unzip/parse is left to a later ETL step.

Note: the WDS full-table endpoint returns a ZIP archive (not gzip)
containing the data CSV plus a separate "...MetaData.csv" file. See:
https://www.statcan.gc.ca/en/developers/wds/user-guide
"""

from __future__ import annotations

import logging
from datetime import datetime
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

default_args = {
    "retries": 2,
    "retry_delay": 300,  # seconds
}


@dag(
    dag_id="statscan_cpi_18100004_monthly",
    description="Download StatsCan CPI (table 18-10-0004) full table zip monthly",
    schedule="@monthly",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["statscan", "cpi", "ingestion"],
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

    download_full_table()


statscan_cpi_dag()