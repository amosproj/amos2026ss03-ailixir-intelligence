"""
Repository for the `documents` Firestore collection.

The collection stores logical Documents; each Document carries its files as an
embedded array (well within Firestore's 1 MB per-document limit at the file
counts this API allows).

All read paths take a `uid` and refuse to return another user's data — the
authorisation boundary lives here so endpoints can't accidentally bypass it.
"""

import base64
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Iterable

from firebase_admin import firestore as firebase_firestore
from google.cloud.firestore_v1 import (
    FieldFilter,
    Query,
    Transaction,
    transactional,
)

from shared.firestore import get_firestore
from shared.models.document import (
    Document,
    DocumentFile,
    DocumentStatus,
)

_log = logging.getLogger(__name__)
_COLLECTION = "documents"


# ──────────────────────────────────────────────────────────────────────────────
# ID generation & cursor encoding
# ──────────────────────────────────────────────────────────────────────────────


def _new_document_id() -> str:
    return f"doc_{uuid.uuid4().hex}"


def _new_file_id() -> str:
    return f"f_{uuid.uuid4().hex}"


def _encode_cursor(created_at: datetime, document_id: str) -> str:
    """Encode a pagination cursor as URL-safe base64 of `{c, i}`."""
    payload = json.dumps(
        {"c": created_at.isoformat(), "i": document_id},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode()).rstrip(b"=").decode()


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Reverse of `_encode_cursor`. Raises ValueError on malformed input."""
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding).decode())
        return datetime.fromisoformat(payload["c"]), payload["i"]
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed cursor") from exc


# ──────────────────────────────────────────────────────────────────────────────
# Firestore <-> Pydantic mapping
# ──────────────────────────────────────────────────────────────────────────────


def _snapshot_to_document(snapshot) -> Document:
    """Convert a Firestore document snapshot into a Document.

    Returned timestamps come from Firestore as `DatetimeWithNanoseconds` (a
    `datetime` subclass) so Pydantic accepts them without coercion.
    """
    data = snapshot.to_dict() or {}
    return Document(**data)


# ──────────────────────────────────────────────────────────────────────────────
# Creates
# ──────────────────────────────────────────────────────────────────────────────


class FileCreationSpec:
    """Input for one file at document creation time. Mirrors `DocumentFile`
    minus server-assigned fields (`file_id`, `gcs_object_path`, timestamps)."""

    __slots__ = ("file_name", "content_type", "size_bytes")

    def __init__(self, *, file_name: str, content_type: str, size_bytes: int):
        self.file_name = file_name
        self.content_type = content_type
        self.size_bytes = size_bytes


def create_document_with_files(
    *,
    uid: str,
    domain: str,
    title: str | None,
    file_specs: list[FileCreationSpec],
    idempotency_key: str | None,
    object_path_builder,
) -> Document:
    """Persist a new Document plus its files in a single Firestore write.

    The caller supplies an `object_path_builder` callable that, given a
    `file_id` and extension, returns the GCS object path. This keeps the
    repository ignorant of GCS layout details while letting the caller
    construct paths under any prefix scheme it wants.
    """
    db = get_firestore()
    document_id = _new_document_id()
    now = datetime.now(timezone.utc)
    total_bytes = sum(spec.size_bytes for spec in file_specs)

    from shared.models.document import EXTENSION_BY_CONTENT_TYPE

    files: list[dict] = []
    for spec in file_specs:
        file_id = _new_file_id()
        extension = EXTENSION_BY_CONTENT_TYPE[spec.content_type]
        object_path = object_path_builder(
            document_id=document_id,
            file_id=file_id,
            extension=extension,
        )
        files.append(
            {
                "file_id": file_id,
                "file_name": spec.file_name,
                "content_type": spec.content_type,
                "size_bytes": spec.size_bytes,
                "gcs_object_path": object_path,
                "upload_completed_at": None,
            }
        )

    payload = {
        "id": document_id,
        "uid": uid,
        "domain": domain,
        "title": title,
        "status": DocumentStatus.PENDING_UPLOAD.value,
        "files": files,
        "file_count": len(files),
        "total_bytes": total_bytes,
        "idempotency_key": idempotency_key,
        "cypher_gcs_uri": None,      # set by worker when pipeline completes
        "processing_step": None,     # updated during processing for frontend polling
        "created_at": firebase_firestore.SERVER_TIMESTAMP,
        "updated_at": firebase_firestore.SERVER_TIMESTAMP,
        "finalized_at": None,
        "deleted_at": None,
        "error": None,
    }

    db.collection(_COLLECTION).document(document_id).set(payload)

    _log.info(
        "document_created document_id=%s uid=%s domain=%s file_count=%d total_bytes=%d",
        document_id,
        uid,
        domain,
        len(files),
        total_bytes,
    )

    # The returned object uses client-side timestamps as a best-effort
    # approximation; the canonical values written via SERVER_TIMESTAMP may
    # differ by up to a few hundred milliseconds.
    return Document(
        id=document_id,
        uid=uid,
        domain=domain,
        title=title,
        status=DocumentStatus.PENDING_UPLOAD,
        files=[DocumentFile(**f) for f in files],
        file_count=len(files),
        total_bytes=total_bytes,
        idempotency_key=idempotency_key,
        created_at=now,
        updated_at=now,
        finalized_at=None,
        deleted_at=None,
        error=None,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Reads
# ──────────────────────────────────────────────────────────────────────────────


def find_document_for_user(document_id: str, uid: str) -> Document | None:
    """Read a document if and only if it belongs to `uid` and is not deleted."""
    db = get_firestore()
    snapshot = db.collection(_COLLECTION).document(document_id).get()
    if not snapshot.exists:
        return None
    document = _snapshot_to_document(snapshot)
    if document.uid != uid or document.deleted_at is not None:
        return None
    return document


def find_document_by_idempotency_key(uid: str, idempotency_key: str) -> Document | None:
    """Look up a document by `(uid, idempotency_key)`. Returns None if absent.

    Backed by the `(uid, idempotency_key)` composite index declared in
    `firestore.indexes.json`.
    """
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
