# Ailixir API — Frontend Integration Guide

- **Base URL (production):** `https://ailixir-backend-599892675013.us-east1.run.app`
- **Auth scheme:** Firebase ID token in `Authorization: Bearer <token>` header on every request except `/health`, `/auth/signup`, and (a separate mechanism entirely — see §5) `/voice/*`
- **OpenAPI / Swagger UI:** `<base>/docs` (interactive; click **Authorize** at the top right, paste the ID token without the `Bearer ` prefix, then any "Try it out" call works)
- **Content type:** all API requests and responses are `application/json` unless noted
- **Files allowed:** `application/pdf`, `image/png`, `image/jpeg`
- **Domains allowed:** `medical`, `finance`
- **Limits:** 50 files per document, 20 MB per file, 200 MB per document total

This guide covers every route the API exposes: Auth, Documents (§3), Chat
(§4), and Voice (§5). For *why* things are built this way, see
[`Documentation/architecture/`](../architecture/README.md); for a quick
task-oriented walkthrough instead of a full reference, see
[`Documentation/running-the-project/`](../running-the-project/README.md).

---

## 1. The mental model

Document uploads are a **three-step handshake**, not a single multipart POST. The API never receives file bytes; it only mints time-limited signed URLs that let the client upload directly to Google Cloud Storage. This is on purpose - keeps the API stateless and cheap, lets uploads scale to phone uploads on bad networks without holding the API hostage.

```
┌────────┐  1. POST /documents          ┌────────┐
│ Client │ ───────────────────────────▶ │  API   │
│ (RN)   │ ◀─────────────────────────── │        │   returns signed URLs
└────────┘   signed PUT URLs            └────────┘
     │
     │  2. PUT bytes directly to each signed URL
     ▼
┌─────────────────────┐
│  Google Cloud       │
│  Storage (bucket)   │
└─────────────────────┘
     ▲
     │
┌────────┐  3. POST /documents/{id}/finalize
│ Client │ ───────────────────────────▶  API verifies bytes exist
│ (RN)   │                                publishes event for worker
└────────┘
```

Three rules drop out of this:

1. **Headers on the PUT must match exactly** what `upload_headers` told you. GCS rejects any mismatch with `403`.
2. **Each signed URL is single-use.** A second PUT to the same URL returns `412 Precondition Failed`. If a file upload genuinely failed mid-flight, call `POST /documents/{id}/upload-urls/refresh` to get fresh URLs for the still-pending files.
3. **Finalize is the trigger.** Until you call `/finalize`, the document stays in `pending_upload` and no AI worker sees it.

Chat (§4) and voice (§5) don't follow this handshake at all — they're plain synchronous JSON requests that return a complete answer.

---

## 2. Authentication

### How the user gets a token

Sign-up is one backend call. **Sign-in is NOT a backend call** - the mobile app talks to Firebase Auth directly and asks Firebase for an ID token. The backend then verifies that token on every request.

```
┌─────────────┐                           ┌──────────────┐
│   Mobile    │  signInWithEmailPassword  │  Firebase    │
│             │ ─────────────────────────▶│  Auth        │
│             │ ◀──────────── ID token ── │              │
└─────────────┘                           └──────────────┘
       │
       │  Authorization: Bearer <token>
       ▼
┌─────────────┐
│  Backend    │  ← verifies token
└─────────────┘
```

### Tokens expire after **1 hour**

Firebase ID tokens are short-lived. The Firebase SDK refreshes them automatically when you call `getIdToken()`. **Always re-fetch the token before each request batch**, don't cache it for the whole session:

If you hit `401 TOKEN_EXPIRED`, force-refresh with `getIdToken(true)` and retry once. Don't loop.

---

## 3. Documents API

Every authenticated endpoint accepts and emits JSON, requires `Authorization: Bearer <id_token>`, and returns errors in the same envelope (see §6).

### 3.1 `GET /health`

Liveness probe. No auth.

```bash
curl https://ailixir-backend-599892675013.us-east1.run.app/health
```

Response **200**:

```json
{ "status": "ok" }
```

---

### 3.2 `POST /auth/signup`

Create a new account. Creates the Firebase Auth user **and** the Firestore profile atomically — if either step fails, the other is rolled back.

After this returns, the client should call Firebase Auth's `signInWithEmailAndPassword` to obtain an ID token.

**Request body:**

| Field        | Type   | Required | Notes                                  |
|--------------|--------|----------|-----------------------------------------|
| `email`      | string | yes      | Valid email format                     |
| `password`   | string | yes      | 8–128 chars, no composition rules      |
| `first_name` | string | yes      | 1–50 chars, trimmed, non-empty         |
| `last_name`  | string | yes      | 1–50 chars, trimmed, non-empty         |

**Response 201:**

```json
{
  "uid": "QkF2eVbZN6V5h8Mz3jK1pXrL2nGy",
  "email": "abdul@example.com",
  "first_name": "Abdul",
  "last_name": "Haseeb"
}
```

**Errors:**

| HTTP | `code`                  | When                                |
|------|-------------------------|--------------------------------------|
| 409  | `EMAIL_ALREADY_EXISTS`  | Email is already registered         |
| 422  | `VALIDATION_FAILED`     | Field validation failed             |
| 400  | `VALIDATION_FAILED`     | Firebase rejected the password etc. |

```bash
curl -X POST https://ailixir-backend-599892675013.us-east1.run.app/auth/signup \
  -H 'Content-Type: application/json' \
  -d '{
    "email": "abdul@example.com",
    "password": "SuperStrong2026",
    "first_name": "Abdul",
    "last_name": "Haseeb"
  }'
```

---

### 3.3 `GET /me`

Returns the authenticated user's profile.

**Headers:** `Authorization: Bearer <token>`

**Response 200:**

```json
{
  "uid": "QkF2eVbZN6V5h8Mz3jK1pXrL2nGy",
  "email": "abc@example.com",
  "first_name": "abc",
  "last_name": "xyz",
  "created_at": "2026-05-20T14:23:11.482Z",
  "updated_at": "2026-05-20T14:23:11.482Z"
}
```

**Errors:**

| HTTP | `code`                    | When                                                  |
|------|----------------------------|--------------------------------------------------------|
| 401  | `UNAUTHENTICATED`         | Missing / invalid / expired token                     |
| 404  | `USER_PROFILE_NOT_FOUND`  | Firebase user exists but Firestore profile missing    |

---

### 3.4 `POST /documents` — create document, get upload URLs

This is step 1 of the upload flow. You describe the document and its files; the API returns one signed PUT URL per file.

**Headers:**

- `Authorization: Bearer <token>`
- `Idempotency-Key: <client-generated-uuid>` *(optional but recommended - see §3.4.1)*

**Request body:**

| Field   | Type     | Required | Notes                                                  |
|---------|----------|----------|----------------------------------------------------------|
| `domain` | string  | yes      | `medical` or `finance`                                 |
| `title`  | string  | no       | ≤ 200 chars, trimmed                                   |
| `files`  | array   | yes      | 1–50 entries                                           |
| `files[].file_name`    | string | yes | 1–512 chars; backend sanitises (strips path chars)     |
| `files[].content_type` | string | yes | `application/pdf` \| `image/png` \| `image/jpeg`       |
| `files[].size_bytes`   | int    | yes | Real byte size of the file (≤ 20 MB)                   |

Example:

```json
{
  "domain": "medical",
  "title": "Blood report — May 2026",
  "files": [
    { "file_name": "page1.pdf", "content_type": "application/pdf", "size_bytes": 124530 },
    { "file_name": "page2.pdf", "content_type": "application/pdf", "size_bytes": 98112 }
  ]
}
```

**Response 201:**

```json
{
  "document_id": "doc_a1b2c3d4e5f6g7h8i9j0",
  "status": "pending_upload",
  "domain": "medical",
  "title": "Blood report — May 2026",
  "file_count": 2,
  "total_bytes": 222642,
  "created_at": "2026-05-20T14:30:00.000Z",
  "files": [
    {
      "file_id": "f_4f2649386da045e3b358ead543122a87",
      "file_name": "page1.pdf",
      "content_type": "application/pdf",
      "size_bytes": 124530,
      "upload_method": "PUT",
      "upload_url": "https://storage.googleapis.com/ailixir-documents-amos26/users/.../page1.pdf?X-Goog-Algorithm=...",
      "upload_headers": {
        "Content-Type": "application/pdf",
        "x-goog-content-length-range": "0,124530",
        "x-goog-if-generation-match": "0"
      },
      "upload_expires_at": "2026-05-20T14:45:00.000Z"
    },
    { "file_id": "f_bc2fa433...", "...": "..." }
  ]
}
```

**Crucial:** copy `upload_headers` **verbatim** onto the PUT - don't add, omit, or reorder. The signature was computed over exactly these headers.

**Errors:**

| HTTP | `code`                | When                                            |
|------|-----------------------|---------------------------------------------------|
| 401  | `UNAUTHENTICATED`     | Token problem                                   |
| 422  | `VALIDATION_FAILED`   | Bad field (unknown domain, bad size, …)         |
| 413  | `TOTAL_SIZE_EXCEEDED` | Sum of `size_bytes` > 200 MB                    |

#### 3.4.1 Idempotency-Key

Optional client-generated string (UUID is fine), ≤ 128 chars. If you set it and retry the same request with the **same key + same user**, the API returns the original document (with fresh signed URLs for any files still pending) instead of creating a duplicate. Stored for 24 hours.

Use it whenever you might retry: weak network, app foreground re-entry, etc. Generate a new key per logical "user pressed upload" event, not per HTTP retry.

---

### 3.5 PUT to each `upload_url` - upload the actual bytes

This request goes to **`storage.googleapis.com`, not the API.** Send:

- HTTP method: `PUT` (or whatever `upload_method` says)
- URL: `upload_url` from the response
- Body: the raw file bytes
- Headers: **exactly** `upload_headers`

```bash
curl -X PUT "$UPLOAD_URL" \
  -H "Content-Type: application/pdf" \
  -H "x-goog-content-length-range: 0,124530" \
  -H "x-goog-if-generation-match: 0" \
  --data-binary @page1.pdf
```

**Success:** HTTP `200` (no JSON body). Move on to the next file.

**Failure modes you should handle:**

| HTTP | Meaning                                             | What to do                                              |
|------|-------------------------------------------------------|------------------------------------------------------------|
| 400  | Body bigger than the declared `size_bytes`          | Bug in client — `size_bytes` you declared was wrong     |
| 403  | Wrong header / content-type / URL tampered with     | Bug — re-create document with correct metadata          |
| 412  | File already uploaded (write-once)                  | Skip; that file is done                                 |
| 5xx  | GCS transient                                       | Retry the same PUT (idempotent)                         |

If the signed URL expired (15 min default), call `POST /documents/{id}/upload-urls/refresh` (§3.7).

---

### 3.6 `POST /documents/{document_id}/finalize`

After all PUTs succeed, call finalize. The API verifies each file exists in GCS (HEAD check), marks the document as `uploaded`, and publishes a `DocumentUploaded` event for the worker.

**Headers:** `Authorization: Bearer <token>`
**Body:** empty (or `{}`)

**Response 200:** same shape as §3.8 (`DocumentResponse`), with `status: "uploaded"` and download URLs populated.

**Errors:**

| HTTP | `code`                       | When                                                      |
|------|-------------------------------|--------------------------------------------------------------|
| 400  | `NO_FILES_UPLOADED`          | No files actually present in GCS — did the PUTs succeed?  |
| 404  | `DOCUMENT_NOT_FOUND`         | Wrong id, or belongs to another user                      |
| 409  | `DOCUMENT_ALREADY_FINALIZED` | Already finalized (idempotent retry safety net)           |

**Tolerance:** partial uploads are accepted. If you uploaded 4 of 5 files and finalize, the document goes `uploaded` with 4 files marked complete and 1 still pending. The pending one can never be re-uploaded — design your UX so partial finalizes are an explicit user choice, not an accident.

---

### 3.7 `POST /documents/{document_id}/upload-urls/refresh`

Get fresh signed URLs for any files in this document that haven't been uploaded yet. Use when the original URLs expired (15 min TTL) before the upload finished.

**Headers:** `Authorization: Bearer <token>`
**Body:** empty

**Response 200:**

```json
{
  "document_id": "doc_a1b2c3d4e5f6g7h8i9j0",
  "status": "pending_upload",
  "files": [
    {
      "file_id": "f_bc2fa433...",
      "file_name": "page2.pdf",
      "content_type": "application/pdf",
      "size_bytes": 98112,
      "upload_method": "PUT",
      "upload_url": "https://storage.googleapis.com/...",
      "upload_headers": { "...": "..." },
      "upload_expires_at": "2026-05-20T15:00:00.000Z"
    }
  ]
}
```

Returned `files` only includes those still pending. Already-uploaded files are immutable (write-once) and absent from the response.

**Errors:**

| HTTP | `code`                       | When                                  |
|------|-------------------------------|-----------------------------------------|
| 404  | `DOCUMENT_NOT_FOUND`         | Wrong id                              |
| 409  | `DOCUMENT_ALREADY_FINALIZED` | Document is no longer `pending_upload`|

---

### 3.8 `GET /documents/{document_id}` — read one document with download URLs

**Headers:** `Authorization: Bearer <token>`

**Response 200:**

```json
{
  "document_id": "doc_a1b2c3d4e5f6g7h8i9j0",
  "status": "extracted",
  "domain": "medical",
  "title": "Blood report — May 2026",
  "file_count": 2,
  "total_bytes": 222642,
  "created_at": "2026-05-20T14:30:00.000Z",
  "updated_at": "2026-05-20T14:32:30.000Z",
  "finalized_at": "2026-05-20T14:32:14.000Z",
  "processing_step": "exporting_cypher",
  "cypher_gcs_uri": "gs://ailixir-cypher-amos26/graphs/doc_a1b2c3d4e5f6g7h8i9j0_graph.cypher",
  "cypher_download_url": "https://storage.googleapis.com/.../doc_a1b2c3..._graph.cypher?X-Goog-Algorithm=...",
  "cypher_download_expires_at": "2026-05-20T14:47:30.000Z",
  "graph_query": "MATCH (n:Entity)-[r]-(m:Entity) WHERE n.group_id = '...' RETURN n, r, m",
  "entities_query": "MATCH (ep:Episodic {name: '...', group_id: '...'})-[r]-(n:Entity) RETURN ep.name AS document, n.name AS entity, labels(n) AS entity_type ORDER BY ep.name",
  "error": null,
  "files": [
    {
      "file_id": "f_4f2649386da045e3b358ead543122a87",
      "file_name": "page1.pdf",
      "content_type": "application/pdf",
      "size_bytes": 124530,
      "upload_completed_at": "2026-05-20T14:31:02.000Z",
      "download_url": "https://storage.googleapis.com/.../page1.pdf?X-Goog-Algorithm=...",
      "download_expires_at": "2026-05-20T14:47:14.000Z"
    },
    { "...": "..." }
  ]
}
```

**File-level fields:**

- `download_url` is a signed GET URL — open it directly (Image component, PDF viewer, browser, etc.). It expires after **15 minutes**; re-fetch the document to get a new one. Don't cache a download URL beyond that.
- Files that haven't completed upload have `download_url: null` and `upload_completed_at: null`.

**Document-level worker fields** (populated by the AI pipeline after finalize):

- `processing_step` — fine-grained progress within the worker pipeline while `status == processing`. One of: `downloading`, `analyzing`, `saving_extraction`, `building_graph`, `updating_summary`, `exporting_cypher`. Useful for a progress UI. Stays at the final step (`exporting_cypher`) once `status == extracted`. See §3.12 for the polling pattern and the friendly-label mapping.
- `cypher_gcs_uri` — set once `status == extracted`. The raw `gs://` URI of the Cypher script the worker generated, kept for tooling that consumes it directly.
- `cypher_download_url` / `cypher_download_expires_at` — a short-lived (15 min) signed **HTTPS** URL for the same file — this is what the frontend should actually fetch; `null` until extraction completes or if signing fails.
- `graph_query` / `entities_query` — ready-to-run Cypher for Neo4j Browser: `graph_query` returns the patient's whole entity graph, `entities_query` scopes to just this document's episode. Both `null` until `status == extracted`. See the note in §10 about these being built with string interpolation of LLM-derived values — treat as read-only convenience queries, not something to build further server-side logic on top of.
- `error` — set when `status == failed`. May contain raw worker error text (database names, exception traces). **Do not display verbatim to end users.** Show a generic failure UI; surface this to support along with the response's `X-Request-ID` header.

**Errors:**

| HTTP | `code`               | When                                           |
|------|-----------------------|---------------------------------------------------|
| 404  | `DOCUMENT_NOT_FOUND` | Wrong id, soft-deleted, or owned by another user |

---

### 3.9 `GET /documents` — paginated list

Newest documents first. Returns a thumbnail URL (signed GET URL for the first completed file) but no full file URLs — call §3.8 to get those.

**Query parameters:**

| Param    | Type   | Notes                                                                  |
|----------|--------|----------------------------------------------------------------------------|
| `limit`  | int    | 1–100, default 50                                                      |
| `cursor` | string | Opaque pagination cursor; pass back what previous `next_cursor` gave   |
| `domain` | string | Filter to `medical` or `finance`                                       |
| `status` | string | One of `pending_upload`, `uploaded`, `processing`, `extracted`, `failed` |

**Response 200:**

```json
{
  "documents": [
    {
      "document_id": "doc_a1b2c3...",
      "status": "uploaded",
      "domain": "medical",
      "title": "Blood report — May 2026",
      "file_count": 2,
      "total_bytes": 222642,
      "created_at": "2026-05-20T14:30:00.000Z",
      "updated_at": "2026-05-20T14:32:14.000Z",
      "finalized_at": "2026-05-20T14:32:14.000Z",
      "thumbnail_url": "https://storage.googleapis.com/.../page1.pdf?...",
      "thumbnail_expires_at": "2026-05-20T14:47:14.000Z"
    }
  ],
  "next_cursor": "eyJjcmVhdGVkX2F0Ijo..."
}
```

`next_cursor: null` means you reached the end. When paginating, **always pass back the cursor unchanged** — it's opaque; don't try to parse it.

**Note:** the list response intentionally **does not** include `processing_step`, `cypher_gcs_uri`, or `error` — these only appear on `GET /documents/{id}` (§3.8). The list view is optimised to render quickly; if you need extraction details for an individual document, call the single-doc endpoint when the user taps it.

**Errors:**

| HTTP | `code`                       | When                          |
|------|--------------------------------|----------------------------------|
| 422  | `INVALID_DOMAIN`             | Unknown domain in filter      |
| 422  | `INVALID_PAGINATION_CURSOR`  | Malformed cursor              |

---

### 3.10 `GET /documents/{document_id}/extraction` — read the extraction record

Returns the structured result of the AI pipeline: the clinical narrative and
classification the LLM produced. Only meaningful once `status == extracted`
(see §3.8).

**Headers:** `Authorization: Bearer <token>`

**Response 200:**

```json
{
  "doc_id": "doc_a1b2c3d4e5f6g7h8i9j0",
  "document_type": "Laborbericht",
  "confidence_score": null,
  "extracted_fields": {},
  "raw_text": null,
  "raw_text_chars": null,
  "raw_text_truncated": null,
  "document_purpose": "Routine blood work follow-up for an existing prostate cancer diagnosis.",
  "document_date": "2026-05-18",
  "episode_body": "Patient-1 (DOB 1961-04-02) presented for routine lab work... PSA 4.2 ng/ml (ref 0-4.0), elevated from 7.6 ng/ml on 2026-01-10...",
  "extracted_at": "2026-05-20T14:32:26.000Z"
}
```

**Two field groups, only one populated per document, depending on which
pipeline processed it:**

- **Current (Gemini-multimodal) pipeline** — populates `document_purpose`,
  `document_date`, `episode_body` (the rich clinical narrative — this is
  what should drive any "document narrative" card in the UI). `confidence_score`,
  `extracted_fields`, `raw_text*` are `null`.
- **Legacy (Document AI OCR) pipeline** — only present on documents
  extracted before the migration to Gemini multimodal; populates
  `confidence_score`, `extracted_fields`, `raw_text*` instead. New uploads
  never produce these fields — treat them as optional and render whichever
  set is actually present.

**Errors:**

| HTTP | `code`                  | When                                                                                          |
|------|--------------------------|--------------------------------------------------------------------------------------------------|
| 404  | `DOCUMENT_NOT_FOUND`    | Wrong id, or belongs to another user (same code as §3.8 on purpose — can't be used to probe existence of another user's documents) |
| 409  | `DOCUMENT_NOT_EXTRACTED`| Document exists but the worker hasn't reached `extracted` yet — keep polling §3.8 instead        |
| 404  | `EXTRACTION_NOT_FOUND`  | `status == extracted` but no extraction record exists — this indicates a backend bug, worth reporting |

---

### 3.11 `DELETE /documents/{document_id}` — soft delete

Marks the document deleted. It disappears from `/documents` listings immediately. A background reconciliation job eventually hard-deletes the GCS objects (we don't expose that timing — treat it as "gone forever from the user's perspective").

**Headers:** `Authorization: Bearer <token>`

**Response 204:** empty body, success.

**Errors:**

| HTTP | `code`                  | When                                                       |
|------|---------------------------|------------------------------------------------------------|
| 404  | `DOCUMENT_NOT_FOUND`    | Wrong id                                                   |
| 409  | `DOCUMENT_IN_PROCESSING` | Worker is mid-extraction; poll & retry in a few seconds   |

---

### 3.12 Polling for extraction status

After `POST /finalize` returns `200`, the worker pipeline runs **automatically and asynchronously** — there's no second API call to trigger it. Typical end-to-end extraction time is **~15-25 seconds** for a small PDF; can be longer for large/multi-file documents.

The frontend should poll `GET /documents/{id}` and watch two fields:

- **`status`** — terminal when it reaches `extracted` or `failed`.
- **`processing_step`** — fine-grained progress while `status == processing`, useful for a progress UI.

#### Recommended polling loop

```ts
// Status values returned by the API. Use this as a switch in the UI.
type DocumentStatus =
  | "pending_upload"  // before finalize
  | "uploaded"        // finalize succeeded, worker hasn't picked up yet (usually < 1s)
  | "processing"      // worker is running the pipeline
  | "extracted"       // ✅ terminal: cypher_gcs_uri is populated
  | "failed";         // ❌ terminal: error is populated

type ProcessingStep =
  | "downloading"          // fetching files from GCS
  | "analyzing"            // Gemini multimodal reads the document
  | "saving_extraction"    // writing the extraction to Firestore
  | "building_graph"       // Graphiti extracts entities/relationships into Neo4j
  | "updating_summary"     // updating the patient's running journey summary
  | "exporting_cypher";    // serialising the graph as a Cypher script

const TERMINAL = new Set<DocumentStatus>(["extracted", "failed"]);
const POLL_INTERVAL_MS = 2_000;     // 2 seconds is a good balance
const POLL_TIMEOUT_MS = 5 * 60_000; // give up after 5 minutes

async function pollUntilDone(documentId: string): Promise<Document> {
  const start = Date.now();
  while (Date.now() - start < POLL_TIMEOUT_MS) {
    const doc = await getDocument(documentId);   // your existing GET /documents/{id} caller
    updateProgressUI(doc.status, doc.processing_step);
    if (TERMINAL.has(doc.status)) return doc;
    await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
  }
  throw new Error(`Extraction did not finish within ${POLL_TIMEOUT_MS / 1000}s`);
}
```

#### Friendly labels for `processing_step`

Use this mapping so the UI is consistent across screens:

| `processing_step`     | UI label                          |
|-------------------------|---------------------------------------|
| (null, before worker) | "Queued for processing…"          |
| `downloading`         | "Preparing your document…"        |
| `analyzing`           | "Reading the document…"           |
| `saving_extraction`   | "Saving extracted data…"          |
| `building_graph`      | "Building the knowledge graph…"   |
| `updating_summary`    | "Updating patient summary…"       |
| `exporting_cypher`    | "Finalising…"                     |


### Exact UI flow to wire up

```typescript
User taps upload                  →  show upload progress bar
Upload completes                  →  call /finalize
Finalize returns 200              →  start polling, show "Processing your document…"
Status = processing               →  show processing_step in UI ("Reading document…", "Building graph…")
Status = extracted                →  show result, offer chat, link to cypher_download_url
Status = failed                   →  show error UI
```

#### Things to know

- **Don't start polling before `/finalize` returns.** Until then, the worker has no event to act on.
- **The `uploaded` state is real but usually invisible** — the worker picks up the Pub/Sub event in well under 1 second. Your loop may never observe it. That's fine; treat it the same as `processing`.
- **`processing_step` is fine-grained, not strictly ordered.** Always trust `status` first; only show step-level UI while `status == processing`.
- **The `extracted` status keeps `processing_step == "exporting_cypher"`** because that was the last step the worker wrote. Don't treat the step's value as authoritative once status is terminal — switch to `status`-driven UI.
- **Idempotency-Key applies only to `POST /documents`** — calling `GET /documents/{id}` in a loop is naturally safe (no side effects).

---

## 4. Chat API

`POST /chat/query` — ask a natural-language question about the authenticated
user's own uploaded documents. Runs synchronously (no polling needed) and
answers from a combination of the patient's knowledge graph and, optionally,
general research-paper reference material. Full pipeline explanation in
[`architecture/02_question_answering_pipeline.md`](../architecture/02_question_answering_pipeline.md).

**Headers:** `Authorization: Bearer <token>`, `Content-Type: application/json`

**Request body:**

| Field     | Type   | Required | Notes                                                                 |
|-----------|--------|----------|----------------------------------------------------------------------|
| `query`   | string | yes      | 1–2000 chars — the user's latest message                             |
| `history` | array  | no       | Prior turns, chronological order, max 20; each `{role, content}`      |
| `history[].role` | string | — | `"user"` or `"assistant"`                                          |
| `history[].content` | string | — | 1–4000 chars                                                    |
| `chat_id` | string \| null | no | ≤128 chars. Opaque Realtime-DB chat id. If present **and** `history` is empty, this is treated as the first turn of a chat and a background title-generation task is scheduled. |

Example — first turn of a new chat:

```bash
curl -s -X POST "$API/chat/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "What medications is the patient currently on?",
    "history": [],
    "chat_id": "chat_abc123"
  }'
```

Example — a follow-up turn (note pronoun "its" — this is what §4's contextualizer step resolves):

```bash
curl -s -X POST "$API/chat/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "What about its side effects?",
    "history": [
      {"role": "user", "content": "What medications is the patient currently on?"},
      {"role": "assistant", "content": "The patient is currently prescribed Tamoxifen 20mg daily."}
    ],
    "chat_id": "chat_abc123"
  }'
```

**Response 200:**

```json
{
  "answer": "The patient is currently prescribed Tamoxifen 20mg daily. Common side effects include...",
  "contextualized_query": "What are the side effects of Tamoxifen?",
  "query_changed": true,
  "facts_used": 3,
  "entities_used": 4,
  "papers_used": 1,
  "title_generation_scheduled": true
}
```

| Field | Meaning |
|---|---|
| `answer` | The natural-language answer to render |
| `contextualized_query` | The query actually used for retrieval — may differ from `query` if it was rewritten against `history` |
| `query_changed` | `true` if the contextualizer rewrote the query (useful for debug UI / analytics, not required for rendering) |
| `facts_used` / `entities_used` | How many knowledge-graph facts/entities backed the answer — 0 doesn't mean failure, it means nothing relevant was found in the graph |
| `papers_used` | Reranked research-paper excerpts used, if any — 0 means the answer came from the knowledge graph alone (this arm degrades silently, it's not an error signal) |
| `title_generation_scheduled` | `true` if a background task was kicked off to auto-title this chat in Realtime Database — purely informational, the client observes the title through its existing RTDB subscription a moment later, no action needed here |

**Errors** — see the full table in §6; the chat-specific codes are:

| HTTP | `code` | Retry? |
|---|---|---|
| 504 | `CHAT_RETRIEVAL_TIMEOUT` | Yes, with backoff |
| 503 | `CHAT_NEO4J_UNAVAILABLE` | Yes, with backoff |
| 503 | `CHAT_RATE_LIMITED` | Yes, with backoff |
| 503 | `CHAT_RETRIEVAL_FAILED` | Yes, with backoff |
| 504 | `CHAT_LLM_TIMEOUT` | Yes, longer backoff |
| 503 | `CHAT_LLM_EMPTY` | **No** — ask the user to rephrase instead |
| 503 | `CHAT_LLM_FAILED` | Yes, with backoff |

---

## 5. Voice API (ElevenLabs Custom LLM integration)

`POST /voice/v1/chat/completions` exists for ElevenLabs' Conversational AI
product, not for the mobile client to call directly. It runs the same
pipeline as §4 but speaks the OpenAI Chat Completions wire format and uses a
**completely different auth model** — see
[`architecture/02_question_answering_pipeline.md`](../architecture/02_question_answering_pipeline.md#voice-the-same-pipeline-behind-an-openai-compatible-adapter-apivoicepy)
for the full rationale. Included here for completeness / anyone building an
ElevenLabs agent config, not because a typical frontend integration calls it.

**Headers:**

- `Authorization: Bearer <ELEVENLABS_CUSTOM_LLM_SECRET>` — a static shared secret configured on the deployment, **not** a Firebase ID token
- `X-User-Id: <firebase-uid>` (configurable header name) — how the patient is identified, since there's no Firebase-authenticated caller in this flow. Set this as an ElevenLabs `secret__`-prefixed dynamic variable, forwarded as a request header from the dashboard's Custom LLM config

**Request body:** OpenAI-compatible `{model, messages: [{role, content}], stream, ...}` — extra fields are tolerated (`extra="allow"`) since ElevenLabs' exact dynamic-variable body shape isn't consistently documented across their own docs.

**Response:** OpenAI `chat.completion` JSON, or `chat.completion.chunk` Server-Sent Events if `stream: true` — delivered as one complete chunk, not token-by-token (see the architecture doc for why).

**Errors:**

| HTTP | `code` | Meaning |
|---|---|---|
| 401 | `VOICE_UNAUTHORIZED` | Bad or missing shared secret |
| 400 | `VOICE_USER_ID_MISSING` | No patient uid found in the header or any known body location |
| 503 | `VOICE_NOT_CONFIGURED` | Deployment has no shared secret set (fails closed) |

Unlike §4, retrieval/answer *pipeline* failures here don't surface as HTTP
errors — they're caught and turned into one apologetic spoken sentence in a
normal `200` response, because a voice agent has no retry-UI loop to react
to an error code with.

---

## 6. Error response shape

Every non-2xx response (except `204` and rare GCS-direct calls) returns the same envelope:

```json
{
  "error": {
    "code": "DOCUMENT_NOT_FOUND",
    "message": "Document not found.",
    "request_id": "req_2083de1099e745f0"
  }
}
```

- **`code`** is stable and machine-readable. Switch on it in code; don't switch on `message`.
- **`message`** is human-readable; safe to surface in dev UI but consider localising for end-users.
- **`request_id`** is returned in the `X-Request-ID` response header too. Include it in any bug report — backend engineers grep logs by it.

### Full code table

| `code`                          | Typical HTTP | Meaning                                                          |
|----------------------------------|-------------|--------------------------------------------------------------------|
| `INTERNAL_SERVER_ERROR`         | 500         | Backend bug; retry once, then report                             |
| `VALIDATION_FAILED`             | 422 / 400   | Request body / fields invalid                                    |
| `UNAUTHENTICATED`               | 401         | Missing / unparseable bearer header                              |
| `TOKEN_EXPIRED`                 | 401         | Token past expiry → call `getIdToken(true)` and retry            |
| `TOKEN_REVOKED`                 | 401         | Force re-login                                                   |
| `INVALID_TOKEN`                 | 401         | Malformed token → force re-login                                 |
| `USER_DISABLED`                 | 401         | Account disabled in Firebase → tell user to contact support      |
| `USER_PROFILE_NOT_FOUND`        | 404         | Auth ok but no profile row → send user to signup                 |
| `EMAIL_ALREADY_EXISTS`          | 409         | Signup hit existing email                                        |
| `DOCUMENT_NOT_FOUND`            | 404         | Wrong id or not yours                                            |
| `DOCUMENT_ALREADY_FINALIZED`    | 409         | Document moved past `pending_upload`                             |
| `DOCUMENT_IN_PROCESSING`        | 409         | Worker mid-extraction; backoff & retry                           |
| `DOCUMENT_NOT_EXTRACTED`        | 409         | Extraction not ready yet — keep polling                          |
| `EXTRACTION_NOT_FOUND`          | 404         | `status==extracted` but no extraction record — backend bug       |
| `NO_FILES_UPLOADED`             | 400         | Finalize called but no files landed in GCS                       |
| `INVALID_DOMAIN`                | 422         | `domain` not in `{medical, finance}`                             |
| `INVALID_FILE_TYPE`             | 422         | `content_type` not allowed                                       |
| `FILE_TOO_LARGE`                | 413         | One file > 20 MB                                                 |
| `TOTAL_SIZE_EXCEEDED`           | 413         | Sum of `size_bytes` > 200 MB                                     |
| `TOO_MANY_FILES`                | 422         | More than 50 files in one document                               |
| `INVALID_FILE_NAME`             | 422         | Filename empty / reserved / illegal chars                        |
| `INVALID_PAGINATION_CURSOR`     | 422         | Cursor mangled                                                   |
| `CHAT_RETRIEVAL_FAILED`         | 503         | Knowledge-graph retrieval failed (generic)                       |
| `CHAT_RETRIEVAL_TIMEOUT`        | 504         | Knowledge-graph search exceeded its timeout                      |
| `CHAT_NEO4J_UNAVAILABLE`        | 503         | Neo4j/Aura unreachable                                            |
| `CHAT_LLM_FAILED`               | 503         | Answer generation failed (generic)                               |
| `CHAT_LLM_TIMEOUT`              | 504         | Answer generation exceeded its timeout                            |
| `CHAT_LLM_EMPTY`                | 503         | Gemini returned nothing (safety filter / token budget) — not retryable, ask user to rephrase |
| `CHAT_RATE_LIMITED`             | 503         | Vertex AI rate limit hit — retry with backoff                     |
| `VOICE_UNAUTHORIZED`           | 401         | Bad/missing voice shared secret                                   |
| `VOICE_USER_ID_MISSING`        | 400         | No patient uid resolvable from the voice request                 |
| `VOICE_NOT_CONFIGURED`         | 503         | Voice integration has no shared secret configured on the server  |

---

## 7. Document status state machine

```
                  create               PUT files       finalize         worker picks up
   (nothing) ─────────────► pending_upload ──────► (same) ────────► uploaded ──────► processing
                                 │                                      │                │
                                 │ DELETE                               │ DELETE   success │  error
                                 ▼                                      ▼                ▼ │  ▼
                            soft-deleted                          soft-deleted     extracted  failed
                                                                                   (terminal) (terminal)
```

| Status            | Triggered by         | Meaning                                                                                |
|--------------------|----------------------|------------------------------------------------------------------------------------------|
| `pending_upload`  | `POST /documents`    | Document row exists; client is uploading files to GCS                                  |
| `uploaded`        | `POST /finalize`     | Finalize succeeded; Pub/Sub event published. Usually visible for < 1 second.           |
| `processing`      | worker picks up event| Worker is running the pipeline. Watch `processing_step` for sub-stage progress.        |
| `extracted`       | worker completes     | ✅ Terminal: `cypher_gcs_uri`/`cypher_download_url` populated, knowledge graph is in Neo4j. |
| `failed`          | worker raises        | ❌ Terminal: `error` field carries the raw worker error message (support-only).        |

Typical end-to-end time from `POST /documents` to `status == extracted` is **~15-25 seconds** for a small PDF on a warm worker. Cold-start (first request after scale-to-zero) can add another ~10 seconds.

**Allowed transitions for `DELETE`:**

- `pending_upload`, `uploaded`, `extracted`, `failed` → ✅ soft-deletes immediately (returns `204`).
- `processing` → ❌ refused with `409 DOCUMENT_IN_PROCESSING`. Wait and retry; should clear within seconds.

See §3.12 for the recommended polling loop and friendly UI labels for each stage.

---

## 8. Quick reference — endpoint table

| Method | Path                                              | Purpose                                      | Auth |
|--------|-----------------------------------------------------|--------------------------------------------------|------|
| GET    | `/health`                                         | Liveness probe                               | no   |
| POST   | `/auth/signup`                                    | Create account                               | no   |
| GET    | `/me`                                             | Current user's profile                       | yes  |
| POST   | `/documents`                                      | Create document + get upload URLs            | yes  |
| POST   | `/documents/{id}/upload-urls/refresh`             | Reissue URLs for pending files               | yes  |
| POST   | `/documents/{id}/finalize`                        | Mark uploaded, trigger worker                | yes  |
| GET    | `/documents`                                      | List user's documents                        | yes  |
| GET    | `/documents/{id}`                                 | Read one document + download URLs + extraction state (poll this — see §3.12) | yes |
| GET    | `/documents/{id}/extraction`                      | Read the structured extraction record        | yes  |
| DELETE | `/documents/{id}`                                 | Soft-delete document                         | yes  |
| POST   | `/chat/query`                                     | Ask a question grounded in the user's graph  | yes  |
| POST   | `/voice/v1/chat/completions`                      | ElevenLabs Custom LLM adapter (not for direct FE use) | shared secret + `X-User-Id`, not Firebase |

---

## 9. Getting an ID token without the mobile app (for Swagger testing)

**Option A - sign in via Firebase REST and copy the token.** No SDK setup needed:

```bash
EMAIL="you@example.com"
PASSWORD="YourStrongPassword2026"
FIREBASE_API_KEY="AIzaSyBNMQFiLvQqyScz8jO_mb9OL_lgGXO2smo"

curl -s "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=$FIREBASE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"returnSecureToken\":true}" \
  | jq -r .idToken
```

(If the account doesn't exist, first hit `POST /auth/signup` on the API to create it.)

**Option B - use the mobile app.** Sign in, then log `auth().currentUser?.getIdToken()` to the console and copy that.

Either way: go to `<base>/docs`, click **Authorize** at the top right, paste the token (no `Bearer ` prefix), then any "Try it out" call works for the next hour.

For a full copy-pasteable walkthrough (signup → token → upload → extract →
chat) against the live deployment, see
[`running-the-project/01_using_the_deployed_system.md`](../running-the-project/01_using_the_deployed_system.md).

---

## 10. Where things live

| Concern                            | File                                                  |
|--------------------------------------|---------------------------------------------------------|
| Endpoint definitions + schemas (auth, documents) | `Backend/api/main.py`                     |
| Chat endpoint + models              | `Backend/api/chat.py`                                 |
| Voice endpoint + models             | `Backend/api/voice.py`                                |
| Chat/voice pipeline (contextualize/retrieve/answer) | `Backend/api/chat_pipeline/`                |
| Auth (token verification)          | `Backend/api/auth.py`                                 |
| Request-ID middleware              | `Backend/api/middleware.py`                           |
| Error envelope handlers            | `Backend/api/errors.py`                               |
| Limits, allowed types, domains     | `Backend/shared/models/document.py`                   |
| Error code enum                    | `Backend/shared/models/errors.py`                     |
| Signed URL generation              | `Backend/shared/gcs.py`                               |
| Firestore repository (documents)   | `Backend/shared/repositories/documents.py`            |
| Pub/Sub publishing                 | `Backend/shared/pubsub.py`                            |
| Worker entry (Pub/Sub push)        | `Backend/workers/main.py`                             |
| Worker pipeline orchestrator       | `Backend/workers/pipeline/document_pipeline.py`       |
| Document analysis (Gemini multimodal — current) | `Backend/workers/pipeline/llm/extractor.py`  |
| OCR adapter (Document AI — deprecated, kept for history only) | `Backend/workers/pipeline/ocr/`  |
| Knowledge graph builder + exporter | `Backend/workers/pipeline/graph/`                     |
| Infrastructure — API               | `Backend/api/terraform/main.tf`                       |
| Infrastructure — worker            | `Backend/workers/terraform/main.tf`                   |

**Note:** the `graph_query`/`entities_query` strings on `GET /documents/{id}`
(§3.8) are built with f-string interpolation of values that ultimately come
from the LLM extraction step, rather than parameterised queries. A future
backend change may replace them with dedicated server-side endpoints — treat
them as read-only convenience values today, not something client code should
extend or compose further.

For the *why* behind any of the above (pacing, retries, the bi-temporal
graph model, etc.), see
[`Documentation/architecture/`](../architecture/README.md); for a per-file
reference of what each of these files exports, see
[`Documentation/code-components/`](../code-components/README.md).

For bugs, please include the `X-Request-ID` from the failing response - that's the fastest path to a server-side answer.
