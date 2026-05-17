provider "google" {
  project = var.project_id
  region  = var.region
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

resource "google_cloud_run_v2_service_iam_member" "worker_invoker" {
  name     = google_cloud_run_v2_service.worker.name
  location = google_cloud_run_v2_service.worker.location
  role     = "roles/run.invoker"
  member   = "projectNumber:${var.project_id}/serviceAccounts/${var.project_id}@appspot.gserviceaccount.com"
}

output "worker_url" {
  value = google_cloud_run_v2_service.worker.uri
}
