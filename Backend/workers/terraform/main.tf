provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  worker_service_account_id   = "ailixir-worker"
  pubsub_pusher_account_id    = "ailixir-pubsub-pusher"
  topic_document_uploaded     = "document-uploaded"
  topic_document_uploaded_dlq = "document-uploaded-dlq"
  subscription_name           = "document-uploaded-ingestion"
}


# ──────────────────────────────────────────────────────────────────────────────
# Service account the worker Cloud Run service runs as.
# Needs Firestore access (to update document status) and GCS read access (to
# read uploaded files for OCR). Permissions added incrementally as the worker
# grows beyond a stub.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_service_account" "worker" {
  account_id   = local.worker_service_account_id
  display_name = "Ailixir worker service account"
  description  = "Runs the worker (Pub/Sub push receiver) on Cloud Run."
}

resource "google_project_iam_member" "worker_firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_project_iam_member" "worker_storage_object_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.worker.email}"
}


# ──────────────────────────────────────────────────────────────────────────────
# Cloud Run worker service.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "worker" {
  name     = "ailixir-worker"
  location = var.region

  template {
    service_account = google_service_account.worker.email

    containers {
      image = "gcr.io/${var.project_id}/ailixir-worker:${var.image_tag}"

      ports {
        container_port = 8080
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "FIREBASE_PROJECT_ID"
        value = var.project_id
      }
      env {
        # Empty audience disables the OIDC `aud` check; the worker still
        # verifies the token's `email` claim against PUBSUB_PUSH_SERVICE_ACCOUNT,
        # which is the actual identity gate. We leave audience empty because
        # passing the Cloud Run URL here would require a terraform two-pass
        # (the URL is a self-reference that doesn't exist until after create).
        name  = "PUBSUB_PUSH_AUDIENCE"
        value = ""
      }
      env {
        name  = "PUBSUB_PUSH_SERVICE_ACCOUNT"
        value = google_service_account.pubsub_pusher.email
      }
      env {
        name  = "PUBSUB_SKIP_OIDC_VERIFICATION"
        value = "0"
      }
      env {
        name  = "FIREBASE_KEY_RELATIVE_PATH"
        value = ""
      }
    }
  }
}


# ──────────────────────────────────────────────────────────────────────────────
# Service account Pub/Sub uses to sign OIDC tokens when pushing to the worker.
# A dedicated SA (separate from the worker's own SA) lets the worker positively
# identify push requests via the `email` claim.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_service_account" "pubsub_pusher" {
  account_id   = local.pubsub_pusher_account_id
  display_name = "Pub/Sub → Worker push identity"
  description  = "Mints OIDC tokens that Pub/Sub attaches to push requests."
}

# Allow the push SA to invoke the worker Cloud Run service.
resource "google_cloud_run_v2_service_iam_member" "pusher_invoker" {
  name     = google_cloud_run_v2_service.worker.name
  location = google_cloud_run_v2_service.worker.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_pusher.email}"
}


# ──────────────────────────────────────────────────────────────────────────────
# Subscription that delivers DocumentUploaded events to the worker.
#
# The topic itself is declared in api/terraform/. Referencing by name keeps the
# two states independent — order of apply doesn't matter as long as both have
# been applied at least once.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_pubsub_subscription" "ingestion" {
  name  = local.subscription_name
  topic = "projects/${var.project_id}/topics/${local.topic_document_uploaded}"

  ack_deadline_seconds       = 600
  message_retention_duration = "604800s"  # 7 days
  retain_acked_messages      = false
  enable_message_ordering    = true

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.worker.uri}/pubsub/push"

    oidc_token {
      service_account_email = google_service_account.pubsub_pusher.email
      # `audience` defaults to the push_endpoint URL; explicit for clarity.
      audience = google_cloud_run_v2_service.worker.uri
    }
  }

  expiration_policy {
    # Never auto-expire; the subscription lives as long as the topic does.
    ttl = ""
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  dead_letter_policy {
    dead_letter_topic     = "projects/${var.project_id}/topics/${local.topic_document_uploaded_dlq}"
    max_delivery_attempts = 5
  }

  depends_on = [
    google_cloud_run_v2_service_iam_member.pusher_invoker,
  ]
}


# ──────────────────────────────────────────────────────────────────────────────
# Outputs.
# ──────────────────────────────────────────────────────────────────────────────

output "worker_url" {
  value = google_cloud_run_v2_service.worker.uri
}

output "worker_service_account_email" {
  value = google_service_account.worker.email
}

output "pubsub_pusher_service_account_email" {
  value = google_service_account.pubsub_pusher.email
}
