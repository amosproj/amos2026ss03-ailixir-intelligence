"""
Ailixir Worker Service.

Internal Pub/Sub push receiver for background AI pipeline tasks (OCR, LLM
extraction, embedding). This service is NOT exposed to the public internet —
it is only reachable by Google Cloud Pub/Sub push subscriptions.

No authentication middleware is applied here. Cloud Run ingress should be
restricted to internal traffic; the Pub/Sub service account is the only
caller.

Run from the `Backend/` directory:
    uvicorn workers.main:app --reload --port 8080
"""

import base64
import json
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Ailixir Worker Service",
    version="1.0.0",
    description="""
## Internal Pub/Sub push receiver for AI pipeline workers.

This service is called exclusively by Google Cloud Pub/Sub — it is not
a public API. No authentication is applied at the HTTP layer; access
control is enforced at the infrastructure level (Cloud Run ingress policy
and Pub/Sub service account permissions).
""",
    contact={
        "name": "Hasnat Ahmed",
        "email": "hasnatahmed331@gmail.com",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)


# ---------------------------------------------------------------------------
# Pub/Sub message models
# ---------------------------------------------------------------------------

class PubSubMessage(BaseModel):
    """The inner message envelope sent by Cloud Pub/Sub."""

    data: str
    """Base64-encoded payload published by the producer."""

    messageId: str
    message_id: str | None = None
    publishTime: str
    publish_time: str | None = None
    attributes: dict[str, str] | None = None
    orderingKey: str | None = None


class PubSubEnvelope(BaseModel):
    """Top-level JSON body that Pub/Sub delivers to the push endpoint."""

    message: PubSubMessage
    subscription: str
    deliveryAttempt: int | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    tags=["System"],
    summary="Health check",
    response_description="Service is running",
)
def health() -> dict:
    return {"status": "ok"}


@app.post(
    "/pubsub/push",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Pub/Sub"],
    summary="Pub/Sub push endpoint",
    response_description="Message acknowledged (empty body)",
    responses={
        204: {"description": "Message received and acknowledged"},
        422: {"description": "Malformed Pub/Sub envelope"},
    },
)
async def pubsub_push(envelope: PubSubEnvelope) -> None:
    """Receive a Pub/Sub push message and dispatch it to the appropriate handler.

    Pub/Sub retries delivery until it receives an HTTP 2xx response. Returning
    204 (No Content) acknowledges the message. Raising an exception causes a
    non-2xx response which tells Pub/Sub to redeliver.

    The `data` field is base64-encoded. The decoded payload is expected to be
    a JSON object whose `event_type` field routes the message to the correct
    AI pipeline stage.
    """
    raw = envelope.message.data

    try:
        payload: Any = json.loads(base64.b64decode(raw).decode("utf-8"))
    except Exception as exc:
        logger.error("Failed to decode Pub/Sub message data: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message data is not valid base64-encoded JSON.",
        ) from exc

    logger.info(
        "Received Pub/Sub message | subscription=%s messageId=%s deliveryAttempt=%s payload=%s",
        envelope.subscription,
        envelope.message.messageId,
        envelope.deliveryAttempt,
        payload,
    )

    # TODO(routing): inspect payload["event_type"] and dispatch to the
    # appropriate AI pipeline handler (ingestion, extraction, embedding, …).
