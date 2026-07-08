# Scraping and embedding pipeline

Standalone pipeline that scrapes **arXiv**, **PubMed**, and **YouTube**, chunks the
text, embeds it with OpenAI **`text-embedding-3-small`** (1536-dim), and upserts the
vectors into **AstraDB**. It runs locally for ad-hoc scrapes and in production as a
monthly **Cloud Run Job**.

## Architecture at a glance

```
keywords CSV ─┐
              ├─► Config ─► Orchestrator ─► Scrapers ─► chunk ─► OpenAI ─► AstraDB
channels CSV ─┘  (config.json)  (per target)  (arXiv/PubMed/    split   embeddings   vectors
                                               YouTube)
                                        dedup: data/*/index.json + data/papers/index.json
```

- **Config** (`src/backend/Config`) turns CLI args — targets, keywords, dates,
  metadata — into `data/config.json`.
- **Orchestrator** (`src/backend/Orchestrator`) runs each configured target and
  isolates per-item failures so one bad paper/video can't abort the run.
- **Scrapers** (`src/backend/Scrapers`) fetch and normalize content; the shared
  **BaseScraper** handles chunking, embedding, and the deterministic AstraDB upsert.

## Setup

Python 3.11 (matches the Docker image and CI).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.template .env
```

Fill in the OpenAI and AstraDB values in `.env`. `YOUTUBE_DATA_API_V3` is only
needed for YouTube scraping.

## Configure and run

Generate `data/config.json`:

```powershell
python -m src.backend.Config.main `
  --targets pubmed archive `
  --keywords prostate cancer `
  --since-date 2026-01-01 `
  --max-results 10
```

Then run the configured targets:

```powershell
python -m src.backend.Orchestrator.main
```

Run commands from this folder's root because data paths are relative to it.

## Embeddings

- **Model:** OpenAI `text-embedding-3-small` — **1536 dimensions**
  ([`base_scraper.py`](src/backend/Scrapers/BaseScraper/base_scraper.py)).
- The AstraDB collection is created lazily at this dimension on first write.
  Switching model or dimension therefore requires a **new collection** — the
  stored vectors and any query-side embedding must use the same model to be
  comparable.

## Duplicate protection

The `data/<source>/index.json` files contain IDs already processed by the current
project and are intentionally included. Keep these files in persistent storage
when moving or deploying the pipeline. Every vector also receives a deterministic
ID, so retries update the same AstraDB record rather than inserting another copy.

PubMed and arXiv additionally share `data/papers/index.json`. Before embedding,
the pipeline checks it by DOI and then by an exact normalized-title fingerprint.
Keep this registry persistent together with the source indexes.

The `raw` directories start empty; previously scraped documents and model files
were deliberately excluded from this portable folder.

## Vector Ingestion Metadata Schema

Each chunk is stored in AstraDB with the following metadata structure:

```json
{
  "domain": "medical | financial | other",
  "sub_domain": "e.g. oncology | nutrition",
  "category": "optional free-form tag for filtering (e.g. Disease | Diagnosis | Treatment)",
  "query_keywords": ["keyword1", "keyword2"],
  "document_keywords": ["keyword1", "keyword2"],
  "source": "archive | pubmed | youtube",
  "source_type": "paper | video",
  "published_date": "ISO-8601 date string",
  "ingested_at": "ISO-8601 timestamp",
  "source_id": "unique element identifier",
  "chunk_index": "integer index of chunk within document",
  "content_section": "optional section (e.g. captions, description)",
  "type": "optional content type indicator"
}
```

### Common Metadata Fields

- **domain**: Broad classification (medical, financial, etc.) set during pipeline configuration
- **sub_domain**: Finer classification (e.g. oncology, nutrition) set during pipeline configuration
- **category**: Optional free-form tag (`--category`) for filtering, e.g. the keyword CSV's category column (Disease, Diagnosis & Screening, Treatment); empty string when unset
- **query_keywords**: Search keywords used to discover the source
- **document_keywords**: Keywords extracted from document content
- **source**: The scraper that extracted the data
- **source_type**: The type of content (paper, video)
- **published_date**: Original publication date from source (if available)
- **ingested_at**: ISO-8601 timestamp when the chunk was processed
- **source_id**: Unique identifier for deduplication and retrieval
- **chunk_index**: Sequential index of this chunk within its source document

### Deterministic Vector IDs

Vector store IDs are generated deterministically from:

```
SHA256({scraper_class}:{element_id}:{chunk_index})
```

This ensures idempotent upserts—retries update existing vectors rather than creating duplicates.

## Supported Sources

| Source      | Type           | Key Metadata                                  | Deduplication                         |
| ----------- | -------------- | --------------------------------------------- | ------------------------------------- |
| **arXiv**   | Academic Paper | DOI, title, authors, abstract, published_date | By DOI (primary) or title fingerprint |
| **PubMed**  | Medical Paper  | DOI, title, authors, abstract, published_date | By DOI (primary) or title fingerprint |
| **YouTube** | Video          | Video metadata, transcript sections           | By video_id + chunk                   |

### Source-Specific Metadata

**PubMed & arXiv papers** additionally store:

- `doi`, `authors`, `abstract`, `journal` (PubMed only)
- Shared registry: `data/papers/index.json` for cross-source deduplication

**YouTube** additionally stores:

- `title`, `author`, `viewCount`, `keywords`, and `content_section` (captions or description)

## Deploy to GCP (monthly Cloud Run Job)

The pipeline is packaged as a **Cloud Run Job** (run-to-completion batch, not a
service) triggered by **Cloud Scheduler** once a month. Terraform for it lives in
[`terraform/`](terraform/) and mirrors the `Backend/workers` stack (same TF-state
bucket, provider, and secrets-as-`-var` convention).

### Moving parts

| File                                  | Role                                                                                                                                                                  |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Dockerfile` / `.dockerignore`        | Slim image (no Chrome/ffmpeg — papers + YouTube transcripts only).                                                                                                    |
| `run_monthly.py`                      | Entrypoint: GCS state sync ⇄, computes last-month `--since-date`, then loops the keyword CSVs (PubMed + arXiv per phrase) and the channels CSV (YouTube per channel). |
| `terraform/`                          | Cloud Run Job, Cloud Scheduler (`0 3 1 * *`), GCS state bucket, service accounts + IAM.                                                                               |

### State persistence (important)

The Job syncs the whole `data/` tree to `gs://ailixir-scraper-state-<project>`
before and after each run. Those `data/*/index.json` files + `data/papers/index.json`
are how the pipeline avoids re-scraping — **keep the bucket**; deleting it makes
every run start from scratch (AstraDB's deterministic IDs still prevent duplicate
vectors, but you re-pay for embeddings). YouTube in particular has no date filter,
so its "latest" depends entirely on the persisted `data/youtube/index.json`.

### One-time setup

1. Copy `terraform/terraform.tfvars.example` to `terraform/terraform.tfvars` and
   fill in the OpenAI + AstraDB (and optional YouTube/NCBI) values. This file is
   gitignored — never commit real secrets.
2. For YouTube, `key_words/cancer_youtube_channels.csv` ships with a `url`
   column of resolvable channel URLs, so it works out of the box. When adding
   rows, include a `url`, `channel_url`, or `handle` (e.g. `@PCRI`) — rows
   without one are skipped. To skip YouTube entirely, set `run_youtube = "0"`.

### Deploy manually

```bash
cd Backend/scrapers
TAG=$(git rev-parse --short HEAD)

# 1. build + push the image
#    a) with local Docker:
docker build -t gcr.io/<project>/ailixir-scraper:$TAG .
docker push  gcr.io/<project>/ailixir-scraper:$TAG
#    b) or without local Docker, build remotely on Cloud Build:
gcloud builds submit --tag gcr.io/<project>/ailixir-scraper:$TAG .

# 2. apply the infra (secrets via terraform.tfvars — see terraform.tfvars.example)
cd terraform
terraform init
terraform apply -var="image_tag=$TAG"

# 3. (optional) run it once now instead of waiting for the 1st of the month
gcloud run jobs execute ailixir-scraper --region us-east1
```

Tunables (`schedule`, `max_results`, `youtube_limit`, `task_timeout`, `cpu`,
`memory`, `sub_domain`, `scraper_targets`, `run_youtube`) are Terraform variables —
see [`terraform/variables.tf`](terraform/variables.tf). `max_results` (results per
keyword per source) defaults to **25**; raising it multiplies run time, so keep it
comfortably under `task_timeout` (6h) or split the job per keyword file.

### Monitoring & logs

```bash
# tail live (needs: gcloud components install beta)
gcloud beta logging tail \
  'resource.type="cloud_run_job" AND resource.labels.job_name="ailixir-scraper"' \
  --project <project> --format="value(textPayload)"

# recent logs, newest first
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="ailixir-scraper"' \
  --project <project> --limit 50 --order desc --format="value(textPayload)"

# list executions (find the latest name / running state)
gcloud run jobs executions list --job ailixir-scraper \
  --region us-east1 --project <project> --limit 5
```

Each run ends with a `[summary] success=… failed=… skipped=…` line. A run where
everything is **skipped** usually means the dedup state already covers those
items — expected on a re-run without new papers. Cloud Monitoring emails
`alert_email` if a Job execution fails.

### Troubleshooting

- **arXiv `HTTP 503`** — transient export-API throttling; that keyword's arXiv
  results are skipped for the run and picked up next time. Non-fatal.
- **`Could not retrieve text data from pdf` / paperscraper Elsevier/PMC errors** —
  full-text PDF wasn't reachable (often paywalled), so the **abstract** is embedded
  instead. Non-fatal.
