provider "google" {
  project = var.project_id
  region  = var.region
}

import {
  id = "projects/${var.project_id}/locations/${var.region}/services/ailixir-worker"
  to = google_cloud_run_v2_service.worker
}

resource "google_cloud_run_v2_service" "worker" {
  name     = "ailixir-worker"
  location = var.region

  template {
    containers {
      image = "gcr.io/${var.project_id}/ailixir-worker:${var.image_tag}"

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

output "worker_url" {
  value = google_cloud_run_v2_service.worker.uri
}