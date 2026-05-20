# Documents API - Frontend Integration Guide



- **Base URL (production):** `https://ailixir-backend-599892675013.us-east1.run.app`
- **Auth scheme:** Firebase ID token in `Authorization: Bearer <token>` header on every request except `/health` and `/auth/signup`
- **OpenAPI / Swagger UI:** `<base>/docs` (interactive; click **Authorize** at the top right, paste the ID token without the `Bearer ` prefix, then any "Try it out" call works)
- **Content type:** all API requests and responses are `application/json` unless noted
- **Files allowed:** `application/pdf`, `image/png`, `image/jpeg`
- **Domains allowed:** `medical`, `finance`
- **Limits:** 50 files per document, 20 MB per file, 200 MB per document total

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

## 3. Endpoint reference

Every authenticated endpoint accepts and emits JSON, requires `Authorization: Bearer <id_token>`, and returns errors in the same envelope (see §4).

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
|--------------|--------|----------|----------------------------------------|
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
|------|-------------------------|-------------------------------------|
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
|------|---------------------------|-------------------------------------------------------|
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
|---------|----------|----------|--------------------------------------------------------|
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
|------|-----------------------|-------------------------------------------------|
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
|------|-----------------------------------------------------|---------------------------------------------------------|
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
|------|------------------------------|-----------------------------------------------------------|
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
|------|------------------------------|---------------------------------------|
| 404  | `DOCUMENT_NOT_FOUND`         | Wrong id                              |
| 409  | `DOCUMENT_ALREADY_FINALIZED` | Document is no longer `pending_upload`|

---

### 3.8 `GET /documents/{document_id}` — read one document with download URLs

**Headers:** `Authorization: Bearer <token>`

**Response 200:**

```json
{
  "document_id": "doc_a1b2c3d4e5f6g7h8i9j0",
  "status": "uploaded",
  "domain": "medical",
  "title": "Blood report — May 2026",
  "file_count": 2,
  "total_bytes": 222642,
  "created_at": "2026-05-20T14:30:00.000Z",
  "updated_at": "2026-05-20T14:32:14.000Z",
  "finalized_at": "2026-05-20T14:32:14.000Z",
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

`download_url` is a signed GET URL — open it directly (Image component, PDF viewer, browser, etc.). It expires after **15 minutes**; re-fetch the document to get a new one. Don't cache a download URL beyond that.

Files that haven't completed upload have `download_url: null` and `upload_completed_at: null`.

**Errors:**

| HTTP | `code`               | When                                           |
|------|----------------------|------------------------------------------------|
| 404  | `DOCUMENT_NOT_FOUND` | Wrong id, soft-deleted, or owned by another user |

---

### 3.9 `GET /documents` — paginated list

Newest documents first. Returns a thumbnail URL (signed GET URL for the first completed file) but no full file URLs — call §3.8 to get those.

**Query parameters:**

| Param    | Type   | Notes                                                                  |
|----------|--------|------------------------------------------------------------------------|
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

**Errors:**

| HTTP | `code`                       | When                          |
|------|------------------------------|-------------------------------|
| 422  | `INVALID_DOMAIN`             | Unknown domain in filter      |
| 422  | `INVALID_PAGINATION_CURSOR`  | Malformed cursor              |

---

### 3.10 `DELETE /documents/{document_id}` — soft delete

Marks the document deleted. It disappears from `/documents` listings immediately. A background reconciliation job eventually hard-deletes the GCS objects (we don't expose that timing — treat it as "gone forever from the user's perspective").

**Headers:** `Authorization: Bearer <token>`

**Response 204:** empty body, success.

**Errors:**

| HTTP | `code`                  | When                                                       |
|------|-------------------------|------------------------------------------------------------|
| 404  | `DOCUMENT_NOT_FOUND`    | Wrong id                                                   |
| 409  | `DOCUMENT_IN_PROCESSING` | Worker is mid-extraction; poll & retry in a few seconds   |

---

## 4. Error response shape

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
|---------------------------------|-------------|------------------------------------------------------------------|
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
| `NO_FILES_UPLOADED`             | 400         | Finalize called but no files landed in GCS                       |
| `INVALID_DOMAIN`                | 422         | `domain` not in `{medical, finance}`                             |
| `INVALID_FILE_TYPE`             | 422         | `content_type` not allowed                                       |
| `FILE_TOO_LARGE`                | 413         | One file > 20 MB                                                 |
| `TOTAL_SIZE_EXCEEDED`           | 413         | Sum of `size_bytes` > 200 MB                                     |
| `TOO_MANY_FILES`                | 422         | More than 50 files in one document                               |
| `INVALID_FILE_NAME`             | 422         | Filename empty / reserved / illegal chars                        |
| `INVALID_PAGINATION_CURSOR`     | 422         | Cursor mangled                                                   |

---

## 5. Document status state machine

```
pending_upload  ─────────►  uploaded  ────────►  processing  ─────►  extracted
      │                         │                     │
      └─── delete ──►  (gone)   └─── delete ──►       └─── any failure ──►  failed
```

| Status            | Meaning                                                                 |
|-------------------|-------------------------------------------------------------------------|
| `pending_upload`  | Document row exists, files not yet (or not all) PUT to GCS              |
| `uploaded`        | Finalize succeeded; worker has a Pub/Sub event queued                   |
| `processing`      | Worker is doing OCR / extraction *(future PRs — currently not entered)* |
| `extracted`       | Worker finished; results available *(future)*                           |
| `failed`          | Terminal; check the `error` field for reason                            |

For PR 1 the worker only logs events — documents will settle at `uploaded` until the extraction worker lands.

---


## 6. Quick reference — endpoint table

| Method | Path                                              | Purpose                          | Auth |
|--------|---------------------------------------------------|----------------------------------|------|
| GET    | `/health`                                         | Liveness probe                   | no   |
| POST   | `/auth/signup`                                    | Create account                   | no   |
| GET    | `/me`                                             | Current user's profile           | yes  |
| POST   | `/documents`                                      | Create document + get upload URLs | yes  |
| POST   | `/documents/{id}/upload-urls/refresh`             | Reissue URLs for pending files   | yes  |
| POST   | `/documents/{id}/finalize`                        | Mark uploaded, trigger worker    | yes  |
| GET    | `/documents`                                      | List user's documents            | yes  |
| GET    | `/documents/{id}`                                 | Read one document + download URLs | yes  |
| DELETE | `/documents/{id}`                                 | Soft-delete document             | yes  |

---

## 7. Getting an ID token without the mobile app (for Swagger testing)

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

---

## 8. Where things live

| Concern                        | File                                                      |
|--------------------------------|-----------------------------------------------------------|
| Endpoint definitions + schemas | `Backend/api/main.py`                                     |
| Auth (token verification)      | `Backend/api/auth.py`                                     |
| Limits, allowed types, domains | `Backend/shared/models/document.py`                       |
| Error code enum                | `Backend/shared/models/errors.py`                         |
| Signed URL generation          | `Backend/shared/gcs.py`                                   |
| Firestore repository           | `Backend/shared/repositories/documents.py`                |
| Pub/Sub publishing             | `Backend/shared/pubsub.py`                                |
| Infrastructure (IAM, bucket)   | `Backend/api/terraform/main.tf`                           |

For bugs, please include the `X-Request-ID` from the failing response - that's the fastest path to a server-side answer.
