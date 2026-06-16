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
