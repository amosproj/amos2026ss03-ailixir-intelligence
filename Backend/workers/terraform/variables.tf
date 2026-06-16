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

variable "neo4j_uri" {
  description = "Neo4j connection URI (e.g. neo4j+s://xxxx.databases.neo4j.io)"
  type        = string
  sensitive   = true
  default     = "fill value here"
}

variable "neo4j_user" {
  description = "Neo4j username"
  type        = string
  sensitive   = true
  default     = "fill value here"
}

variable "neo4j_password" {
  description = "Neo4j password"
  type        = string
  sensitive   = true
  default     = "fill value here"
}

variable "neo4j_database" {
  description = "Neo4j database name (default: neo4j — AuraDB often uses a custom name like a UUID)"
  type        = string
  default     = "neo4j"
}

# document_ai_processor_id and document_ai_location are retained here so that
# existing terraform.tfvars files setting these values do not cause Terraform
# to error. They are no longer referenced by any resource — the pipeline now
# uses Gemini multimodal (Vertex AI) instead of Document AI for document analysis.
variable "document_ai_processor_id" {
  description = "UNUSED — kept for tfvars compatibility. Document AI replaced by Gemini multimodal."
  type        = string
  default     = ""
}

variable "document_ai_location" {
  description = "UNUSED — kept for tfvars compatibility. Document AI replaced by Gemini multimodal."
  type        = string
  default     = ""
}