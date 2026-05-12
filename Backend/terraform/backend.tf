terraform {
  backend "gcs" {
    bucket = "amos2026ss03-ailixir-tf-state"
    prefix = "ailixir-backend"
  }
}