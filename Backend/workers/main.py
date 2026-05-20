"""
Ailixir Worker Service.

Internal Pub/Sub push receiver for background AI pipeline tasks. The service
is reachable only from inside GCP — Cloud Run ingress is set to internal +
load-balancer, and Pub/Sub authenticates each push with an OIDC token signed
by a dedicated service account.

Run from the `Backend/` directory:
    uvicorn workers.main:app --reload --port 8080
"""

import base64
import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
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
_SKIP_OIDC_VERIFICATION = os.getenv("PUBSUB_SKIP_OIDC_VERIFICATION", "").lower() in {"1", "true"}


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
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
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

    if not authorization_header or not authorization_header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")

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

def _handle_document_uploaded(payload: dict[str, Any]) -> None:
    """Stub for the ingestion pipeline. Real OCR / extraction lands in a
    later ticket — for now we log the event so the round-trip is visible."""
    logger.info(
        "document_uploaded_event document_id=%s uid=%s domain=%s file_count=%s",
        payload.get("document_id"),
        payload.get("uid"),
        payload.get("domain"),
        payload.get("file_count"),
    )


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
        payload: Any = json.loads(base64.b64decode(raw).decode("utf-8"))
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
        logger.warning("unknown_event_type event_type=%s message_id=%s",
                       event_type, envelope.message.messageId)
        return

    handler(payload)
