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

# -----------------------------
# BACKEND (PUBLIC)
# -----------------------------
resource "google_cloud_run_v2_service" "backend" {
  name     = "ailixir-backend"
  location = var.region

  template {
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

resource "google_cloud_run_v2_service_iam_member" "backend_public" {
  name     = google_cloud_run_v2_service.backend.name
  location = google_cloud_run_v2_service.backend.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# -----------------------------
# WORKER (PRIVATE)
# -----------------------------
resource "google_cloud_run_v2_service" "worker" {
  name     = "ailixir-worker"
  location = var.region

  template {
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

# -----------------------------
# OUTPUTS
# -----------------------------
output "backend_url" {
  value = google_cloud_run_v2_service.backend.uri
}

output "worker_url" {
  value = google_cloud_run_v2_service.worker.uri
}