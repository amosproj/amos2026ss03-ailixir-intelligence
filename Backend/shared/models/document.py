"""
Domain model for an uploaded document and its lifecycle status.

A `Document` is a row in the `documents` Firestore collection. The same shape is
used by the API (writes), the ingestion worker (status updates), and any future
service that reads document state.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class DocumentStatus(str, Enum):
    """Lifecycle states for an uploaded document.

    Forward path: PENDING_UPLOAD → UPLOADED → PROCESSING → EXTRACTED.
    From any state the document may transition to FAILED, which is terminal.
    """

    PENDING_UPLOAD = "pending_upload"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    EXTRACTED = "extracted"
    FAILED = "failed"


class Document(BaseModel):
    id: str
    uid: str
    file_name: str
    content_type: str
    size_bytes: int
    domain: str
    status: DocumentStatus
    gcs_uri: str | None = None
    cypher_gcs_uri: str | None = None   # set when pipeline completes; frontend reads this
    processing_step: str | None = None  # fine-grained progress for frontend polling
    created_at: datetime
    updated_at: datetime
    error: str | None = None
