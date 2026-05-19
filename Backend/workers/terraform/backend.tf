terraform {
  backend "gcs" {
    bucket = "amos2026ss03-ailixir-tf-state"
    prefix = "ailixir-worker"
  }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }
}