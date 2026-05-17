terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_cloud_run_service" "backend" {
  name     = "ailixir-backend"
  location = var.region

  template {
    spec {
      containers {
        image = "gcr.io/${var.project_id}/ailixir-backend:latest"
        ports {
          container_port = 8000
        }
        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }
}

resource "google_cloud_run_service_iam_member" "public" {
  service  = google_cloud_run_service.backend.name
  location = google_cloud_run_service.backend.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_service" "worker" {
  name     = "ailixir-worker"
  location = var.region

  template {
    spec {
      containers {
        image = "gcr.io/${var.project_id}/ailixir-worker:latest"
        ports {
          container_port = 8080
        }
        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }
}

# Grant Cloud Pub/Sub service account access to invoke the worker service
resource "google_cloud_run_service_iam_member" "pubsub_invoker" {
  service  = google_cloud_run_service.worker.name
  location = google_cloud_run_service.worker.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_client_config.current.project_number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

data "google_client_config" "current" {}

output "backend_service_url" {
  value       = google_cloud_run_service.backend.status[0].url
  description = "URL of the ailixir-backend service"
}

output "worker_service_url" {
  value       = google_cloud_run_service.worker.status[0].url
  description = "URL of the ailixir-worker service"
}