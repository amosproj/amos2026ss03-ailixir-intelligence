"""
Domain model for the OCR extraction result of a document.

One `Extraction` is stored in the `extractions` Firestore collection per document.
It holds the structured fields the OCR model pulled out and, when available,
the raw OCR text concatenated across all pages/files in the document.

The frontend reads this to display what was found in the document. The
`raw_text` field is intentionally optional and capped by the repository
layer — only debug surfaces should rely on it being populated.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Extraction(BaseModel):
    doc_id: str
    uid: str
    document_type: str
    # Populated by old Document AI OCR pipeline; None in new LLM pipeline.
    confidence_score: float | None = None
    # Populated by old Document AI form parser; empty dict in new LLM pipeline.
    # `default_factory=dict` produces a fresh {} per instance — using `= {}`
    # directly would be a shared-mutable-default footgun even under Pydantic
    # (works today, but invites bugs the first time someone mutates it).
    extracted_fields: dict = Field(default_factory=dict)
    # Populated by old Document AI OCR pipeline; None in new LLM pipeline.
    raw_text: str | None = None
    raw_text_chars: int | None = None
    raw_text_truncated: bool | None = None
    # Fields populated by the new LLM extraction pipeline.
    document_purpose: str | None = None   # one-sentence role in patient journey
    document_date: str | None = None      # YYYY-MM-DD date from the document itself
    episode_body: str | None = None       # rich clinical narrative fed to Graphiti
    extracted_at: datetime
