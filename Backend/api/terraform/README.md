# Backend API Infrastructure

## Automated Terraform Deployment

Infrastructure is automatically managed through the CI/CD pipeline. No manual setup required!

### What It Does

- Creates Cloud Run service `ailixir-backend`
- Sets up public access (allUsers invoker)
- Manages service URL output

### Required GitHub Secrets

- `GCP_SA_KEY`: Service account JSON key
- `GCP_PROJECT_ID`: Your GCP project ID
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`: chat pipeline knowledge-graph retrieval
- `ELEVENLABS_CUSTOM_LLM_SECRET`: voice Custom LLM integration
- `ASTRA_DB_API_ENDPOINT`, `ASTRA_DB_TOKEN`, `ASTRA_DB_COLLECTION`: chat pipeline hybrid retrieval, research-paper arm (same AstraDB collection `scrapers/` ingests into)
- `OPENAI_API_KEY`: query-embedding key for the research-paper arm — MUST be the same OpenAI key used to embed the scraped collection (`OPEN_AI_API` in `scrapers/.env`)

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
- **Prefix:** `ailixir-backend`

### Local Testing

```bash
cd Backend/api/terraform
terraform init
terraform plan \
  -var="project_id=YOUR_PROJECT_ID" \
  -var="image_tag=latest"
terraform apply \
  -var="project_id=YOUR_PROJECT_ID" \
  -var="image_tag=latest"
```

> The GCS bucket must already exist before running `terraform init`.