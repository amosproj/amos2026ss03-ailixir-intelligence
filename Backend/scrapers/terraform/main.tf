provider "google" {
  project = var.project_id
  region  = var.region
}


# ──────────────────────────────────────────────────────────────────────────────
# Required GCP APIs. Enabling in terraform keeps fresh-project provisioning
# self-contained. disable_on_destroy = false avoids yanking an API out from
# under sibling services on `terraform destroy`.
# ──────────────────────────────────────────────────────────────────────────────

locals {
  required_apis = [
    "run.googleapis.com",               # Cloud Run Jobs
    "storage.googleapis.com",           # GCS state bucket
    "cloudscheduler.googleapis.com",    # monthly trigger
    "containerregistry.googleapis.com", # gcr.io image pulls
    "monitoring.googleapis.com"         # job-failure alerting
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.required_apis)
  service  = each.value

  disable_on_destroy         = false
  disable_dependent_services = false
}


# ──────────────────────────────────────────────────────────────────────────────
# Service accounts.
#  - scraper: identity the Job runs as (writes GCS state; reads env secrets).
#  - scheduler: identity Cloud Scheduler uses to execute the Job.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_service_account" "scraper" {
  account_id   = "ailixir-scraper"
  display_name = "Ailixir scraper Cloud Run Job"
  description  = "Runs the monthly scraping + embedding job."
}

resource "google_service_account" "scheduler" {
  account_id   = "ailixir-scraper-sched"
  display_name = "Ailixir scraper scheduler trigger"
  description  = "Cloud Scheduler identity that executes the scraper Job."
}


# ──────────────────────────────────────────────────────────────────────────────
# GCS bucket holding the persistent data/ tree (dedup indexes + paper registry +
# YouTube channel_map). Without this, every monthly run re-scrapes from scratch.
# Versioning lets a bad run be rolled back.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_storage_bucket" "state" {
  name                        = "ailixir-scraper-state-${var.project_id}"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = true
  }

  # Reap old noncurrent versions so rollback history doesn't grow unbounded.
  lifecycle_rule {
    condition {
      age        = 90
      with_state = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket_iam_member" "scraper_state_admin" {
  bucket = google_storage_bucket.state.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.scraper.email}"
}


# ──────────────────────────────────────────────────────────────────────────────
# Cloud Run Job — run-to-completion batch task (not a request-driven service).
# ──────────────────────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_job" "scraper" {
  name     = "ailixir-scraper"
  location = var.region

  template {
    template {
      service_account = google_service_account.scraper.email
      timeout         = var.task_timeout
      # One retry covers a transient source/network blip; the dedup indexes make
      # a retry safe (already-ingested elements are skipped).
      max_retries = 1

      containers {
        image = "gcr.io/${var.project_id}/ailixir-scraper:${var.image_tag}"

        resources {
          limits = {
            cpu    = var.cpu
            memory = var.memory
          }
        }

        # ── Runner behaviour ──────────────────────────────────────────────────
        env {
          name  = "STATE_BUCKET"
          value = google_storage_bucket.state.name
        }
        env {
          name  = "SCRAPER_TARGETS"
          value = var.scraper_targets
        }
        env {
          name  = "RUN_YOUTUBE"
          value = var.run_youtube
        }
        env {
          name  = "MAX_RESULTS"
          value = var.max_results
        }
        env {
          name  = "YOUTUBE_LIMIT"
          value = var.youtube_limit
        }
        env {
          name  = "DOMAIN"
          value = var.domain
        }
        env {
          name  = "SUB_DOMAIN"
          value = var.sub_domain
        }

        # ── Secrets (read by the scraper via os.getenv) ───────────────────────
        env {
          name  = "OPEN_AI_API"
          value = var.open_ai_api
        }
        env {
          name  = "ASTRA_DB_API_ENDPOINT"
          value = var.astra_db_api_endpoint
        }
        env {
          name  = "ASTRA_DB_TOKEN"
          value = var.astra_db_token
        }
        env {
          name  = "ASTRA_DB_NAMESPACE"
          value = var.astra_db_namespace
        }
        env {
          name  = "ASTRA_DB_COLLECTION"
          value = var.astra_db_collection
        }
        env {
          name  = "YOUTUBE_DATA_API_V3"
          value = var.youtube_data_api_v3
        }
        env {
          name  = "NCBI_API_KEY"
          value = var.ncbi_api_key
        }
      }
    }
  }

  depends_on = [
    google_project_service.apis,
    google_storage_bucket_iam_member.scraper_state_admin,
  ]
}


# ──────────────────────────────────────────────────────────────────────────────
# Let the scheduler identity execute the Job. roles/run.invoker includes
# run.jobs.run, which is what Cloud Scheduler needs to POST the :run call.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_job_iam_member" "scheduler_run_invoker" {
  project  = var.project_id
  location = google_cloud_run_v2_job.scraper.location
  name     = google_cloud_run_v2_job.scraper.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}


# ──────────────────────────────────────────────────────────────────────────────
# Monthly trigger. Cloud Scheduler POSTs to the Cloud Run Admin API :run
# endpoint with an OAuth token minted for the scheduler service account.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_cloud_scheduler_job" "monthly" {
  name      = "ailixir-scraper-monthly"
  region    = var.region
  schedule  = var.schedule
  time_zone = var.time_zone

  attempt_deadline = "320s" # deadline for the trigger call itself, not the Job run

  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.scraper.name}:run"

    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }

  # Retry the trigger call itself if it fails to even start the Job (e.g. a
  # transient Cloud Run API error). This does not retry the Job's own work —
  # that is covered by max_retries on the Job and the dedup indexes.
  retry_config {
    retry_count          = 3
    min_backoff_duration = "30s"
    max_backoff_duration = "300s"
    max_doublings        = 3
  }

  depends_on = [
    google_project_service.apis,
    google_cloud_run_v2_job_iam_member.scheduler_run_invoker,
  ]
}


# ──────────────────────────────────────────────────────────────────────────────
# Failure alerting. A monthly cron that fails silently loses a whole month, so
# alert on any failed Job execution. Only created when alert_email is set.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_monitoring_notification_channel" "email" {
  count        = var.alert_email == "" ? 0 : 1
  display_name = "Ailixir scraper alerts"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

resource "google_monitoring_alert_policy" "job_failed" {
  count        = var.alert_email == "" ? 0 : 1
  display_name = "ailixir-scraper job execution failed"
  combiner     = "OR"

  conditions {
    display_name = "Failed execution in the last 10m"
    condition_threshold {
      filter = join(" AND ", [
        "resource.type = \"cloud_run_job\"",
        "resource.labels.job_name = \"${google_cloud_run_v2_job.scraper.name}\"",
        "metric.type = \"run.googleapis.com/job/completed_execution_count\"",
        "metric.labels.result = \"failed\"",
      ])
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      trigger {
        count = 1
      }

      aggregations {
        alignment_period   = "600s"
        per_series_aligner = "ALIGN_DELTA"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email[0].id]

  alert_strategy {
    auto_close = "1800s"
  }

  depends_on = [google_project_service.apis]
}


# ──────────────────────────────────────────────────────────────────────────────
# Outputs.
# ──────────────────────────────────────────────────────────────────────────────

output "job_name" {
  value = google_cloud_run_v2_job.scraper.name
}

output "state_bucket" {
  value = google_storage_bucket.state.name
}

output "scheduler_job" {
  value = google_cloud_scheduler_job.monthly.name
}

output "scraper_service_account_email" {
  value = google_service_account.scraper.email
}

output "scheduler_service_account_email" {
  value = google_service_account.scheduler.email
}
