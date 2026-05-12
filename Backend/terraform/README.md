# Backend Infrastructure

## Automated Terraform Deployment

Infrastructure is automatically managed through the CI/CD pipeline. No manual setup required!

### What It Does

- Creates Cloud Run service `ailixir-backend`
- Sets up public access
- Manages service URL output

### Required GitHub Secrets

- `GCP_SA_KEY`: Service account JSON key
- `GCP_PROJECT_ID`: Your GCP project ID
- `GCP_TF_STATE_BUCKET`: GCS bucket name for Terraform remote state

### Service Account Permissions

The SA needs:

- `roles/run.admin` (Cloud Run)
- `roles/storage.admin` (Container Registry)

### How It Works

1. **Push to main** → CI/CD runs Terraform automatically
2. **Creates infrastructure** if it doesn't exist
3. **Updates infrastructure** if needed
4. **Deploys application** to the service

### Local Testing

```bash
cd Backend/terraform
terraform init \
  -backend-config="bucket=YOUR_TF_STATE_BUCKET" \
  -backend-config="prefix=ailixir-backend"
terraform plan -var="project_id=YOUR_PROJECT_ID"
terraform apply -var="project_id=YOUR_PROJECT_ID"
```

> The GCS bucket must already exist before running `terraform init`.
