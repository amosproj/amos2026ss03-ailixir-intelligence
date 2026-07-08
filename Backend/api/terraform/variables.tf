variable "project_id" {
  description = "GCP Project ID"
  type        = string
  default     = "amos26"
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-east1"
}

variable "image_tag" {
  description = "Docker image tag (git SHA from CI)"
  type        = string
  default     = "latest"
}

# ── Neo4j (chat pipeline — knowledge graph retrieval) ─────────────────────────

variable "neo4j_uri" {
  description = "Neo4j connection URI (neo4j+s://... for Aura, bolt://... for self-hosted)"
  type        = string
}

variable "neo4j_user" {
  description = "Neo4j database user"
  type        = string
  default     = "neo4j"
}

variable "neo4j_password" {
  description = "Neo4j database password"
  type        = string
  sensitive   = true
}

variable "neo4j_database" {
  description = "Neo4j database name"
  type        = string
  default     = "neo4j"
}

# ── Vertex AI (chat pipeline — Gemini LLM + embeddings) ───────────────────────

variable "vertex_location" {
  description = "Vertex AI region (Gemini models require us-central1)"
  type        = string
  default     = "us-central1"
}

variable "vertex_llm_model" {
  description = "Gemini model for contextualization and answering"
  type        = string
  default     = "gemini-2.5-flash"
}

# ── ElevenLabs (voice — Custom LLM integration, see api/voice.py) ─────────────

variable "elevenlabs_custom_llm_secret" {
  description = "Shared secret ElevenLabs presents as `Authorization: Bearer <value>`; must match the agent's Custom LLM \"API key\" field in the ElevenLabs dashboard"
  type        = string
  sensitive   = true
}

variable "elevenlabs_user_id_header" {
  description = "Request header name ElevenLabs sends the patient's Firebase UID in (configured as a secret__ dynamic variable on the agent's Custom LLM)"
  type        = string
  default     = "X-User-Id"
}

# ── AstraDB + OpenAI (chat pipeline — hybrid retrieval, research-paper arm) ───
# Same AstraDB collection scrapers/ ingests into; see
# api/chat_pipeline/paper_retriever.py and scrapers/README.md.

variable "astra_db_api_endpoint" {
  description = "AstraDB API endpoint (https://<db-id>-<region>.apps.astra.datastax.com)"
  type        = string
}

variable "astra_db_token" {
  description = "AstraDB application token (AstraCS:...)"
  type        = string
  sensitive   = true
}

variable "astra_db_namespace" {
  description = "AstraDB keyspace/namespace"
  type        = string
  default     = "default_keyspace"
}

variable "astra_db_collection" {
  description = "AstraDB collection name holding scraped research-paper chunks"
  type        = string
}

variable "openai_api_key" {
  description = "OpenAI API key for query embeddings — MUST match the embedding model scrapers/ used to ingest the collection (same key as scrapers' OPEN_AI_API)"
  type        = string
  sensitive   = true
}

# ── Vertex AI Ranking API (chat pipeline — reranks paper vector-search hits) ──

variable "vertex_ranking_location" {
  description = "Vertex AI Ranking API location (rankingConfigs only exist at \"global\")"
  type        = string
  default     = "global"
}

variable "vertex_ranking_config_id" {
  description = "Vertex AI ranking config ID (every project gets \"default_ranking_config\" for free)"
  type        = string
  default     = "default_ranking_config"
}

variable "chat_paper_rerank_model" {
  description = "Vertex AI Ranking API model"
  type        = string
  default     = "semantic-ranker-default@latest"
}

# ── Paper retrieval domain scoping ────────────────────────────────────────────
# Hardcoded today — all current users are oncology patients. See
# api/chat_pipeline/paper_retriever.py module docstring.

variable "chat_paper_domain" {
  description = "Metadata pre-filter: domain field on scraped paper chunks"
  type        = string
  default     = "medical"
}

variable "chat_paper_sub_domain" {
  description = "Metadata pre-filter: sub_domain field on scraped paper chunks"
  type        = string
  default     = "oncology"
}
