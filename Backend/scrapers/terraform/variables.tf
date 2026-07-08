variable "project_id" {
  description = "GCP Project ID"
  type        = string
  default     = "amos26"
}

variable "region" {
  description = "GCP region for the Cloud Run Job, state bucket, and scheduler"
  type        = string
  default     = "us-east1"
}

variable "image_tag" {
  description = "Docker image tag (git SHA from CI)"
  type        = string
  default     = "latest"
}

# ── Schedule ──────────────────────────────────────────────────────────────────

variable "schedule" {
  description = "Cron for the monthly run (default: 03:00 on the 1st of each month)"
  type        = string
  default     = "0 3 1 * *"
}

variable "time_zone" {
  description = "IANA time zone the cron is evaluated in"
  type        = string
  default     = "Etc/UTC"
}

# ── Runner tunables (become Job env vars; safe to change without a rebuild) ────

variable "scraper_targets" {
  description = "Space-separated paper targets run per keyword phrase"
  type        = string
  default     = "pubmed archive"
}

variable "run_youtube" {
  description = "\"1\" to also run the YouTube channel loop, \"0\" to skip it"
  type        = string
  default     = "1"
}

variable "max_results" {
  description = "Results per keyword query per source"
  type        = string
  default     = "25"
}

variable "youtube_limit" {
  description = "Newest videos inspected per channel per run"
  type        = string
  default     = "25"
}

variable "domain" {
  description = "domain value stored in vector metadata"
  type        = string
  default     = "medical"
}

variable "sub_domain" {
  description = "sub_domain value stored in vector metadata"
  type        = string
  default     = "oncology"
}

# ── Job sizing ────────────────────────────────────────────────────────────────

variable "task_timeout" {
  description = "Max wall-clock per task before Cloud Run kills it (Jobs allow up to 24h)"
  type        = string
  default     = "21600s" # 6h — ~88 phrases x 2 sources + PDF parse + embeddings
}

variable "cpu" {
  description = "vCPU per task"
  type        = string
  default     = "1"
}

variable "memory" {
  description = "Memory per task"
  type        = string
  default     = "2Gi"
}

# ── Secrets (sensitive) — injected as Job env, matching the repo convention of
#    passing secrets as TF vars rather than Secret Manager. Supply via
#    terraform.tfvars / -var / TF_VAR_*; never commit real values. ─────────────

variable "open_ai_api" {
  description = "OpenAI API key (embeddings)"
  type        = string
  sensitive   = true
}

variable "astra_db_api_endpoint" {
  description = "AstraDB API endpoint"
  type        = string
  sensitive   = true
}

variable "astra_db_token" {
  description = "AstraDB application token"
  type        = string
  sensitive   = true
}

variable "astra_db_namespace" {
  description = "AstraDB namespace/keyspace"
  type        = string
  sensitive   = true
}

variable "astra_db_collection" {
  description = "AstraDB collection name"
  type        = string
  sensitive   = true
}

variable "youtube_data_api_v3" {
  description = "YouTube Data API v3 key (only needed when run_youtube = 1)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "ncbi_api_key" {
  description = "NCBI (Entrez) API key — raises the PubMed rate limit 3->10 req/s. Optional but recommended."
  type        = string
  sensitive   = true
  default     = ""
}

variable "alert_email" {
  description = "Email for Cloud Monitoring job-failure alerts. Empty = no alert/channel created."
  type        = string
  default     = "hossamyasseramer@gmail.com"
}
