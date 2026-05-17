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