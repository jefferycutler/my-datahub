terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  backend "gcs" {
    bucket = "cutlernet-datahub-tf-state" # You'll need to create this bucket manually once
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. Create the Service Account for Harbor
resource "google_service_account" "harbor_sa" {
  account_id   = "harbor-replicator"
  display_name = "Harbor Replication Service Account"
  description  = "Used by local Harbor to push/pull images for DR sync"
}

# 2. Grant permissions SPECIFICALLY on the PR Repository
resource "google_artifact_registry_repository_iam_member" "harbor_pr_access" {
  project    = var.project_id
  location   = var.region
  repository = "datahub-pr" # Assumes this repo is already created or managed here
  role       = "roles/artifactregistry.writer" # "Writer" allows Push (Backup) and Pull (Restore)
  member     = "serviceAccount:${google_service_account.harbor_sa.email}"
}

# 3. Grant permissions SPECIFICALLY on the NP Repository
resource "google_artifact_registry_repository_iam_member" "harbor_np_access" {
  project    = var.project_id
  location   = var.region
  repository = "datahub-np"
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.harbor_sa.email}"
}