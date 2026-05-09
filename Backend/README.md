# Ailixir Backend

## Deployment

The backend uses **automated Terraform + CI/CD** for infrastructure and application deployment.

### Infrastructure (Terraform)

- **Cloud Run Service**: Automatically created/managed
- **Public Access**: Enabled for API access
- **Zero Manual Setup**: Just push code!

### Application (CI/CD)

- **Container Build**: Automatic Docker image creation
- **Deployment**: Pushes to Cloud Run service
- **Health Checks**: Validates application starts

### Required GitHub Secrets

- `GCP_SA_KEY`: Service account JSON key
- `GCP_PROJECT_ID`: Your GCP project ID

### How It Works

1. **Push to main** → CI/CD pipeline triggers
2. **Terraform runs** → Creates/updates Cloud Run service
3. **Docker builds** → Creates container image
4. **Deploy** → Updates service with new image

### Service Configuration

- **Region**: us-central1
- **Public Access**: Enabled
- **Auto-scaling**: Based on traffic

### Local Development

```bash
# Install dependencies
cd Backend
pip install -r api/requirements.txt

# Run locally
uvicorn api.main:app --reload
```

### API Documentation

When deployed, visit the service URL + `/docs` for interactive API documentation.
