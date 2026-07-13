# 01 — Using the Deployed System

Zero setup. This walks through hitting the **already-deployed** `api`
service: create an account, upload a document, watch it turn into a
knowledge graph, then chat against it. Everything here is just HTTP calls —
no clone, no local Python, no GCP project of your own.

For the full field-by-field endpoint reference (every request/response
shape, every error code), see
[`Documentation/api-integration-guides/Document_API_FE_Integration_guide.md`](../api-integration-guides/Document_API_FE_Integration_guide.md).
This doc is the shorter task-oriented version.

## The deployed backend

```
https://ailixir-backend-599892675013.us-east1.run.app
```

Interactive Swagger UI: `<base>/docs`. Every authenticated call in this doc
can also be run there — click **Authorize**, paste the ID token from Step 1
(no `Bearer ` prefix), then use "Try it out" on any endpoint.

> The URL/keys below are the current team demo deployment and may rotate.
> If a call unexpectedly 404s or the Firebase key stops working, ask the
> maintainer for the current values — nothing else in this walkthrough
> changes.

Prerequisites: `curl` and `jq` (`brew install jq` / `apt install jq`).

## Step 0 — create an account

```bash
export API="https://ailixir-backend-599892675013.us-east1.run.app"
export FIREBASE_API_KEY="AIzaSyBNMQFiLvQqyScz8jO_mb9OL_lgGXO2smo"
export EMAIL="you@example.com"
export PASSWORD="YourStrongPasswordHere"

curl -s -X POST "$API/auth/signup" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"first_name\":\"Demo\",\"last_name\":\"User\"}"
```

`201` with `{"uid": ...}` means it worked. `409 EMAIL_ALREADY_EXISTS` just
means the account already exists — continue to Step 1 either way.

## Step 1 — sign in and get a Firebase ID token

Sign-in is **not** a backend endpoint — you talk to Firebase Auth directly,
the same way the mobile app does:

```bash
export TOKEN=$(curl -s \
  "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=$FIREBASE_API_KEY" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"returnSecureToken\":true}" \
  | jq -r .idToken)

echo "Token length: ${#TOKEN}"   # should be 900+
```

The token expires after **1 hour** — a `401 TOKEN_EXPIRED` on any later
step means rerun this.

## Step 2 — upload a document and watch it get extracted

This is the three-step handshake every client (mobile app included) goes
through: create → PUT bytes to GCS → finalize. See
[`architecture/01_extraction_and_knowledge_graph_pipeline.md`](../architecture/01_extraction_and_knowledge_graph_pipeline.md)
for what happens after finalize.

```bash
export PDF_PATH="/full/path/to/your.pdf"     # pdf, png, or jpeg; ≤ 20MB
export SIZE=$(wc -c < "$PDF_PATH" | tr -d ' ')
export FILE_NAME=$(basename "$PDF_PATH")
export CONTENT_TYPE="application/pdf"        # or "image/png" / "image/jpeg"

# 2a — create the document, get a signed upload URL
CREATE_RESPONSE=$(curl -s -X POST "$API/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"domain\":\"medical\",\"title\":\"$FILE_NAME\",\"files\":[{\"file_name\":\"$FILE_NAME\",\"content_type\":\"$CONTENT_TYPE\",\"size_bytes\":$SIZE}]}")

export DOC_ID=$(echo "$CREATE_RESPONSE" | jq -r '.document_id')
export UPLOAD_URL=$(echo "$CREATE_RESPONSE" | jq -r '.files[0].upload_url')
echo "Created document: $DOC_ID"

# 2b — PUT the raw bytes directly to GCS (not the API)
curl -X PUT "$UPLOAD_URL" \
  -H "Content-Type: $CONTENT_TYPE" \
  -H "x-goog-content-length-range: 0,$SIZE" \
  -H "x-goog-if-generation-match: 0" \
  --data-binary "@$PDF_PATH" \
  -w "\nUpload HTTP %{http_code}\n"

# 2c — finalize: this is what actually triggers the worker pipeline
curl -s -X POST "$API/documents/$DOC_ID/finalize" \
  -H "Authorization: Bearer $TOKEN" -d '{}' | jq '{status}'
```

Then poll until it's done (`extracted` or `failed`, typically ~15-25s):

```bash
while true; do
  RESP=$(curl -s -H "Authorization: Bearer $TOKEN" "$API/documents/$DOC_ID")
  STATE=$(echo "$RESP" | jq -r .status)
  echo "$RESP" | jq '{status, processing_step, error}'
  [ "$STATE" = "extracted" ] || [ "$STATE" = "failed" ] && break
  sleep 2
done
```

Once `extracted`, the same response carries `cypher_gcs_uri` (a `gs://` URI
to the exported knowledge-graph script — needs `gsutil` or a service-account
key to fetch, since it's not a public HTTPS URL) and, more usefully for
day-to-day use, `graph_query`/`entities_query` — ready-made Cypher you can
paste into Neo4j Browser if you have access to the project's Neo4j instance.

## Step 3 — chat against what you just uploaded

This is the same three-step RAG pipeline described in
[`architecture/02_question_answering_pipeline.md`](../architecture/02_question_answering_pipeline.md) —
contextualize → retrieve (your knowledge graph + research papers) → answer.
It only knows what's in *your* uploaded documents (`group_id` = your `uid`),
so ask about something that was actually in the PDF you uploaded:

```bash
curl -s -X POST "$API/chat/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "What medications is the patient currently on?",
    "history": [],
    "chat_id": "demo-chat-1"
  }' | jq .
```

Response includes the natural-language `answer` plus `facts_used`/
`entities_used` (how many graph facts backed the answer) and `papers_used`
(reranked research-paper excerpts, if any — 0 just means the graph alone
answered it). Send a follow-up in the same conversation by replaying the
prior turn in `history`:

```bash
curl -s -X POST "$API/chat/query" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "What about its side effects?",
    "history": [
      {"role": "user", "content": "What medications is the patient currently on?"},
      {"role": "assistant", "content": "<paste the previous answer here>"}
    ],
    "chat_id": "demo-chat-1"
  }' | jq .
```

Watch `query_changed: true` and `contextualized_query` in the response —
that's Step 1 rewriting "its side effects" into a self-contained question
using the history you sent.

## Voice — not directly playable without a deployment secret

`POST /voice/v1/chat/completions` runs the same pipeline behind an
OpenAI-Chat-Completions-shaped adapter for ElevenLabs' Conversational AI
(see [`architecture/02_question_answering_pipeline.md`](../architecture/02_question_answering_pipeline.md#voice-the-same-pipeline-behind-an-openai-compatible-adapter-apivoicepy)).
It requires a shared secret (`ELEVENLABS_CUSTOM_LLM_SECRET`) set on the
deployment, and identifies the patient via a header rather than a Firebase
token — not something an external user can call without that secret. If you
want to try it end-to-end, set your own secret and run it yourself: see
[02 — Running Locally](02_running_locally.md).

## Troubleshooting

| Symptom | Cause |
|---|---|
| `401` on any authenticated call | Token expired (1h) — redo Step 1 |
| `422 VALIDATION_FAILED` on create | Wrong `content_type` or bad `size_bytes` |
| `403` on the GCS PUT | Upload headers don't match what create returned — copy them verbatim, don't reorder/add/omit |
| `400 NO_FILES_UPLOADED` on finalize | The PUT didn't actually succeed — check its HTTP code |
| Stuck in `processing` for minutes | Worker cold start (scale-to-zero) — wait ~30-60s more before assuming it's stuck |
| `status: failed` | Read the `error` field in the document response |
| `503 CHAT_*` on `/chat/query` | Transient dependency (Neo4j/Vertex) — retry with backoff, see the error-code table in [doc 02 architecture](../architecture/02_question_answering_pipeline.md#error-taxonomy-chatquery) |
| zsh eats `.files[0]` in a `jq` path | Quote it: `jq -r '.files[0].upload_url'` — unquoted brackets are a zsh glob |

Always include the response's `X-Request-ID` header in a bug report — it's
how backend engineers grep Cloud Logging for your exact request.
