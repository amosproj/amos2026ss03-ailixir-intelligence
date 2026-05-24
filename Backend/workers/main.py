"""
Ailixir Worker Service.

Internal Pub/Sub push receiver for background AI pipeline tasks.
This service is NOT exposed to the public internet — it is only reachable
by Google Cloud Pub/Sub push subscriptions.

Run from the Backend/ directory:
    uvicorn workers.main:app --reload --port 8080

Pub/Sub message payload (base64-encoded JSON):
    {
        "event_type": "document_uploaded",
        "doc_id":     "doc_abc123",
        "uid":        "firebase_uid",
        "gcs_uri":    "gs://bucket/documents/doc_abc123.jpg",
        "file_name":  "prescription.jpg"
    }
"""

import asyncio
import base64
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(level=logging.INFO)
_log = logging.getLogger(__name__)

# ── App lifespan: warm up singletons once on startup ─────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    from workers.connections.graphiti_client import close_graphiti, get_graphiti
    from workers.connections.neo4j import close_driver

    _log.info("worker_startup: initialising connections")
    await get_graphiti()   # creates Neo4j driver + Graphiti client + builds indices
    _log.info("worker_startup: ready")

    yield

    _log.info("worker_shutdown: closing connections")
    await close_graphiti()
    close_driver()


app = FastAPI(
    title="Ailixir Worker Service",
    version="1.0.0",
    description="Internal Pub/Sub push receiver for AI pipeline workers.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── Pub/Sub message models ────────────────────────────────────────────────────

class PubSubMessage(BaseModel):
    data: str
    messageId: str
    message_id: str | None = None
    publishTime: str
    publish_time: str | None = None
    attributes: dict[str, str] | None = None
    orderingKey: str | None = None


class PubSubEnvelope(BaseModel):
    message: PubSubMessage
    subscription: str
    deliveryAttempt: int | None = None


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"], summary="Health check")
def health() -> dict:
    return {"status": "ok"}


@app.post(
    "/pubsub/push",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Pub/Sub"],
    summary="Pub/Sub push endpoint",
    responses={
        204: {"description": "Message acknowledged"},
        422: {"description": "Malformed Pub/Sub envelope"},
    },
)
async def pubsub_push(envelope: PubSubEnvelope) -> None:
    """
    Decode the Pub/Sub message and dispatch to the correct pipeline handler.

    Returning 204 acknowledges the message. Raising an exception causes Pub/Sub
    to redeliver (retry) — only raise on transient failures, not bad payloads.
    """
    try:
        payload: Any = json.loads(base64.b64decode(envelope.message.data).decode())
    except Exception as exc:
        _log.error("pubsub_decode_error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message data is not valid base64-encoded JSON.",
        ) from exc

    event_type: str = payload.get("event_type", "")
    _log.info(
        "pubsub_received event=%s messageId=%s attempt=%s",
        event_type, envelope.message.messageId, envelope.deliveryAttempt,
    )

    if event_type == "document_uploaded":
        await _handle_document_uploaded(payload)
    else:
        _log.warning("pubsub_unknown_event event=%s — ignoring", event_type)


# ── Event handlers ────────────────────────────────────────────────────────────

async def _handle_document_uploaded(payload: dict) -> None:
    """Validate the payload and run the document pipeline."""
    required = ("doc_id", "uid", "gcs_uri", "file_name")
    missing = [k for k in required if not payload.get(k)]
    if missing:
        _log.error("document_uploaded_payload_missing fields=%s", missing)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing required fields: {missing}",
        )

    from workers.pipeline.document_pipeline import run as run_pipeline

    # Fire-and-forget so Pub/Sub gets a fast 204 acknowledgement.
    # The pipeline updates Firestore status throughout; the frontend polls.
    asyncio.create_task(
        run_pipeline(
            doc_id=payload["doc_id"],
            uid=payload["uid"],
            gcs_uri=payload["gcs_uri"],
            file_name=payload["file_name"],
        )
    )
