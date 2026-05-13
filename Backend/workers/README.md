# Ailixir Worker Service

Internal Pub/Sub push receiver for background AI pipeline tasks.  
This service is **not** a public API — it is only called by Google Cloud Pub/Sub.

---

## Overview

The worker service decouples long-running AI tasks (OCR, LLM extraction, embedding generation) from the low-latency API that serves the mobile client. The API publishes events to a Pub/Sub topic; this service receives them via a push subscription and dispatches them to the correct pipeline handler.

```
Mobile client
    │
    ▼
[api service]  ──(publishes event)──▶  Pub/Sub topic
                                              │
                                     push subscription
                                              │
                                             ▼
                                    [workers service]
                                    POST /pubsub/push
                                              │
                                     (dispatch by event_type)
                                              │
                              ┌───────────────┼───────────────┐
                              ▼               ▼               ▼
                         ingestion      extraction        embedding
```

---

## Running Locally

Run from the **`Backend/`** directory so that the `shared/` package is on the Python path:

```bash
cd Backend
uvicorn workers.main:app --reload --port 8080
```

The service starts at `http://localhost:8080`.  
Interactive docs are at `http://localhost:8080/docs`.

---

## Pub/Sub Message Format

Cloud Pub/Sub delivers messages as HTTP POST to `/pubsub/push`.

### HTTP envelope

```json
{
  "message": {
    "data": "<base64-encoded JSON payload>",
    "messageId": "2070443601311540",
    "publishTime": "2024-01-15T10:30:00.000Z",
    "attributes": {
      "event_type": "document.uploaded"
    }
  },
  "subscription": "projects/amos26/subscriptions/worker-sub",
  "deliveryAttempt": 1
}
```

### Decoded `data` payload (expected structure)

```json
{
  "event_type": "document.uploaded",
  "document_id": "abc123",
  "uid": "firebase-user-uid",
  "gcs_uri": "gs://ailixir-docs/abc123.pdf"
}
```

The `event_type` field is used to route the message to the appropriate pipeline handler.

### Acknowledgement

| Response    | Pub/Sub behaviour                         |
|-------------|-------------------------------------------|
| `2xx`       | Message acknowledged, removed from queue |
| Non-`2xx`   | Message redelivered after backoff         |

The endpoint returns **`204 No Content`** on success.

---

## Testing the Endpoint Manually

Simulate a Pub/Sub push with `curl` (the `data` field must be base64-encoded):

```bash
# Encode the payload
PAYLOAD=$(echo -n '{"event_type":"document.uploaded","document_id":"test-doc-1"}' | base64)

curl -X POST http://localhost:8080/pubsub/push \
  -H "Content-Type: application/json" \
  -d "{
    \"message\": {
      \"data\": \"$PAYLOAD\",
      \"messageId\": \"test-1\",
      \"publishTime\": \"2024-01-15T10:30:00.000Z\"
    },
    \"subscription\": \"projects/amos26/subscriptions/worker-sub\"
  }"
```

Expected response: `HTTP 204 No Content`

---

## Docker

The Dockerfile must be built from the **`Backend/`** directory so `shared/` is included in the build context:

```bash
# From Backend/
docker build -f workers/Dockerfile -t ailixir-workers .

docker run --rm -p 8080:8080 ailixir-workers
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| *(none currently)* | — | No env vars needed for the stub implementation |

Copy `.env.example` at the `Backend/` level and extend it as pipeline handlers are added.

---

## Adding a New Pipeline Handler

1. Add a new handler function in `workers/main.py` (or a separate module under `workers/`).
2. Add the `event_type` string to the routing block inside `pubsub_push`.
3. Add any new dependencies to `workers/requirements.txt`.
