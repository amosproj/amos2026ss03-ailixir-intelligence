terraform {
  backend "gcs" {
    bucket = "amos2026ss03-ailixir-tf-state"
    prefix = "ailixir-scraper"
  }

  required_providers {
    google = {
      source = "hashicorp/google"
      # google_cloud_run_v2_job requires provider >= 4.44. `~> 4.0` resolves to
      # the newest 4.x on first `terraform init`, which satisfies that. If an
      # existing lock pins an older 4.x, run `terraform init -upgrade`.
      version = "~> 4.0"
    }
  }
}
