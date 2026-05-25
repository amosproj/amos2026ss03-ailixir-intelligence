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

variable "openrouter_api_key" {
  description = "OpenRouter API key for the OCR vision model"
  type        = string
  sensitive   = true
  default     = "fill value here"
}

variable "document_ai_processor_id" {
  description = "Document AI processor ID for PDF OCR (create in GCP Console under Document AI)"
  type        = string
  default     = "fill value here"
}

variable "document_ai_location" {
  description = "Document AI processor region — must match where the processor was created (e.g. us, eu)"
  type        = string
  default     = "us"
}