# Run the extraction pipeline on a document (via curl)

Step-by-step recipe to push a single PDF/image through the live Ailixir backend
and get back the `.cypher` knowledge-graph file.

---

## Prerequisites

| What | Where to get it |
|---|---|
| A test account email + password | Sign up via the API (step 0) or reuse any team test account |
| The PDF/image you want to extract | Local file path; supported types: `application/pdf`, `image/png`, `image/jpeg`; max 20 MB per file |
| `curl` and `jq` | `brew install jq` if missing |
| For the final step (downloading the cypher from GCS): either `gsutil` **or** a service-account key with read access to the `ailixir-cypher-amos26` bucket |

The backend is at:

```
https://ailixir-backend-599892675013.us-east1.run.app
```

(`https://ailixir-backend-5mg2ellzaa-ue.a.run.app` is the legacy Cloud Run URL — same service, both work.)

---

## Setup — shell variables you'll reuse

Paste this into your terminal once. Replace `EMAIL` / `PASSWORD` / `PDF_PATH`.

```bash
export API="https://ailixir-backend-599892675013.us-east1.run.app"
export FIREBASE_API_KEY="AIzaSyBNMQFiLvQqyScz8jO_mb9OL_lgGXO2smo"
export EMAIL="you@example.com"
export PASSWORD="YourStrongPasswordHere"
export PDF_PATH="/full/path/to/your.pdf"
```

---

## Step 0 — (one time) create the test account

Skip if you already have an account.

```bash
curl -s -X POST "$API/auth/signup" \
  -H 'Content-Type: application/json' \
  -d "{
    \"email\":\"$EMAIL\",
    \"password\":\"$PASSWORD\",
    \"first_name\":\"Pipeline\",
    \"last_name\":\"Runner\"
  }"
```

Expected: `201` with `{"uid":...}`. `409 EMAIL_ALREADY_EXISTS` is fine — that means the account is already there, continue to step 1.

---

## Step 1 — sign in and get a Firebase ID token

```bash
export TOKEN=$(curl -s \
  "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=$FIREBASE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"returnSecureToken\":true}" \
  | jq -r .idToken)

echo "Token length: ${#TOKEN} (should be ~900+)"
```

The token expires after **1 hour**. If you hit `401 TOKEN_EXPIRED` later, rerun this step.

---

## Step 2 — create the document and get a signed upload URL

Paste each export separately (don't paste comments in the middle of a multi-line block — zsh treats them oddly):

```bash
export SIZE=$(wc -c < "$PDF_PATH" | tr -d ' ')
export FILE_NAME=$(basename "$PDF_PATH")
export CONTENT_TYPE="application/pdf"   # use "image/png" or "image/jpeg" for images
export DOMAIN="medical"                 # or "finance"

CREATE_RESPONSE=$(curl -s -X POST "$API/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{
    \"domain\": \"$DOMAIN\",
    \"title\": \"$FILE_NAME\",
    \"files\": [{
      \"file_name\": \"$FILE_NAME\",
      \"content_type\": \"$CONTENT_TYPE\",
      \"size_bytes\": $SIZE
    }]
  }")

echo "$CREATE_RESPONSE" | jq .

# IMPORTANT: single-quote any jq path that contains [n] — zsh treats brackets
# as glob patterns and will error with "no matches found" otherwise.
export DOC_ID=$(echo "$CREATE_RESPONSE" | jq -r '.document_id')
export UPLOAD_URL=$(echo "$CREATE_RESPONSE" | jq -r '.files[0].upload_url')
export UPLOAD_METHOD=$(echo "$CREATE_RESPONSE" | jq -r '.files[0].upload_method')

echo "Created document: $DOC_ID"
```

---

## Step 3 — PUT the bytes directly to GCS

This request goes to Google Cloud Storage, **not** your API. Headers must match exactly what step 2 returned.

```bash
curl -X "$UPLOAD_METHOD" "$UPLOAD_URL" \
  -H "Content-Type: $CONTENT_TYPE" \
  -H "x-goog-content-length-range: 0,$SIZE" \
  -H "x-goog-if-generation-match: 0" \
  --data-binary "@$PDF_PATH" \
  -w "\nUpload HTTP %{http_code}\n"
```

Expected: `HTTP 200`. Anything else means the headers didn't match the signed URL — re-check Content-Type and size.

---

## Step 4 — finalize the document (triggers the worker pipeline)

```bash
curl -s -X POST "$API/documents/$DOC_ID/finalize" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{}' | jq .
```

Expected: `{"status": "uploaded", ...}`. This publishes a Pub/Sub event; the worker picks it up within ~1 second and starts extraction.

---

## Step 5 — poll until `status: extracted`

Watch the document. Stop when status is `extracted` (success) or `failed`.

```bash
while true; do
  STATUS=$(curl -s -H "Authorization: Bearer $TOKEN" "$API/documents/$DOC_ID" \
    | jq -r '{status, processing_step, cypher_gcs_uri, error}')
  echo "$STATUS"
  STATE=$(echo "$STATUS" | jq -r .status)
  if [ "$STATE" = "extracted" ] || [ "$STATE" = "failed" ]; then
    break
  fi
  sleep 2
done
```

When done, capture the cypher URI:

```bash
export CYPHER_URI=$(curl -s -H "Authorization: Bearer $TOKEN" "$API/documents/$DOC_ID" \
  | jq -r '.cypher_gcs_uri')
echo "Cypher file: $CYPHER_URI"
# e.g. gs://ailixir-cypher-amos26/graphs/doc_xxx_graph.cypher
```

---

## Step 6 — download the `.cypher` file from GCS

The URI is a `gs://` URI, not a public HTTPS URL. Pick one of the following.

### Option A — `gsutil` (cleanest)

```bash
gsutil cp "$CYPHER_URI" "./$(basename $CYPHER_URI)"
```

Requires `gcloud` installed and `gcloud auth login` once.

### Option B — Python one-liner (works with the team's service-account key)

Use the Backend venv's Python explicitly.

If you have the Firebase service-account key at `Backend/secrets/serviceAccountKey.json`:

```bash
GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/Backend/secrets/serviceAccountKey.json" \
Backend/.venv/bin/python3 -c "
from google.cloud import storage
uri = '$CYPHER_URI'                    # gs://bucket/path/to/file
bucket, _, blob = uri[5:].partition('/')
out = blob.split('/')[-1]              # local file name
storage.Client().bucket(bucket).blob(blob).download_to_filename(out)
print('Downloaded ->', out)
"
```

If you don't have the Backend venv yet, either set one up (`cd Backend && python3 -m venv .venv && source .venv/bin/activate && pip install google-cloud-storage`) or use plain `python3`.

You now have the `.cypher` file locally.

---
## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `zsh: no matches found: .files[0]...` | Unquoted jq path — zsh globs `[0]`. Wrap the path in single quotes: `jq -r '.files[0].upload_url'`. |
| `quote>` prompt after pasting a multi-line export block | A `#` comment inside the block confused zsh. Paste exports one at a time, or remove inline comments. |
| `python3` hangs on "Press enter to display the license" | macOS Xcode CLT license prompt. Use `Backend/.venv/bin/python3` instead, or run `sudo xcodebuild -license accept` once. |
| `curl: option -X: blank argument` | A shell variable expanded to empty (usually `$UPLOAD_METHOD` because the `jq` extraction failed silently). Re-check the previous `export` lines and `echo` each variable before using. |
| `401` on step 2 | Token expired — rerun step 1 |
| `422 VALIDATION_FAILED` on step 2 | Wrong `content_type` or bad `size_bytes` — re-check |
| `403` on step 3 | Upload headers don't match what step 2 returned — copy them verbatim |
| `400 NO_FILES_UPLOADED` on step 4 | Step 3 didn't actually succeed; check its HTTP code |
| Pipeline stuck in `processing` for > 2 min | Worker may be on cold start; wait another minute |
| Status reaches `failed` | Read the `error` field in the GET response — usually a Neo4j or Document AI config issue |

Include the `X-Request-ID` response header in any bug report — that's how backend engineers grep Cloud Logging.
