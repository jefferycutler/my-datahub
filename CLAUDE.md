## My Datahub Personal Project to explore data engineering in K8s and Airflow
This is a personal home lab project to build a data lake on low cost raspberry PI's using Kubernetes and Airflow.  A mix of streaming data sources and batch collection agents are explored.

## Folder layout

ansible/ folder is for ansible playbooks that standup and maintain host assets.
ansible/inventory.pr.yaml contains the host inventory for the datalake

k8s/ folder is where all kubernetes deployments, configurations, and helm charts will reside

gcp/ folder is where any GCP asset configurations are stored.  We use cloud build for deploying those assets using terraform.

misc/ folder will be for the odd utility script that is not a part of normal operations.

