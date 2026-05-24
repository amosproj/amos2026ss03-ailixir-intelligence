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



# Audience the push subscription was configured to set in OIDC tokens. The
# Cloud Run URL of this worker is the canonical value; in local dev we relax
# verification (see `_verify_oidc_token`).
_OIDC_AUDIENCE = os.getenv("PUBSUB_PUSH_AUDIENCE", "")

# Email of the service account terraform created for Pub/Sub-to-worker pushes.
# Verifying this prevents impersonation even if someone else acquires a valid
# Google OIDC token for the worker's audience.
_OIDC_TRUSTED_EMAIL = os.getenv("PUBSUB_PUSH_SERVICE_ACCOUNT", "")

# Local dev / emulator escape hatch. Set to "1" to skip OIDC verification.
# Never set this in production — terraform must inject `_OIDC_AUDIENCE` and
# `_OIDC_TRUSTED_EMAIL` so the prod path is taken.
_SKIP_OIDC_VERIFICATION = os.getenv("PUBSUB_SKIP_OIDC_VERIFICATION", "").lower() in {
    "1",
    "true",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up singleton connections once on startup; close cleanly on shutdown."""
    from workers.connections.graphiti_client import close_graphiti, get_graphiti
    from workers.connections.neo4j import close_driver

    logger.info("worker_startup: initialising connections")
    if not os.getenv("SKIP_STARTUP_CONNECTIONS"):
        await get_graphiti()  # creates Neo4j driver + Graphiti client + builds indices
    logger.info("worker_startup: ready")

    yield

    logger.info("worker_shutdown: closing connections")
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


def _verify_oidc_token(authorization_header: str | None) -> None:
    """Validate the OIDC token Pub/Sub attached to the push request.

    Raises 401 if the token is missing, malformed, expired, signed by an
    untrusted issuer, has the wrong audience, or was minted by an unexpected
    service account.

    Skipped entirely when `PUBSUB_SKIP_OIDC_VERIFICATION=1` (local emulator).
    """
    if _SKIP_OIDC_VERIFICATION:
        return

    if not authorization_header or not authorization_header.lower().startswith(
        "bearer "
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token."
        )

    token = authorization_header.split(" ", 1)[1].strip()

    try:
        claims = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            audience=_OIDC_AUDIENCE or None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"OIDC verification failed: {exc}",
        ) from exc

    if _OIDC_TRUSTED_EMAIL and claims.get("email") != _OIDC_TRUSTED_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC token from unexpected service account.",
        )
    if not claims.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OIDC token email not verified.",
        )


# ──────────────────────────────────────────────────────────────────────────────
# Event dispatch
# ──────────────────────────────────────────────────────────────────────────────


async def _handle_document_uploaded(payload: dict[str, Any]) -> None:
    document_id = payload.get("document_id")
    uid = payload.get("uid")
    if not document_id or not uid:
        logger.error(
            "document_uploaded_missing_fields payload=%s", payload
        )
        return
    logger.info(
        "document_uploaded_event document_id=%s uid=%s domain=%s file_count=%s",
        document_id,
        uid,
        payload.get("domain"),
        payload.get("file_count"),
    )
    from workers.pipeline.document_pipeline import run as run_pipeline
    await run_pipeline(document_id=document_id, uid=uid)


_EVENT_HANDLERS = {
    "DocumentUploaded": _handle_document_uploaded,
}


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────


@app.get(
    "/health",
    tags=["System"],
    summary="Health check",
)
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
