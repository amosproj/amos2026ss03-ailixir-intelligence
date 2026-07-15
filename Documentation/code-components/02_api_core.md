# 02 — API Core (`Backend/api/`)

The top-level files of the API service — app wiring, auth, error handling,
request tracing, and the two route modules that aren't inlined in `main.py`.
The RAG internals `chat.py`/`voice.py` call into live in
[`chat_pipeline/`](03_api_chat_pipeline.md).

## `api/main.py`

**Purpose:** The FastAPI app itself, plus the `/auth` and `/documents`
endpoints (defined inline rather than in their own router modules, since
their request/response Pydantic models sit right above them in the same
file).

**App wiring:**
- `lifespan()` — optional Graphiti warmup on startup (`CHAT_GRAPHITI_WARMUP=true`), best-effort close on shutdown.
- Middleware order: `RequestIDMiddleware` then `CORSMiddleware`.
- Exception handlers registered for `APIError`, `StarletteHTTPException`, `RequestValidationError`, and bare `Exception` (all from `api/errors.py`).
- Routers mounted: `chat_router` (prefix `/chat`), `voice_router` (prefix `/voice`).
- `custom_openapi()` — decorates the auto-generated OpenAPI schema so Swagger's Authorize dialog shows a useful description for the bearer-token scheme.

**Auth endpoints:**
- `POST /auth/signup` — creates the Firebase Auth user + Firestore `UserProfile` as a manual saga (compensating delete of the Auth user if the Firestore write fails). See [doc 03 architecture](../architecture/03_api_service_architecture.md#auth-apiauthpy) for the sequence.
- `GET /me` — returns the caller's `UserProfile` (404 if missing).

**Documents endpoints** (all behind `get_current_user`):
- `POST /documents` — creates a `Document` + per-file records, returns signed upload URLs. Honors an `Idempotency-Key` header (`_create_response_from_existing` replays a prior response with fresh URLs for still-pending files).
- `POST /documents/{id}/finalize` — verifies files landed in GCS (parallel `gcs.verify_object_exists`), transitions to `uploaded`, publishes `DocumentUploaded`.
- `POST /documents/{id}/upload-urls/refresh` — reissues signed URLs for files that haven't uploaded yet (for uploads that outlived the URL TTL).
- `GET /documents` — paginated list (`limit`, `cursor`, `domain`, `status` filters).
- `GET /documents/{id}` — full detail incl. per-file download URLs and (once extracted) a signed `cypher_download_url`.
- `GET /documents/{id}/extraction` — the `Extraction` record; three distinct 4xx codes depending on whether the document is missing, not yet extracted, or (a pipeline bug) extracted with no record.
- `DELETE /documents/{id}` — soft delete; 409s if `processing`.

**Notable private helpers:** `_sanitize_filename` (strips path components/control chars/unicode lookalikes), `_upload_headers_for`/`_make_upload_instruction` (signed-URL response shaping), `_to_document_response`/`_to_list_item` (Firestore model → API response mapping, including building the signed cypher download URL).

## `api/auth.py`

**Purpose:** Firebase identity — token verification for every authenticated
route, plus the two Admin SDK calls signup needs.
- `get_current_user(creds)` — FastAPI dependency (`Depends`); verifies the bearer ID token via `firebase_admin.auth.verify_id_token`, returns `{uid, email, name, email_verified}`. Maps `ExpiredIdTokenError`/`RevokedIdTokenError`/`UserDisabledError`/`InvalidIdTokenError` each to a `401` with a distinct message; infra-level verification failures propagate as `500` (not an auth failure — retrying the same token won't help).
- `create_firebase_user(email, password, display_name)` → uid.
- `delete_firebase_user(uid)` — the compensating action used by `/auth/signup`.

## `api/errors.py`

**Purpose:** Structured error responses — see
[doc 03 architecture](../architecture/03_api_service_architecture.md#error-model-apierrorspy)
for the full table of handlers.
- `APIError(HTTPException)` — carries a domain `ErrorCode` alongside the HTTP status; this is what route code raises directly.
- `api_error_handler`, `http_exception_handler`, `validation_error_handler`, `unhandled_exception_handler` — one handler per exception type FastAPI can surface; all funnel through `_envelope()` to produce the same `{error: {code, message, request_id}}` JSON shape.
- `_resolve_request_id(request)` — prefers `request.state.request_id` (survives even the outermost `ServerErrorMiddleware`), falls back to the `middleware.py` contextvar.

## `api/middleware.py`

**Purpose:** Per-request id propagation for tracing.
- `RequestIDMiddleware` — pure ASGI (not `BaseHTTPMiddleware` — see the module docstring / [doc 03 architecture](../architecture/03_api_service_architecture.md#middleware-request-id-propagation-apimiddlewarepy) for why that distinction matters for `ContextVar` inheritance into exception handlers). Honors a client-supplied `X-Request-ID` (capped 64 chars) or mints `req_<16 hex>`; writes it into both the ASGI `scope["state"]` and a `ContextVar`, and echoes it back as a response header.
- `request_id_var` — the `ContextVar[str]`, default `""` so log records emitted outside a request don't `KeyError`.
- `RequestIDLogFilter` — a `logging.Filter` that injects the current request id into every log record as `%(request_id)s`.

## `api/chat.py`

**Purpose:** `POST /chat/query` — the mobile client's chat endpoint. Wires
together the three [chat_pipeline](03_api_chat_pipeline.md) steps plus the
concurrent title-generation and paper-retrieval tasks, and translates every
pipeline failure mode into one of the granular `CHAT_*` error codes. Full
walkthrough in [doc 02 architecture](../architecture/02_question_answering_pipeline.md).
- `ChatMessage`, `ChatQueryRequest`, `ChatQueryResponse` — the request/response Pydantic models (history capped at 20 turns, query capped at 2000 chars).
- `chat_query(payload, user)` — the route handler.
- `_maybe_start_title(payload, uid)` — launches best-effort title generation as a tracked `asyncio.Task` on the first turn of a chat.
- `_title_tasks`, `_paper_tasks` — module-level `set[asyncio.Task]` holding strong references so fire-and-forget tasks (title generation, paper retrieval when the graph arm fails first) aren't garbage-collected mid-flight — `asyncio` only holds a *weak* reference to a bare `create_task`.

## `api/voice.py`

**Purpose:** `POST /voice/v1/chat/completions` — an OpenAI-Chat-Completions-shaped
adapter so ElevenLabs' Conversational AI can use the same pipeline as a
"Custom LLM." See [doc 02 architecture](../architecture/02_question_answering_pipeline.md#voice-the-same-pipeline-behind-an-openai-compatible-adapter-apivoicepy)
for the full contract and why it differs from `chat.py`.

*Future work — deployed, but not exercised by any live caller.*
- `VoiceChatCompletionRequest` / `_VoiceMessage` — permissive (`extra="allow"`) models matching the OpenAI wire shape, since ElevenLabs' exact field set for dynamic variables isn't consistently documented.
- `_verify_shared_secret(authorization)` — fails closed if `ELEVENLABS_CUSTOM_LLM_SECRET` is unset; otherwise constant-time-compares (`secrets.compare_digest`) the bearer token.
- `_extract_uid(payload, header_uid)` — resolves the patient's Firebase UID, checking the configured header first, then a list of plausible dynamic-variable body locations; returns `(uid, source)` so the matching path is visible in logs.
- `_messages_to_query_and_history(messages)` — splits OpenAI-style messages into `(latest user query, prior turns)`, dropping system messages.
- `_run_pipeline(uid, query, history)` — `contextualize → retrieve → answer`, degrading to a fixed apologetic sentence on any failure instead of raising (no paper-retrieval arm, no title generation).
- `_stream_answer` / `_completion_json` / `_sse_event` / `_completion_id` — OpenAI-compatible response framing (SSE or plain JSON depending on `payload.stream`).
- `voice_chat_completions(request, payload, authorization)` — the route handler.
