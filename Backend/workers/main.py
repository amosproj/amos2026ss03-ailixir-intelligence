"""
Ailixir Worker Service.

Internal Pub/Sub push receiver for background AI pipeline tasks. The service
is reachable only from inside GCP — Cloud Run ingress is set to internal +
load-balancer, and Pub/Sub authenticates each push with an OIDC token signed
by a dedicated service account.

Run from the `Backend/` directory:
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
import os
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from neo4j.exceptions import (
    AuthError as Neo4jAuthError,
    ServiceUnavailable as Neo4jServiceUnavailable,
    SessionExpired as Neo4jSessionExpired,
)
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


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


# Exceptions from Neo4j/Graphiti that mean "the dependency is transiently unreachable"
# rather than "this message is permanently bad". Mapped to HTTP 503 in the push
# handler so Pub/Sub retries per the subscription's backoff policy. Adding new
# retryable error classes here is the way to extend coverage — keep this tuple
# narrow so we don't accidentally silence genuine logic errors.
_RETRYABLE_DEPENDENCY_ERRORS: tuple[type[BaseException], ...] = (
    Neo4jServiceUnavailable,   # DNS failure, network partition, Aura paused/deleted
    Neo4jSessionExpired,       # connection pool stale; next call typically succeeds
    Neo4jAuthError,            # rare but worth retrying — credentials may be mid-rotation
    ConnectionError,           # generic socket-level error from any client
    TimeoutError,              # asyncio timeout from any awaited call
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan that does NOT touch external dependencies at startup.

    Earlier versions called `get_graphiti()` here to "warm up" the Neo4j
    connection and build indices. That made the container's readiness probe
    transitively depend on Neo4j Aura being reachable — a managed-service
    outage upstream would cause every cold start to fail, taking the worker
    out of rotation entirely. (We hit exactly this when an Aura Free
    instance auto-paused; the worker couldn't boot for days even though
    nothing in our code had changed.)

    The fix: connect lazily on first request. The container boots regardless
    of Neo4j state, the Cloud Run readiness probe passes, and Pub/Sub's
    own retry policy handles transient downstream failures cleanly via
    the 503 response path in `pubsub_push` below.
    """
    logger.info("worker_startup: ready (dependencies will be connected lazily)")
    yield

    logger.info("worker_shutdown: closing connections (best-effort)")
    # Import lazily so a broken import in a connection module doesn't prevent
    # the worker from starting in the first place.
    try:
        from workers.connections.graphiti_client import close_graphiti
        await close_graphiti()
    except Exception as exc:
        # Shutdown failures must not raise — Cloud Run gives us only ~10s
        # for SIGTERM cleanup and a raise here would mask the real signal.
        logger.warning("close_graphiti_failed: %s", exc)
    try:
        from workers.connections.neo4j import close_driver
        close_driver()
    except Exception as exc:
        logger.warning("close_driver_failed: %s", exc)


app = FastAPI(
    title="Ailixir Worker Service",
    version="1.0.0",
    description="""
## Internal Pub/Sub push receiver for AI pipeline workers.

Authenticated by Pub/Sub-signed OIDC tokens. Not a public API.
""",
    contact={
        "name": "Hasnat Ahmed",
        "email": "hasnatahmed331@gmail.com",
    },
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ──────────────────────────────────────────────────────────────────────────────
# Pub/Sub envelope models
# ──────────────────────────────────────────────────────────────────────────────


class PubSubMessage(BaseModel):
    """The inner message envelope sent by Cloud Pub/Sub."""

    data: str  # base64-encoded
    messageId: str
    message_id: str | None = None
    publishTime: str
    publish_time: str | None = None
    attributes: dict[str, str] | None = None
    orderingKey: str | None = None


class PubSubEnvelope(BaseModel):
    """Top-level JSON body Pub/Sub delivers to the push endpoint."""

    message: PubSubMessage
    subscription: str
    deliveryAttempt: int | None = None


# ──────────────────────────────────────────────────────────────────────────────
# OIDC verification
# ──────────────────────────────────────────────────────────────────────────────


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
)
async def pubsub_push(
    envelope: PubSubEnvelope,
    authorization: str | None = Header(default=None),
) -> None:
    """Receive a Pub/Sub push message, dispatch to the correct handler.

    Returning 204 acks the message. Raising tells Pub/Sub to redeliver per the
    subscription's retry policy; persistent failures land in the DLQ.
    """
    _verify_oidc_token(authorization)

    raw = envelope.message.data
    try:
        payload: Any = json.loads(base64.b64decode(envelope.message.data).decode())
    except Exception as exc:
        logger.error("Failed to decode Pub/Sub message data: %s", exc)
        # 422 lets Pub/Sub mark the message as a permanent failure — DLQ
        # routing prevents infinite redelivery of malformed bodies.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message data is not valid base64-encoded JSON.",
        ) from exc

    event_type = payload.get("event_type") if isinstance(payload, dict) else None
    logger.info(
        "pubsub_received subscription=%s message_id=%s event_type=%s delivery_attempt=%s",
        envelope.subscription,
        envelope.message.messageId,
        event_type,
        envelope.deliveryAttempt,
    )

    handler = _EVENT_HANDLERS.get(event_type) if event_type else None
    if handler is None:
        # Unknown event type — ack so Pub/Sub doesn't loop. Worker version
        # may simply not know about this event yet; logging is enough.
        logger.warning(
            "unknown_event_type event_type=%s message_id=%s",
            event_type,
            envelope.message.messageId,
        )
        return

    # Dispatch with explicit retryable-vs-permanent error handling.
    #
    # The contract with Pub/Sub Push is:
    #   2xx  → message acked, removed from the subscription
    #   4xx  → message acked (Pub/Sub treats it as "won't ever succeed"); for
    #          422 specifically we want the message to fall through to the DLQ
    #          after the configured max_delivery_attempts
    #   5xx  → message nacked, retried per the subscription's backoff policy
    #
    # For a known-transient downstream failure (Neo4j unreachable, network blip)
    # we want 5xx so the retry buys time for the dependency to recover.
    # For a genuinely unexpected exception we still return 5xx — Pub/Sub will
    # retry, and after max attempts the message goes to the DLQ where an
    # operator can inspect it (better than silently acking a bug).
    try:
        await handler(payload)
    except _RETRYABLE_DEPENDENCY_ERRORS as exc:
        # Transient dependency failure. Log at WARNING (not ERROR) because the
        # retry path is the design — getting a few of these is normal during
        # an upstream blip. Pages should fire on sustained 503 rate, not on
        # a single occurrence.
        logger.warning(
            "pipeline_transient_failure event_type=%s message_id=%s delivery_attempt=%s err=%s",
            event_type,
            envelope.message.messageId,
            envelope.deliveryAttempt,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Transient downstream dependency unavailable; Pub/Sub will retry.",
        ) from exc
    except Exception as exc:
        # Unexpected error. ERROR level + full traceback for the on-call
        # responder. Still 5xx so Pub/Sub will retry then DLQ on giving up.
        logger.exception(
            "pipeline_unexpected_failure event_type=%s message_id=%s delivery_attempt=%s",
            event_type,
            envelope.message.messageId,
            envelope.deliveryAttempt,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal pipeline error.",
        ) from exc
