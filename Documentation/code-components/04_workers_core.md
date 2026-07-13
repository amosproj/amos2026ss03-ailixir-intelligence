# 04 — Workers Core (`Backend/workers/main.py`, `Backend/workers/connections/`)

The worker service's entry point and its singleton clients for every
external dependency (Gemini, Neo4j/Graphiti, GCS). Pipeline logic that
*uses* these clients lives in [`workers/pipeline/`](05_workers_pipeline.md).

## `workers/main.py`

**Purpose:** The FastAPI app for the internal Pub/Sub push receiver — not a
public API. Full request lifecycle in
[doc 01 architecture](../architecture/01_extraction_and_knowledge_graph_pipeline.md#component-1--pubsub-push-receiver-workersmainpy).
- `lifespan()` — deliberately does **not** touch Neo4j/Graphiti at startup (lazy connect on first use); best-effort close of Graphiti + the Neo4j driver on shutdown.
- `PubSubMessage`, `PubSubEnvelope` — Pydantic models for the Pub/Sub push HTTP envelope.
- `_verify_oidc_token(authorization_header)` — validates the Google-signed OIDC token: audience, issuing service account email, `email_verified`. Skippable via `PUBSUB_SKIP_OIDC_VERIFICATION=1` for local dev only.
- `_handle_document_uploaded(payload)` — the one registered handler; validates `document_id`/`uid` are present, then calls `workers.pipeline.document_pipeline.run()`.
- `_EVENT_HANDLERS` — `event_type → handler` dispatch table (currently just `"DocumentUploaded"`).
- `_RETRYABLE_DEPENDENCY_ERRORS` — the subset of exceptions mapped to `503` (Pub/Sub retry) rather than `500`.
- `pubsub_push(envelope, authorization)` — the route: verify OIDC → decode base64 JSON → dispatch by `event_type` → map the outcome to `204`/`422`/`503`/`500` per the retry contract described in the architecture doc.
- `health()` — `GET /health`.

## `workers/connections/gemini_client.py`

**Purpose:** Singleton Gemini/Vertex AI client used directly by the LLM
document-analysis step (not by Graphiti, which has its own client — see
below).
- `get_gemini_client()` — lazy singleton, ADC auth, `VERTEX_PROJECT`/`VERTEX_LOCATION` env vars.

## `workers/connections/graphiti_client.py`

**Purpose:** Singleton `Graphiti` instance for **ingestion** — wraps Neo4j +
paced Gemini clients + embedder.
- `get_graphiti()` — builds `Graphiti` with `Neo4jDriver`, `PacedGeminiClient`, `GeminiEmbedder` (768-dim, `text-embedding-005`), `PacedGeminiRerankerClient`. Calls `build_indices_and_constraints()` once per process (guarded by `_indices_built`), on first use — not at app startup.
- `close_graphiti()` — closes the driver; called from `main.py`'s shutdown.
- **Notes:** Default LLM model is `gemini-2.5-flash` (not `-lite`) — the module docstring is explicit that even with pacing, `-lite`'s lower RPM budget would saturate under the entity-resolution burst a fixed-schema episode produces.

## `workers/connections/neo4j.py`

**Purpose:** Singleton raw Neo4j driver — used directly (not through Graphiti) by the Cypher exporter, which runs its own read queries.
- `get_driver()` — lazy singleton `GraphDatabase.driver`.
- `get_session()` — opens a session against the configured database (`NEO4J_DATABASE`, default `neo4j`).
- `close_driver()`.

## `workers/connections/gcs.py`

**Purpose:** Worker-side GCS helpers — downloading uploaded documents, uploading exported Cypher files. (Distinct from `shared/gcs.py`, which handles the API's signed-URL generation.)
- `get_client()` — singleton `storage.Client`.
- `download_bytes(gcs_uri)` — full `gs://bucket/path` URI → `(bytes, content-type)`.
- `download_document(gcs_object_path)` — downloads from `GCS_DOCUMENTS_BUCKET` by the relative path stored on `DocumentFile.gcs_object_path`.
- `upload_text(content, doc_id, suffix, folder="graphs")` — uploads to `GCS_CYPHER_BUCKET` at `{folder}/{doc_id}_{suffix}`, returns the `gs://` URI.
- `_parse_uri(gcs_uri)` — `gs://bucket/path` → `(bucket, path)`.

## `workers/connections/paced_gemini.py`

**Purpose:** Rate-limit pacer + output-token-floor fix for every Gemini call
Graphiti makes internally during ingestion. Full rationale (why a single
document can burst 30-50 calls, and the thinking-tokens truncation bug this
also fixes) in
[doc 01 architecture](../architecture/01_extraction_and_knowledge_graph_pipeline.md#why-every-gemini-call-in-this-service-is-paced).
- `pace_gemini_call()` — public admission hook for callers **outside** Graphiti's own client classes (used by `pipeline/llm/extractor.py`'s direct Vertex calls, so the top-level analyzer and Graphiti's internal calls share one admission queue).
- `PacedGeminiClient(GeminiClient)` — overrides `generate_response` to admit via the pacer and floor `max_tokens` to `_MAX_OUTPUT_TOKENS` (65536) before delegating to the base class.
- `PacedGeminiRerankerClient(GeminiRerankerClient)` — overrides `rank` to admit via the same pacer.
- `_admit()` — the actual wait/timestamp-update logic, guarded by one module-global `asyncio.Lock` + `_last_call_at`, shared across every caller in the process.
- Constants: `_MIN_INTERVAL_S` (0.5s, env `GEMINI_PACER_MIN_INTERVAL_S`), `_MAX_OUTPUT_TOKENS` (65536, env `GEMINI_MAX_OUTPUT_TOKENS`).
