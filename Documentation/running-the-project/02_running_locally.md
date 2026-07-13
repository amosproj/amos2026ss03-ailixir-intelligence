# 02 — Running Locally

How to run your **own copy** of `api` + `workers` on your machine. Unlike a
typical `docker-compose up` project, most of Ailixir's dependencies are
managed cloud services (Firebase, Vertex AI, Neo4j, AstraDB) rather than
containers you spin up alongside it — so "running locally" means running the
two Python services locally while they talk to real (or emulated) cloud
backends.

> **`Backend/.env.example` is out of date** (it still references an older
> OpenRouter/OCR-vision config that predates the current Gemini-multimodal
> pipeline). The environment variable tables below are sourced directly from
> the current code (`os.environ`/`os.getenv` calls across `shared/`, `api/`,
> `workers/`) — use these, not that file.

## Prerequisites

| What | Needed for | Notes |
|---|---|---|
| Python 3.11 | Both services | Matches the Docker images |
| `gcloud` CLI | Both, unless using a service-account key | `gcloud auth application-default login` for local ADC |
| A GCP project | Both | Needs Firestore, Cloud Storage, Pub/Sub, Vertex AI (`aiplatform.googleapis.com`) enabled |
| A Firebase project (usually the same GCP project) | Both | Auth + Firestore + Realtime Database |
| A Neo4j instance | Both | [Aura Free](https://neo4j.com/cloud/aura/) works, or `docker run neo4j` locally |
| An AstraDB database + collection | API only, **optional** | Only the chat paper-retrieval arm needs it — the rest of the system works fine without it (see below) |
| An OpenAI API key | API only, **optional** | Only needed alongside AstraDB, for query-side paper embeddings |
| An ElevenLabs account | API only, **optional** | Only needed to test the `/voice` endpoint |

You do **not** need Document AI — that's the deprecated OCR pipeline (see
[`code-components/05_workers_pipeline.md`](../code-components/05_workers_pipeline.md#deprecated--dead-code-kept-for-historical-reference-only)).
The current pipeline only needs Vertex AI (Gemini).

## 1. Clone and install

```bash
git clone <repo-url>
cd amos2026ss03-ailixir-intelligence/Backend

python3 -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate on Windows

pip install -r api/requirements.txt
pip install -r workers/requirements.txt
```

Both `requirements.txt` files are independent (each service ships its own
Docker image), but installing both into one venv is the easiest way to run
them side by side locally.

## 2. Credentials

Two independent things need auth: **Firebase Admin SDK** (Firestore, Auth,
Realtime DB) and **Vertex AI / Google Cloud** (Gemini, GCS, Pub/Sub).

- **Firebase Admin SDK** — either:
  - Download a service-account key from Firebase Console → Project
    Settings → Service Accounts, save it under `Backend/`, and set
    `FIREBASE_KEY_RELATIVE_PATH=<filename>`; or
  - Leave `FIREBASE_KEY_RELATIVE_PATH=""` to use Application Default
    Credentials instead (see the next point) — `shared/firestore.py` treats
    an empty value as an explicit opt-in to ADC, not a mistake.
- **Vertex AI / GCP** — `gcloud auth application-default login` once. Both
  `gemini_client.py` modules and `graphiti_client.py` modules (API and
  worker each have their own copies) use ADC, no API key.
- **Fully offline option** — set `FIRESTORE_EMULATOR_HOST` and/or
  `FIREBASE_AUTH_EMULATOR_HOST` to point at the Firebase Local Emulator
  Suite; `shared/firestore.py` auto-detects either and skips real credential
  validation. Vertex AI/Neo4j/AstraDB have no emulator equivalent here, so
  this only gets you as far as auth + document metadata, not the actual
  LLM/graph pipeline.

## 3. Environment variables

### Shared by both services

| Variable | Default | Notes |
|---|---|---|
| `FIREBASE_PROJECT_ID` | `amos26` | |
| `FIREBASE_KEY_RELATIVE_PATH` | `amos26-firebase-adminsdk-fbsvc-c05787eb8f.json` | Set to `""` for ADC |
| `FIREBASE_DATABASE_URL` | the project's `europe-west1` RTDB URL | Only actually exercised by the API's title-writer; harmless to leave default |
| `VERTEX_PROJECT` | *(required)* | GCP project ID |
| `VERTEX_LOCATION` | `us-central1` | Gemini models require this region regardless of where you deploy |
| `VERTEX_LLM_MODEL` | `gemini-2.5-flash` | |
| `VERTEX_EMBEDDING_MODEL` | `text-embedding-005` | |
| `NEO4J_URI` | *(required)* | `bolt://localhost:7687` (local) or `neo4j+s://...` (Aura) |
| `NEO4J_USER` / `NEO4J_PASSWORD` | *(required)* | |
| `NEO4J_DATABASE` | `neo4j` | Aura sometimes uses a generated name instead |

### API-only (`Backend/api`)

| Variable | Default | Notes |
|---|---|---|
| `GCS_BUCKET_NAME` | `ailixir-documents-amos26` | The uploaded-documents bucket |
| `GCS_SIGNED_URL_TTL_SECONDS` | `900` | Signed upload/download URL lifetime |
| `PUBSUB_TOPIC_DOCUMENT_UPLOADED` | `document-uploaded` | |
| `CHAT_GRAPHITI_WARMUP` | unset | `"true"` to eagerly init Graphiti at startup instead of on first chat request |
| `CHAT_GEMINI_PACER_MIN_INTERVAL_S` | `0.30` | Chat pipeline's own Vertex rate limiter |
| `ASTRA_DB_API_ENDPOINT` / `ASTRA_DB_TOKEN` / `ASTRA_DB_COLLECTION` | — | **Optional** — leave unset and the paper-retrieval arm degrades to graph-only answers (see [architecture doc](../architecture/02_question_answering_pipeline.md#component-2b--research-paper-retrieval-chat_pipelinepaper_retrieverpy)) |
| `ASTRA_DB_NAMESPACE` | `default_keyspace` | |
| `OPEN_AI_API` | — | OpenAI key for query-side paper embeddings; only needed with AstraDB configured |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | **Must** match whatever the scraper embedded with — see [doc 04 architecture](../architecture/04_literature_ingestion_pipeline.md#the-embedding-model-coupling-a-documented-footgun-already-hit-once) |
| `VERTEX_RANKING_LOCATION` | `global` | |
| `VERTEX_RANKING_CONFIG_ID` | `default_ranking_config` | |
| `CHAT_PAPER_DOMAIN` / `CHAT_PAPER_SUB_DOMAIN` | `medical` / `oncology` | Pre-filter on the AstraDB metadata |
| `ELEVENLABS_CUSTOM_LLM_SECRET` | — | Required only to exercise `/voice`; unset means that endpoint always 503s (fails closed by design) |
| `ELEVENLABS_USER_ID_HEADER` | `X-User-Id` | |

### Worker-only (`Backend/workers`)

| Variable | Default | Notes |
|---|---|---|
| `GCS_DOCUMENTS_BUCKET` | *(required)* | Same bucket the API's `GCS_BUCKET_NAME` points at |
| `GCS_CYPHER_BUCKET` | *(required)* | Where exported `.cypher` files go |
| `GEMINI_PACER_MIN_INTERVAL_S` | `0.5` | Worker's own (separate-process) Vertex rate limiter |
| `GEMINI_MAX_OUTPUT_TOKENS` | `65536` | Floors Graphiti's edge-extraction token budget — see [doc 01 architecture](../architecture/01_extraction_and_knowledge_graph_pipeline.md#why-every-gemini-call-in-this-service-is-paced) |
| `LLM_CALL_TIMEOUT_S` | `120` | Per-call ceiling for the document-analysis Gemini call |
| `PUBSUB_SKIP_OIDC_VERIFICATION` | unset | **Local dev only.** Set to `1` to accept unsigned pushes to `/pubsub/push` — never set this in a deployed environment |
| `PUBSUB_PUSH_AUDIENCE` / `PUBSUB_PUSH_SERVICE_ACCOUNT` | — | Only relevant when real Pub/Sub pushes reach a locally-exposed worker (e.g. via a tunnel); irrelevant if you're just simulating pushes with curl |

## 4. Run both services

From `Backend/` (both must run from here so the `shared/` package resolves):

```bash
# Terminal 1 — API
uvicorn api.main:app --reload --port 8000

# Terminal 2 — Worker (skip OIDC so you can simulate pushes locally)
PUBSUB_SKIP_OIDC_VERIFICATION=1 uvicorn workers.main:app --reload --port 8080
```

- API docs: `http://localhost:8000/docs`
- Worker docs: `http://localhost:8080/docs` (there's nothing to "try out"
  here beyond `/health` — the real endpoint expects a Pub/Sub envelope, see
  below)

## 5. Exercise the full pipeline locally

The API won't actually publish-and-have-something-consume-it unless you
either (a) point `PUBSUB_TOPIC_DOCUMENT_UPLOADED` at a real Pub/Sub topic
with a push subscription pointed at your local worker (needs a public
tunnel, e.g. `ngrok`), or (b) skip Pub/Sub entirely and call the worker
directly. `Backend/test_e2e.py` does the latter and is the fastest way to
verify a local setup end-to-end:

```bash
# with both services already running (Step 4)
python test_e2e.py
```

It signs up/logs in a test user, uploads a real sample PDF, finalizes it,
then POSTs a hand-built Pub/Sub-shaped envelope straight to
`http://localhost:8080/pubsub/push` — bypassing real Pub/Sub, which is why
`PUBSUB_SKIP_OIDC_VERIFICATION=1` needs to be set on the worker. Useful
flags:

```bash
python test_e2e.py --no-trigger              # upload only, don't call the worker yet
python test_e2e.py --doc-id <id> --uid <uid>  # re-trigger an existing document
```

`Backend/test_pipeline.py` is an **older** smoke test against the deprecated
Document AI OCR path — skip it; it needs `DOCUMENT_AI_PROCESSOR_ID`, which
current deployments don't set.

To simulate a raw Pub/Sub push manually instead (e.g. to test a malformed
payload), see the `curl` recipe in
[`Backend/workers/README.md`](../../Backend/workers/README.md#testing-the-endpoint-manually).

## 6. Docker

Both Dockerfiles expect to be built with `Backend/` as the build context
(not `api/` or `workers/`), so `shared/` is included:

```bash
cd Backend
docker build -f api/Dockerfile -t ailixir-api .
docker build -f workers/Dockerfile -t ailixir-workers .

docker run --rm -p 8000:8000 --env-file .env ailixir-api
docker run --rm -p 8080:8080 --env-file .env ailixir-workers
```

## 7. Running the scraper subsystem locally (optional)

Only needed if you want to populate your own AstraDB collection for the
paper-retrieval arm rather than leaving it unconfigured. It's a fully
separate codebase/venv — see
[`Backend/scrapers/README.md`](../../Backend/scrapers/README.md) and
[`architecture/04_literature_ingestion_pipeline.md`](../architecture/04_literature_ingestion_pipeline.md)
for the full setup and run instructions.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `KeyError: 'VERTEX_PROJECT'` (or similar) on first request | A required env var is unset — required vars have no code default and fail loudly rather than silently degrading |
| Worker won't boot / hangs on startup | Shouldn't happen — the worker's `lifespan` deliberately avoids connecting to Neo4j at startup (see [doc 01 architecture](../architecture/01_extraction_and_knowledge_graph_pipeline.md#lifespan-no-eager-connections)). If it does hang, check for a stray `CHAT_GRAPHITI_WARMUP=true` left over from copying the API's env into the worker's |
| `test_e2e.py` 401s on the worker push | Worker wasn't started with `PUBSUB_SKIP_OIDC_VERIFICATION=1` |
| Neo4j calls hang or fail after working before | Aura Free instances auto-pause when idle — open the Aura console once to resume it |
| Chat answers are graph-only even with AstraDB configured | Check `OPENAI_EMBEDDING_MODEL` matches what your scraper collection was actually embedded with — a mismatch doesn't error, it just returns near-random vector-search results that never make the rerank cut |
| `/voice/v1/chat/completions` always `503` | `ELEVENLABS_CUSTOM_LLM_SECRET` is unset — this is fail-closed by design, not a bug |
