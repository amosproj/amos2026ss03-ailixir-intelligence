provider "google" {
  project = var.project_id
  region  = var.region
}

import {
  id = "projects/${var.project_id}/locations/${var.region}/services/ailixir-backend"
  to = google_cloud_run_v2_service.backend
}

resource "google_cloud_run_v2_service" "backend" {
  name     = "ailixir-backend"
  location = var.region

  template {
    containers {
      image = "gcr.io/${var.project_id}/ailixir-backend:${var.image_tag}"

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

output "backend_url" {
  value = google_cloud_run_v2_service.backend.uri
}