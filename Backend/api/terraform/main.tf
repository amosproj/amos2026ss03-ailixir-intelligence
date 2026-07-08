provider "google" {
  project = var.project_id
  region  = var.region
}


# ──────────────────────────────────────────────────────────────────────────────
# Required GCP APIs.
#
# Enabling them in terraform keeps fresh-project provisioning self-contained:
# nothing has to be clicked in the console for a new environment to come up.
# `disable_on_destroy = false` prevents `terraform destroy` from yanking the
# API out from under sibling services that depend on it.
# ──────────────────────────────────────────────────────────────────────────────

locals {
  required_apis = [
    "run.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "pubsub.googleapis.com",
    "identitytoolkit.googleapis.com",   # Firebase Auth (signup/signin)
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",    # v4 signed URLs without a private key
    "aiplatform.googleapis.com",        # Vertex AI — Gemini LLM + embeddings in workers
    "documentai.googleapis.com",        # Document AI — PDF OCR in workers
    "discoveryengine.googleapis.com",   # Vertex AI Ranking API — reranks paper retrieval hits
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.required_apis)
  service  = each.value

  disable_on_destroy         = false
  disable_dependent_services = false
}

# Local names referenced repeatedly. Keeping them as locals lets us rename in
# one place if the team converges on a different convention later.
locals {
  bucket_name             = "ailixir-documents-${var.project_id}"
  topic_uploaded          = "document-uploaded"
  topic_uploaded_dlq      = "document-uploaded-dlq"
  api_service_account_id  = "ailixir-api"
}


# ──────────────────────────────────────────────────────────────────────────────
# Service account the API runs as.
#
# Owns: signed-URL signing (Storage Object Admin + serviceAccountTokenCreator
# on itself), event publishing (Pub/Sub Publisher), Firestore reads/writes
# (Datastore User).
# ──────────────────────────────────────────────────────────────────────────────

resource "google_service_account" "api" {
  account_id   = local.api_service_account_id
  display_name = "Ailixir API service account"
  description  = "Runs the documents API on Cloud Run."
}

# Grants the SA permission to mint OAuth tokens for itself, which the
# google-cloud-storage library needs to call IAM Credentials API for signing
# URLs without a private key file. Without this, v4 signed URLs fail on prod.
resource "google_service_account_iam_member" "api_self_token_creator" {
  service_account_id = google_service_account.api.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.api.email}"
}


# ──────────────────────────────────────────────────────────────────────────────
# GCS bucket holding document files.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_storage_bucket" "documents" {
  name                        = local.bucket_name
  location                    = var.region
  uniform_bucket_level_access = true

  # Refuse to destroy a non-empty bucket via `terraform destroy`. Production
  # operators must explicitly empty the bucket first; this prevents the
  # ultimate accidental data loss.
  force_destroy = false

  # Object versioning lets a recovery process restore a file that was
  # accidentally overwritten. We separately enforce x-goog-if-generation-match=0
  # at the API layer so legitimate uploads never overwrite.
  versioning {
    enabled = true
  }

  # Reap noncurrent (versioned) objects after 7 days. Combined with the API's
  # write-once enforcement, this means deleted/replaced objects don't linger.
  lifecycle_rule {
    condition {
      age        = 7
      with_state = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  # CORS for browser-based uploads (Swagger UI Try-It-Out, future web admin).
  # React Native doesn't enforce CORS, so this is for dev tooling — keeping
  # the allow-list tight to known dev origins until we add production ones.
  cors {
    origin          = ["http://localhost:3000", "http://localhost:8000", "http://127.0.0.1:8000"]
    method          = ["GET", "PUT", "HEAD"]
    response_header = ["Content-Type", "x-goog-content-length-range", "x-goog-if-generation-match"]
    max_age_seconds = 3600
  }
}

resource "google_storage_bucket_iam_member" "api_documents_admin" {
  bucket = google_storage_bucket.documents.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.api.email}"
}


# ──────────────────────────────────────────────────────────────────────────────
# Pub/Sub: DocumentUploaded topic and DLQ.
#
# Subscription resource lives in workers/terraform/ (owned by the consumer).
# The API publishes here by name; cross-state references aren't needed because
# Pub/Sub topic names are stable identifiers.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_pubsub_topic" "document_uploaded" {
  name                       = local.topic_uploaded
  message_retention_duration = "604800s"  # 7 days
}

resource "google_pubsub_topic" "document_uploaded_dlq" {
  name                       = local.topic_uploaded_dlq
  message_retention_duration = "604800s"
}

resource "google_pubsub_topic_iam_member" "api_publisher" {
  topic  = google_pubsub_topic.document_uploaded.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.api.email}"
}


# ──────────────────────────────────────────────────────────────────────────────
# Firestore access for the API. Datastore User covers read + write on
# documents within the user's own namespace; security rules (when added) will
# enforce per-uid isolation.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_project_iam_member" "api_firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# Firebase Auth admin: required for the /auth/signup endpoint, which calls
# firebase_admin.auth.create_user under the hood. Without this, every signup
# request fails with a permission-denied error wrapped in a generic 500.
resource "google_project_iam_member" "api_firebase_auth_admin" {
  project = var.project_id
  role    = "roles/firebaseauth.admin"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# Vertex AI — required for the chat pipeline (Gemini LLM calls for
# contextualization + answering, and Gemini embeddings for Graphiti search).
# The same role is already granted to the worker; the API now needs it too
# because the /chat/query endpoint runs Graphiti retrieval inline.
resource "google_project_iam_member" "api_vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# Vertex AI Ranking API — required for the chat pipeline's research-paper
# retrieval arm (api/chat_pipeline/paper_retriever.py). `viewer` is the
# minimal role that grants `discoveryengine.rankingConfigs.rank`; it does
# NOT grant write/index access, which this service never needs (paper
# ingestion is owned entirely by the standalone scrapers/ subsystem).
resource "google_project_iam_member" "api_discoveryengine_viewer" {
  project = var.project_id
  role    = "roles/discoveryengine.viewer"
  member  = "serviceAccount:${google_service_account.api.email}"
}


# ──────────────────────────────────────────────────────────────────────────────
# Cloud Run API service.
# ──────────────────────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "backend" {
  name     = "ailixir-backend"
  location = var.region

  template {
    service_account = google_service_account.api.email

    containers {
      image = "gcr.io/${var.project_id}/ailixir-backend:${var.image_tag}"

      ports {
        container_port = 8000
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
        name  = "GCS_BUCKET_NAME"
        value = google_storage_bucket.documents.name
      }
      env {
        name  = "PUBSUB_TOPIC_DOCUMENT_UPLOADED"
        value = google_pubsub_topic.document_uploaded.name
      }
      # Empty value forces shared/firestore.py and shared/gcs.py to fall back
      # to Application Default Credentials (the metadata server on Cloud Run).
      env {
        name  = "FIREBASE_KEY_RELATIVE_PATH"
        value = ""
      }

      # ── Vertex AI (chat pipeline) ────────────────────────────────────────────
      # Gemini models require us-central1 regardless of the Cloud Run region.
      env {
        name  = "VERTEX_PROJECT"
        value = var.project_id
      }
      env {
        name  = "VERTEX_LOCATION"
        value = var.vertex_location
      }
      env {
        name  = "VERTEX_LLM_MODEL"
        value = var.vertex_llm_model
      }

      # ── Neo4j (chat pipeline — Graphiti knowledge graph retrieval) ───────────
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

      # ── ElevenLabs (voice — Custom LLM integration, see api/voice.py) ───────
      env {
        name  = "ELEVENLABS_CUSTOM_LLM_SECRET"
        value = var.elevenlabs_custom_llm_secret
      }
      env {
        name  = "ELEVENLABS_USER_ID_HEADER"
        value = var.elevenlabs_user_id_header
      }

      # ── AstraDB + OpenAI (chat pipeline — hybrid retrieval, paper arm) ──────
      # Same collection scrapers/ ingests into; the embedding model here MUST
      # match what scrapers used, so OPENAI_API_KEY and the Astra creds are
      # shared across both subsystems. See api/chat_pipeline/paper_retriever.py.
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
        name  = "OPEN_AI_API"
        value = var.openai_api_key
      }
      env {
        name  = "OPENAI_EMBEDDING_MODEL"
        value = var.openai_embedding_model
      }

      # ── Vertex AI Ranking API (reranks paper vector-search hits) ────────────
      env {
        name  = "VERTEX_RANKING_LOCATION"
        value = var.vertex_ranking_location
      }
      env {
        name  = "VERTEX_RANKING_CONFIG_ID"
        value = var.vertex_ranking_config_id
      }
      env {
        name  = "CHAT_PAPER_RERANK_MODEL"
        value = var.chat_paper_rerank_model
      }

      # ── Paper retrieval domain scoping — hardcoded (see variables.tf) ───────
      env {
        name  = "CHAT_PAPER_DOMAIN"
        value = var.chat_paper_domain
      }
      env {
        name  = "CHAT_PAPER_SUB_DOMAIN"
        value = var.chat_paper_sub_domain
      }
    }
  }

  # Ensure IAM bindings exist before the service tries to use them on cold start.
  depends_on = [
    google_service_account_iam_member.api_self_token_creator,
    google_storage_bucket_iam_member.api_documents_admin,
    google_pubsub_topic_iam_member.api_publisher,
    google_project_iam_member.api_firestore_user,
    google_project_iam_member.api_firebase_auth_admin,
    google_project_iam_member.api_vertex_ai_user,
    google_project_iam_member.api_discoveryengine_viewer,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "backend_public" {
  name     = google_cloud_run_v2_service.backend.name
  location = google_cloud_run_v2_service.backend.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}


# ──────────────────────────────────────────────────────────────────────────────
# Outputs.
# ──────────────────────────────────────────────────────────────────────────────

output "backend_url" {
  value = google_cloud_run_v2_service.backend.uri
}

output "documents_bucket" {
  value = google_storage_bucket.documents.name
}

output "topic_document_uploaded" {
  value = google_pubsub_topic.document_uploaded.name
}

output "topic_document_uploaded_dlq" {
  value = google_pubsub_topic.document_uploaded_dlq.name
}

output "api_service_account_email" {
  value = google_service_account.api.email
}
