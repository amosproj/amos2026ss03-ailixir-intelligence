"""
Repository for the `documents` Firestore collection.

Callers go through these functions instead of touching Firestore directly. This is
the seam where we can later add caching, switch databases, or substitute a fake
implementation in tests.
"""

import logging
import uuid
from datetime import datetime, timezone

from firebase_admin import firestore

from shared.firestore import get_firestore
from shared.models.document import Document, DocumentStatus

_log = logging.getLogger(__name__)
_COLLECTION = "documents"


def _new_id() -> str:
    return f"doc_{uuid.uuid4().hex}"


def create_document(
    *,
    uid: str,
    file_name: str,
    content_type: str,
    size_bytes: int,
    domain: str,
) -> Document:
    """Persist a new document record in PENDING_UPLOAD state and return it.

    The created_at/updated_at on the returned Document are best-effort client time.
    The canonical values written to Firestore use SERVER_TIMESTAMP and may differ
    from the returned object by up to a few hundred milliseconds.
    """
    db = get_firestore()
    doc_id = _new_id()
    now = datetime.now(timezone.utc)

    # SERVER_TIMESTAMP is atomic with the write and ordered by server clock.
    # Client wall clocks drift; we don't trust them for ordering.
    db.collection(_COLLECTION).document(doc_id).set(
        {
            "id": doc_id,
            "uid": uid,
            "file_name": file_name,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "domain": domain,
            "status": DocumentStatus.PENDING_UPLOAD.value,
            "gcs_uri": None,
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "error": None,
        }
    )

    _log.info(
        "document_created id=%s uid=%s domain=%s size_bytes=%d",
        doc_id, uid, domain, size_bytes,
    )

    return Document(
        id=doc_id,
        uid=uid,
        file_name=file_name,
        content_type=content_type,
        size_bytes=size_bytes,
        domain=domain,
        status=DocumentStatus.PENDING_UPLOAD,
        gcs_uri=None,
        created_at=now,
        updated_at=now,
        error=None,
    )


def get_document(doc_id: str) -> Document | None:
    """Fetch a document by id. Returns None if the id does not exist."""
    db = get_firestore()
    snapshot = db.collection(_COLLECTION).document(doc_id).get()
    if not snapshot.exists:
        return None
    return Document(**snapshot.to_dict())


def update_status(
    doc_id: str,
    status: DocumentStatus,
    *,
    error: str | None = None,
) -> None:
    """Transition a document to a new status. Optionally record an error message."""
    db = get_firestore()
    patch: dict = {
        "status": status.value,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    if error is not None:
        patch["error"] = error
    db.collection(_COLLECTION).document(doc_id).update(patch)
    _log.info("document_status_updated id=%s status=%s", doc_id, status.value)


def update_processing_step(doc_id: str, step: str) -> None:
    """Write a human-readable progress step for frontend polling (e.g. 'ocr', 'graph')."""
    db = get_firestore()
    db.collection(_COLLECTION).document(doc_id).update(
        {"processing_step": step, "updated_at": firestore.SERVER_TIMESTAMP}
    )
    _log.info("document_step_updated id=%s step=%s", doc_id, step)


def update_cypher_uri(doc_id: str, cypher_gcs_uri: str) -> None:
    """Attach the GCS URI of the exported Cypher file once the pipeline finishes."""
    db = get_firestore()
    db.collection(_COLLECTION).document(doc_id).update(
        {"cypher_gcs_uri": cypher_gcs_uri, "updated_at": firestore.SERVER_TIMESTAMP}
    )
    _log.info("document_cypher_uri_set id=%s uri=%s", doc_id, cypher_gcs_uri)
