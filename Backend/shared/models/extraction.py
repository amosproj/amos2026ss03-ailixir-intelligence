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

from pydantic import BaseModel


class Extraction(BaseModel):
    doc_id: str
    uid: str
    document_type: str
    confidence_score: float | None = None
    extracted_fields: dict
    # Optional. Full raw OCR text concatenated across files/pages.
    # Capped at the persistence layer (see shared.repositories.extractions)
    # to stay safely under Firestore's 1 MB per-document limit. Old
    # Extraction records pre-dating this field load with raw_text=None.
    raw_text: str | None = None
    # Length of the persisted raw_text (after the cap). Useful for the UI
    # to show a chip ("12,418 chars") without reading the whole body.
    raw_text_chars: int | None = None
    # True if raw_text was truncated to fit Firestore's document size limit.
    # When True, the displayed text is the leading slice — not all OCR
    # output. Lets the UI show a "Truncated" badge so users aren't misled.
    raw_text_truncated: bool | None = None
    extracted_at: datetime
