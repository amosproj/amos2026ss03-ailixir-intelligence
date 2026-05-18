# Worker Infrastructure

## Automated Terraform Deployment

Infrastructure is automatically managed through the CI/CD pipeline. No manual setup required!

### What It Does

- Creates Cloud Run service `ailixir-worker`
- Runs as a private service (no public access)
- Manages service URL output

### Required GitHub Secrets

- `GCP_SA_KEY`: Service account JSON key
- `GCP_PROJECT_ID`: Your GCP project ID

### Service Account Permissions

The SA needs:

- `roles/run.admin` (Cloud Run)
- `roles/storage.admin` (Container Registry)

### How It Works

1. **Push to main** → CI/CD builds and pushes Docker image tagged with git SHA
2. **Imports existing service** into state if it already exists
3. **Updates infrastructure** if needed
4. **Deploys new image** to Cloud Run

### State Management

State is stored remotely in GCS:

- **Bucket:** `amos2026ss03-ailixir-tf-state`
- **Prefix:** `ailixir-worker`

### Local Testing

```bash
cd Backend/workers/terraform
terraform init
terraform plan \
  -var="project_id=YOUR_PROJECT_ID" \
  -var="image_tag=latest"
terraform apply \
  -var="project_id=YOUR_PROJECT_ID" \
  -var="image_tag=latest"
```

> The GCS bucket must already exist before running `terraform init`.
