"""
Domain model for an uploaded document and its files.

A `Document` is one logical user upload (e.g. a multi-page blood report). It
owns an array of `DocumentFile` entries — one per physical file (each page of a
scanned PDF, each PNG from a phone camera burst).

The same shapes are used by the API (creates, reads), the ingestion worker
(status transitions), and any future service that reads document state.
"""

from datetime import datetime
from enum import Enum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


# Domains the API will accept at create time. Sourced here as a constant for PR 1;
# eventually replaced by a runtime lookup against the domain-config service so
# adding a new domain stays a YAML-only change.
# TODO(domain-config): wire this to the domain-config service when it lands.
SUPPORTED_DOMAINS: frozenset[str] = frozenset({"medical", "finance"})


# Content types the API accepts for document files. Anything outside this set
# is rejected before any GCS work happens.
ALLOWED_FILE_CONTENT_TYPES: frozenset[str] = frozenset(
    {"image/png", "image/jpeg", "application/pdf"}
)


# Map content type to the file extension we store in GCS. Keeps the storage
# layout self-describing without trusting client-supplied extensions.
EXTENSION_BY_CONTENT_TYPE: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "application/pdf": "pdf",
}


# Hard caps. These are defensive limits, not product policy — protect Cloud Run
# from runaway requests. Real per-user quotas belong in a future ticket.
MAX_FILES_PER_DOCUMENT: int = 50
MAX_FILE_SIZE_BYTES: int = 20 * 1024 * 1024  # 20 MB per file
MAX_TOTAL_SIZE_BYTES: int = 200 * 1024 * 1024  # 200 MB per document


class DocumentStatus(str, Enum):
    """Lifecycle of a document.

    Forward: PENDING_UPLOAD → UPLOADED → PROCESSING → EXTRACTED.
    From any state the document may transition to FAILED, which is terminal.
    """

    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    FAILED = "failed"


class DocumentFile(BaseModel):
    """One physical file inside a Document."""

    file_id: str
    file_name: str
    content_type: str
    size_bytes: int
    gcs_object_path: str
    # Set by finalize once the API verifies the upload landed in GCS. Until
    # then, this file is conceptually still pending.
    upload_completed_at: datetime | None = None


class Document(BaseModel):
    """A user-owned logical document plus its files."""

    # `extra=ignore` lets us deserialize older Firestore records that lack
    # fields added by later schema changes (forward/backward compat).
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    id: str
    uid: str
    domain: str
    title: str | None
    status: DocumentStatus
    files: list[DocumentFile]
    file_count: int
    total_bytes: int

    # Per-uid idempotency key (SHA-256 hash of the client header).
    idempotency_key: str | None = None

    # Set by the worker when the knowledge-graph pipeline completes.
    # Frontend polls status and reads this once it's non-null.
    cypher_gcs_uri: str | None = None
    # Fine-grained progress written during processing for frontend polling.
    processing_step: str | None = None

    created_at: datetime
    updated_at: datetime
    # Set when status transitions to UPLOADED.
    finalized_at: datetime | None = None
    # Soft-delete marker. Reads filter on this; a background job hard-deletes
    # after retention.
    deleted_at: datetime | None = None
    # Populated when status transitions to FAILED.
    error: str | None = None
