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
        "created_at": firebase_firestore.SERVER_TIMESTAMP,
        "updated_at": firebase_firestore.SERVER_TIMESTAMP,
        "finalized_at": None,
        "deleted_at": None,
        "error": None,
    }

    db.collection(_COLLECTION).document(document_id).set(payload)

    _log.info(
        "document_created document_id=%s uid=%s domain=%s file_count=%d total_bytes=%d",
        document_id, uid, domain, len(files), total_bytes,
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
    query = (
        db.collection(_COLLECTION)
        .where(filter=FieldFilter("uid", "==", uid))
        .where(filter=FieldFilter("idempotency_key", "==", idempotency_key))
        .limit(1)
    )
    for snapshot in query.stream():
        return _snapshot_to_document(snapshot)
    return None


def list_documents_for_user(
    uid: str,
    *,
    domain: str | None = None,
    status: DocumentStatus | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[Document], str | None]:
    """Paginated list of a user's documents, newest first.

    Returns `(documents, next_cursor)`. `next_cursor` is None when no further
    pages remain. Excludes soft-deleted documents.
    """
    db = get_firestore()
    query = (
        db.collection(_COLLECTION)
        .where(filter=FieldFilter("uid", "==", uid))
        .where(filter=FieldFilter("deleted_at", "==", None))
        .order_by("created_at", direction=Query.DESCENDING)
        .order_by("id", direction=Query.DESCENDING)
    )

    if domain is not None:
        query = query.where(filter=FieldFilter("domain", "==", domain))
    if status is not None:
        query = query.where(filter=FieldFilter("status", "==", status.value))

    # Fetch one extra to detect "is there a next page".
    query = query.limit(limit + 1)

    if cursor:
        cursor_dt, cursor_id = decode_cursor(cursor)
        query = query.start_after([cursor_dt, cursor_id])

    snapshots = list(query.stream())
    has_next = len(snapshots) > limit
    if has_next:
        snapshots = snapshots[:limit]

    documents = [_snapshot_to_document(s) for s in snapshots]

    next_cursor: str | None = None
    if has_next and documents:
        last = documents[-1]
        next_cursor = _encode_cursor(last.created_at, last.id)

    return documents, next_cursor


# ──────────────────────────────────────────────────────────────────────────────
# State transitions
# ──────────────────────────────────────────────────────────────────────────────

class DocumentStateError(Exception):
    """Raised when a transition is attempted from an incompatible state."""

    def __init__(self, current_status: DocumentStatus):
        super().__init__(f"document is in state {current_status.value}")
        self.current_status = current_status


def mark_uploaded(
    document_id: str,
    uid: str,
    uploaded_file_ids: Iterable[str],
) -> Document:
    """Atomically transition `pending_upload` → `uploaded`.

    Uses a Firestore transaction so concurrent finalize attempts cannot both
    succeed. Refuses if the document is missing, owned by another user, soft
    deleted, or in any state other than `pending_upload`.

    `uploaded_file_ids` is the set of files verified to exist in GCS — these
    get an `upload_completed_at` stamp. The document's `file_count` is updated
    to match (partial uploads are tolerated; the worker handles them).
    """
    db = get_firestore()
    doc_ref = db.collection(_COLLECTION).document(document_id)
    uploaded_ids = set(uploaded_file_ids)
    now = datetime.now(timezone.utc)

    @transactional
    def _txn(transaction: Transaction) -> Document:
        snapshot = doc_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise LookupError("document not found")

        data = snapshot.to_dict() or {}
        if data.get("uid") != uid or data.get("deleted_at") is not None:
            raise LookupError("document not found")

        current_status = DocumentStatus(data["status"])
        if current_status is not DocumentStatus.PENDING_UPLOAD:
            raise DocumentStateError(current_status)

        files: list[dict] = list(data.get("files", []))
        updated_files: list[dict] = []
        for file_dict in files:
            if file_dict["file_id"] in uploaded_ids:
                file_dict = {**file_dict, "upload_completed_at": now}
            updated_files.append(file_dict)

        transaction.update(
            doc_ref,
            {
                "status": DocumentStatus.UPLOADED.value,
                "files": updated_files,
                "file_count": len(uploaded_ids),
                "finalized_at": firebase_firestore.SERVER_TIMESTAMP,
                "updated_at": firebase_firestore.SERVER_TIMESTAMP,
            },
        )

        return Document(
            **{
                **data,
                "status": DocumentStatus.UPLOADED.value,
                "files": updated_files,
                "file_count": len(uploaded_ids),
                "finalized_at": now,
                "updated_at": now,
            }
        )

    document = _txn(db.transaction())

    _log.info(
        "document_finalized document_id=%s uid=%s uploaded_count=%d declared_count=%d",
        document_id, uid, len(uploaded_ids), document.file_count,
    )
    return document


def soft_delete(document_id: str, uid: str) -> None:
    """Mark a document as deleted. Refuses if status is `processing`.

    Files in GCS are not touched here — a background reconciliation job
    hard-deletes them after the retention window. This keeps the delete
    user-facing latency low and gives operators a window to undo.
    """
    db = get_firestore()
    doc_ref = db.collection(_COLLECTION).document(document_id)

    @transactional
    def _txn(transaction: Transaction) -> None:
        snapshot = doc_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise LookupError("document not found")

        data = snapshot.to_dict() or {}
        if data.get("uid") != uid or data.get("deleted_at") is not None:
            raise LookupError("document not found")

        current_status = DocumentStatus(data["status"])
        if current_status is DocumentStatus.PROCESSING:
            raise DocumentStateError(current_status)

        transaction.update(
            doc_ref,
            {
                "deleted_at": firebase_firestore.SERVER_TIMESTAMP,
                "updated_at": firebase_firestore.SERVER_TIMESTAMP,
            },
        )

    _txn(db.transaction())
    _log.info("document_soft_deleted document_id=%s uid=%s", document_id, uid)


def pending_files(document: Document) -> list[DocumentFile]:
    """Return files in a document that have not yet completed upload."""
    return [f for f in document.files if f.upload_completed_at is None]
