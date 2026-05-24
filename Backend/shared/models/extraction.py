"""
Domain model for the OCR extraction result of a document.

One `Extraction` is stored in the `extractions` Firestore collection per document.
It holds only the structured fields the OCR model pulled out — no embeddings,
no raw text blocks, no internal pipeline metadata.

The frontend and other services read this to display what was found in the document.
"""

from datetime import datetime

from pydantic import BaseModel


class Extraction(BaseModel):
    doc_id: str
    uid: str
    document_type: str
    confidence_score: float | None = None
    extracted_fields: dict
    extracted_at: datetime
