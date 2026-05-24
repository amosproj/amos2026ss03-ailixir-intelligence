"""
Google Cloud Pub/Sub publisher and event helpers.

The API publishes `DocumentUploaded` events after finalize so the worker can
pick up OCR / extraction asynchronously. All publishes use `document_id` as
the ordering key so per-document events stay sequenced (e.g. upload before any
later delete or reprocess).
"""

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone

from google.cloud import pubsub_v1

from shared.models.document import Document

_log = logging.getLogger(__name__)

_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "amos26")
_TOPIC_DOCUMENT_UPLOADED = os.getenv("PUBSUB_TOPIC_DOCUMENT_UPLOADED", "document-uploaded")

# Schema version for event payloads. Bump when the event shape changes in a
# way that downstream consumers must handle differently.
EVENT_SCHEMA_VERSION = "v1"

# Block until the publisher confirms delivery (or fails). Short enough to surface
# real problems to the caller; long enough to ride out transient network blips.
_PUBLISH_TIMEOUT_SECONDS = 30

_init_lock = threading.Lock()
_publisher: pubsub_v1.PublisherClient | None = None


def _get_publisher() -> pubsub_v1.PublisherClient:
    """Lazily initialise the Pub/Sub publisher with message ordering enabled.

    Ordering must be enabled at the client level — it cannot be toggled per
    publish call. The matching subscription side also needs ordering enabled
    in terraform.
    """
    global _publisher
    if _publisher is not None:
        return _publisher
    with _init_lock:
        if _publisher is None:
            _publisher = pubsub_v1.PublisherClient(
                publisher_options=pubsub_v1.types.PublisherOptions(
                    enable_message_ordering=True,
                )
            )
    return _publisher


def _topic_path(topic_name: str) -> str:
    return _get_publisher().topic_path(_PROJECT_ID, topic_name)


def publish_document_uploaded(document: Document) -> str:
    """Publish a `DocumentUploaded` event and return the Pub/Sub message id.

    The event payload includes only files whose upload was verified by finalize
    — partially-uploaded documents emit an event reflecting just the present
    files, not the originally-declared file count.

    Raises whatever `Future.result` raises if the publish fails. Callers must
    decide whether to retry (and risk duplicate delivery, which the worker
    dedupes on `event_id`) or surface the error to the client.
    """
    publisher = _get_publisher()

    event = {
        "event_type": "DocumentUploaded",
        "event_id": f"evt_{uuid.uuid4().hex}",
        "schema_version": EVENT_SCHEMA_VERSION,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "document_id": document.id,
        "uid": document.uid,
        "domain": document.domain,
        "file_count": sum(1 for f in document.files if f.upload_completed_at is not None),
        "files": [
            {
                "file_id": f.file_id,
                "gcs_object_path": f.gcs_object_path,
                "content_type": f.content_type,
                "size_bytes": f.size_bytes,
                "file_name": f.file_name,
            }
            for f in document.files
            if f.upload_completed_at is not None
        ],
    }

    payload = json.dumps(event, separators=(",", ":")).encode("utf-8")

    future = publisher.publish(
        _topic_path(_TOPIC_DOCUMENT_UPLOADED),
        payload,
        ordering_key=document.id,
        event_type="DocumentUploaded",
        schema_version=EVENT_SCHEMA_VERSION,
    )
    message_id = future.result(timeout=_PUBLISH_TIMEOUT_SECONDS)

    _log.info(
        "event_published topic=%s message_id=%s event_id=%s document_id=%s",
        _TOPIC_DOCUMENT_UPLOADED, message_id, event["event_id"], document.id,
    )
    return message_id
