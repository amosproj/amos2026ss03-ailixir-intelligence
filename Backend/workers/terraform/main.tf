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
  documents_bucket_name       = "ailixir-documents-${var.project_id}"
  cypher_bucket_name          = "ailixir-cypher-${var.project_id}"

  # The API service account is defined in api/terraform/main.tf as
  # `account_id = "ailixir-api"`. We hardcode its email here rather than
  # using a `data "google_service_account"` lookup because that lookup
  # would create a hard ordering between the two terraform states
  # (api/ must apply before workers/ can plan). With this string the
  # binding still applies cleanly even if both states race.
  api_service_account_email = "ailixir-api@${var.project_id}.iam.gserviceaccount.com"
}


# ──────────────────────────────────────────────────────────────────────────────
# Enable Vertex AI API (needed for Gemini LLM + embeddings via ADC).
# ──────────────────────────────────────────────────────────────────────────────

resource "google_project_service" "vertex_ai" {
  service            = "aiplatform.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "document_ai" {
  service            = "documentai.googleapis.com"
  disable_on_destroy = false
}


# ──────────────────────────────────────────────────────────────────────────────
# Service account the worker Cloud Run service runs as.
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

# Scoped read access to the documents bucket only (not all buckets in project).
resource "google_storage_bucket_iam_member" "worker_documents_viewer" {
  bucket = local.documents_bucket_name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.worker.email}"
}

# Write access to the cypher bucket (fix #4 — was objectViewer project-wide).
resource "google_storage_bucket_iam_member" "worker_cypher_admin" {
  bucket     = google_storage_bucket.cypher.name
  role       = "roles/storage.objectAdmin"
  member     = "serviceAccount:${google_service_account.worker.email}"
  depends_on = [google_storage_bucket.cypher]
}

# Read access for the API service account so it can sign v4 GET URLs for
# the .cypher files. v4 signed URLs carry the signer's identity in the
# signature; GCS evaluates the signer (not the caller) for object access.
# Without this binding, the signed URL the API returns to the frontend
# 403s with "ailixir-api does not have storage.objects.get access". This
# is purely a read grant — the worker keeps exclusive write access via
# the binding above.
resource "google_storage_bucket_iam_member" "api_cypher_viewer" {
  bucket     = google_storage_bucket.cypher.name
  role       = "roles/storage.objectViewer"
  member     = "serviceAccount:${local.api_service_account_email}"
  depends_on = [google_storage_bucket.cypher]
}

# Vertex AI — required for Gemini LLM and embedding calls via graphiti-core.
resource "google_project_iam_member" "worker_vertex_ai_user" {
  project    = var.project_id
  role       = "roles/aiplatform.user"
  member     = "serviceAccount:${google_service_account.worker.email}"
  depends_on = [google_project_service.vertex_ai]
}

# Document AI — required for PDF OCR via google-cloud-documentai.
resource "google_project_iam_member" "worker_document_ai_user" {
  project    = var.project_id
  role       = "roles/documentai.apiUser"
  member     = "serviceAccount:${google_service_account.worker.email}"
  depends_on = [google_project_service.document_ai]
}


# ──────────────────────────────────────────────────────────────────────────────
# GCS bucket for exported Cypher graph files (fix #3 — bucket was missing).
# Workers write here; frontend reads the signed URL from Firestore.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_storage_bucket" "cypher" {
  name                        = local.cypher_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  versioning {
    enabled = false
  }

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }
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

      # ── GCP / Firebase ──────────────────────────────────────────────────────
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "FIREBASE_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "FIREBASE_KEY_RELATIVE_PATH"
        value = ""
      }

      # ── Pub/Sub OIDC ────────────────────────────────────────────────────────
      env {
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

      # ── GCS buckets (fix #2 and #3) ─────────────────────────────────────────
      env {
        name  = "GCS_DOCUMENTS_BUCKET"
        value = local.documents_bucket_name
      }
      env {
        name  = "GCS_CYPHER_BUCKET"
        value = google_storage_bucket.cypher.name
      }

      # ── Vertex AI / Gemini ──────────────────────────────────────────────────
      # VERTEX_LOCATION is independent of the Cloud Run region (var.region).
      # Gemini models require us-central1; us-east1 does not have them.
      env {
        name  = "VERTEX_PROJECT"
        value = var.project_id
      }
      env {
        name  = "VERTEX_LOCATION"
        value = "us-central1"
      }
      # gemini-2.5-flash chosen over the cheaper -flash-lite because flash
      # carries a much higher per-project Generate-Content RPM quota. With
      # GRAPHITI_INCLUDE_RAW_OCR=true below, Graphiti can burst 30-50 Gemini
      # calls per document during entity resolution — flash-lite's quota
      # was being exhausted by that pattern and surfacing as RateLimitError
      # → document FAILED. Changes here need a worker redeploy to apply.
      env {
        name  = "VERTEX_LLM_MODEL"
        value = "gemini-2.5-flash"
      }
      env {
        name  = "EMBEDDING_DIM"
        value = "768"
      }

      # ── Graphiti pipeline ───────────────────────────────────────────────────
      # When ON, the worker forwards the full OCR raw text (and tables) into
      # Graphiti's episode body. Gemini then extracts real clinical entities
      # ("Schmidt, Johannes", "Bandscheibenprolaps L4/L5", etc.) instead of
      # just the filename. Off would degrade gracefully to a filename-only
      # graph — useful as an emergency kill-switch if Vertex rate limits
      # ever break extraction again. See workers/pipeline/document_pipeline.py.
      env {
        name  = "GRAPHITI_INCLUDE_RAW_OCR"
        value = "true"
      }
      # Paces Vertex Gemini calls at one per N seconds to stay under the
      # project's Generate-Content RPM quota. 0.5s = 120 RPM ceiling, safe
      # under the gemini-2.5-flash default quota even with the rich-payload
      # burst. See workers/connections/paced_gemini.py.
      env {
        name  = "GEMINI_PACER_MIN_INTERVAL_S"
        value = "0.5"
      }

      # ── Neo4j (fix #5 — was completely missing) ──────────────────────────────
      env {
        name  = "NEO4J_URI"
        value = var.neo4j_uri
      }
      env {
        name  = "NEO4J_USER"
        value = var.neo4j_user
      }
      env {
        name  = "NEO4J_PASSWORD"
        value = var.neo4j_password
      }
      env {
        name  = "NEO4J_DATABASE"
        value = var.neo4j_database
      }

      # ── Google Cloud Document AI OCR (PDFs) ──────────────────────────────────
      env {
        name  = "DOCUMENT_AI_PROCESSOR_ID"
        value = var.document_ai_processor_id
      }
      env {
        name  = "DOCUMENT_AI_LOCATION"
        value = var.document_ai_location
      }
    }
  }

  depends_on = [
    google_project_iam_member.worker_firestore_user,
    google_storage_bucket_iam_member.worker_documents_viewer,
    google_storage_bucket_iam_member.worker_cypher_admin,
    google_project_iam_member.worker_vertex_ai_user,
    google_project_iam_member.worker_document_ai_user,
  ]
}


# ──────────────────────────────────────────────────────────────────────────────
# Service account Pub/Sub uses to sign OIDC tokens when pushing to the worker.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_service_account" "pubsub_pusher" {
  account_id   = local.pubsub_pusher_account_id
  display_name = "Pub/Sub → Worker push identity"
  description  = "Mints OIDC tokens that Pub/Sub attaches to push requests."
}

resource "google_cloud_run_v2_service_iam_member" "pusher_invoker" {
  name     = google_cloud_run_v2_service.worker.name
  location = google_cloud_run_v2_service.worker.location
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.pubsub_pusher.email}"
}


# ──────────────────────────────────────────────────────────────────────────────
# Subscription that delivers DocumentUploaded events to the worker.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_pubsub_subscription" "ingestion" {
  name  = local.subscription_name
  topic = "projects/${var.project_id}/topics/${local.topic_document_uploaded}"

  ack_deadline_seconds       = 600
  message_retention_duration = "604800s" # 7 days
  retain_acked_messages      = false
  enable_message_ordering    = true

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.worker.uri}/pubsub/push"

    oidc_token {
      service_account_email = google_service_account.pubsub_pusher.email
      audience              = google_cloud_run_v2_service.worker.uri
    }
  }

  expiration_policy {
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

output "cypher_bucket" {
  value = google_storage_bucket.cypher.name
}
