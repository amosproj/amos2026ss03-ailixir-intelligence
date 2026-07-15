# 01 — Shared (`Backend/shared/`)

Code imported by **both** the API and worker services. Nothing in here talks
to a specific pipeline step — it's models, persistence, and thin
infrastructure clients. Both services run `uvicorn` from `Backend/` so this
package resolves the same way for either.

## Infrastructure clients

### `shared/firestore.py`
**Purpose:** Firebase Admin SDK bootstrap and the singleton Firestore client both services go through.
- `ensure_firebase_app()` — initializes the Firebase app exactly once (thread-safe double-checked lock). Three paths: emulator mode (`FIRESTORE_EMULATOR_HOST`/`FIREBASE_AUTH_EMULATOR_HOST` set), Application Default Credentials (empty `FIREBASE_KEY_RELATIVE_PATH` — the Cloud Run path), or a service-account JSON key file.
- `get_firestore()` — returns the cached `Client`, calling `ensure_firebase_app()` first if needed.
- **Notes:** A non-empty `FIREBASE_KEY_RELATIVE_PATH` pointing at a missing file raises loudly (`FileNotFoundError`) rather than silently falling back to ADC — a typo here should not masquerade as "using ADC on purpose." Also sets `databaseURL` unconditionally so the Realtime Database `db` module (used by `chat_pipeline/titler.py`) works.

### `shared/gcs.py`
**Purpose:** GCS client + v4 signed URL generation. The API never proxies file bytes — clients upload/download directly to/from GCS using URLs this module mints.
- `get_storage_client()`, `get_bucket()` — singleton client / documents bucket handle.
- `build_object_path(uid, document_id, file_id, extension)` — canonical path `users/{uid}/documents/{doc_id}/{file_id}.{ext}`.
- `generate_upload_url(object_path, content_type, max_size_bytes, ttl=900s)` — signed PUT URL; binds content-type, a size range (`x-goog-content-length-range`), and write-once semantics (`x-goog-if-generation-match: 0`).
- `generate_download_url(object_path, ttl)` / `generate_download_url_for_gs_uri(gs_uri, ...)` — signed GET URLs; the `_for_gs_uri` variant signs across *any* bucket (used for the worker-owned cypher bucket).
- `verify_object_exists(object_path)` — async existence check (wraps a sync `blob.exists()` in a thread so many can run concurrently via `asyncio.gather`).
- `delete_object(object_path)` — best-effort, swallows failures (a reconciliation job is the authoritative cleaner).
- **Notes:** Two separate credential objects exist — the storage client's own (scoped to `devstorage.*`) and a dedicated `cloud-platform`-scoped one just for `_signing_kwargs()` — reusing the storage client's credentials for signing 403s in production (`ACCESS_TOKEN_SCOPE_INSUFFICIENT`).

### `shared/pubsub.py`
**Purpose:** Publishes the `DocumentUploaded` event that hands a finalized document off to the worker.
- `publish_document_uploaded(document)` — builds the event payload (`event_type`, `event_id`, `schema_version`, file list filtered to only files whose upload completed), publishes with `ordering_key=document.id`, returns the Pub/Sub message id.
- **Notes:** The publisher client is created once with `enable_message_ordering=True` — ordering is a client-construction-time setting, not per-publish. The matching subscription (owned by `workers/terraform/`) must also have ordering enabled.

### `shared/retryable_errors.py`
**Purpose:** Single source of truth for "is this a transient failure worth retrying." Consumed by the worker's Pub/Sub handler, `document_pipeline.py`, and `api/chat.py`.
- `RETRYABLE_PIPELINE_ERRORS` — tuple covering Neo4j transient errors, generic `ConnectionError`/`TimeoutError`, and Vertex/Google API transient errors (`ResourceExhausted`, `ServiceUnavailable`, `DeadlineExceeded`, `InternalServerError`) plus Graphiti's `RateLimitError`.
- `is_retryable(exc)` — boolean convenience wrapper.
- **Notes:** Optional imports (`google-api-core`, `graphiti-core`) are guarded with harmless placeholder exception classes so this module loads even in a test environment without those deps installed.

## Models (`shared/models/`)

Plain Pydantic `BaseModel`s — the shapes stored in Firestore and shared
between both services. None of them contain I/O.

| File | Model(s) | Notes |
|---|---|---|
| `document.py` | `Document`, `DocumentFile`, `DocumentStatus` (enum) | Also holds the shared constants both API and worker validate against: `SUPPORTED_DOMAINS`, `ALLOWED_FILE_CONTENT_TYPES`, `EXTENSION_BY_CONTENT_TYPE`, `MAX_FILES_PER_DOCUMENT` (50), `MAX_FILE_SIZE_BYTES` (20MB), `MAX_TOTAL_SIZE_BYTES` (200MB). `Document.model_config` uses `extra="ignore"` so older Firestore records missing newer fields still deserialize. |
| `extraction.py` | `Extraction` | Carries both the legacy OCR fields (`raw_text`, `extracted_fields`, `confidence_score` — `None` for new records) and the current LLM fields (`document_purpose`, `document_date`, `episode_body`). |
| `journey_summary.py` | `JourneySummary` | One per user: `uid`, `summary`, `document_count`, `last_updated`, `last_extraction_id`. |
| `user.py` | `UserProfile` | `uid`, `email`, `first_name`, `last_name` + timestamps — the fields Firebase Auth itself doesn't store. |
| `literature_paper.py` | `LiteraturePaper` | The scraper subsystem's global dedup ledger record (keyed by PMID) — `diseases` is an append-only tag list, `chunk_count`/`embedded_at` describe the AstraDB-side state. |
| `errors.py` | `ErrorCode` (enum), `ErrorDetail`, `ErrorResponse` | The closed set of error codes the API can return (auth, documents, chat, voice) and the JSON envelope shape — see [doc 02](02_api_core.md#apierrorspy). |

## Repositories (`shared/repositories/`)

One module per Firestore collection. Every read that takes a `uid` refuses to
return another user's data — the authorization boundary for user-owned data
lives here, not just at the API route layer.

### `repositories/documents.py`
Backs the `documents` collection. The biggest repository — owns both the
create/read/list path and the worker-facing state-transition path.
- `create_document_with_files(uid, domain, title, file_specs, idempotency_key, object_path_builder)` — mints a `doc_{uuid}` id, builds per-file records via the caller-supplied `object_path_builder` (keeps this module ignorant of GCS path layout), writes status `pending_upload`.
- `find_document_for_user(document_id, uid)` — read scoped to owner + not soft-deleted.
- `find_document_by_idempotency_key(uid, idempotency_key)` — backs `POST /documents`'s idempotent-retry behavior.
- `list_documents_for_user(uid, domain=, status=, limit=, cursor=)` / `decode_cursor(cursor)` — cursor-based pagination (base64 of `{created_at, id}`), newest first.
- `mark_uploaded(document_id, uid, uploaded_file_ids)` — Firestore **transaction**; `pending_upload → uploaded`, stamps `upload_completed_at` per file, refuses (`DocumentStateError`) from any other status.
- `soft_delete(document_id, uid)` — transaction; sets `deleted_at`, refuses while `processing`.
- `update_status`, `update_processing_step`, `update_cypher_uri`, `update_graph_queries` — worker-side writes as the pipeline progresses (see [doc 05](05_workers_pipeline.md)).
- `pending_files(document)` — files without `upload_completed_at` yet.
- `DocumentStateError` — raised when a transition is attempted from an incompatible status; carries `.current_status`.

### `repositories/extractions.py`
Backs the `extractions` collection (one per document, keyed by `doc_id`).
- `save_extraction(extraction)` — upserts both legacy OCR fields and current LLM fields; truncates `raw_text` to 200K chars if present.
- `get_extraction(doc_id)` — returns `None` if not found; old records missing the newer LLM fields deserialize fine since those fields are optional.

### `repositories/journey_summaries.py`
Backs the `journey_summaries` collection (one per user, keyed by `uid`).
- `get_summary(uid)` — returns `None` if the user has no prior summary.
- `upsert_summary(uid, summary_text, last_extraction_id)` — Firestore **transaction**; makes `document_count`'s increment race-safe across concurrent documents for the same user. The summary text itself is last-writer-wins by design (see [doc 05](05_workers_pipeline.md) for the trade-off).

### `repositories/users.py`
Backs the `users` collection (keyed by Firebase UID).
- `create_user_profile(uid, email, first_name, last_name)`.
- `get_user_profile(uid)` — returns `None` if not found (e.g. a user created directly in the Firebase Console, bypassing `/auth/signup`).

### `repositories/literature_papers.py`
Backs the `literature_papers` collection — global (not per-user) dedup ledger for the scraper subsystem.
- `get_paper(pmid)`.
- `get_indexed_pmids(pmids)` — one batched `get_all` read rather than N round-trips.
- `record_paper(pmid, doi=, title=, disease=, chunk_count=, full_text=, source=)` — transaction; first sight writes the full record, later sights only append to `diseases` (`ArrayUnion`) without touching `chunk_count`/`embedded_at` (the vectors aren't re-created).
