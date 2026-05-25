"""
Repository for the `extractions` Firestore collection.

Each document has at most one extraction record, keyed by doc_id.
Only clean OCR output is stored here — no embeddings, no pipeline internals.
"""

import logging

from firebase_admin import firestore

from shared.firestore import get_firestore
from shared.models.extraction import Extraction

_log = logging.getLogger(__name__)
_COLLECTION = "extractions"


def save_extraction(extraction: Extraction) -> None:
    """Upsert the OCR extraction result for a document."""
    db = get_firestore()
    db.collection(_COLLECTION).document(extraction.doc_id).set(
        {
            "doc_id": extraction.doc_id,
            "uid": extraction.uid,
            "document_type": extraction.document_type,
            "confidence_score": extraction.confidence_score,
            "extracted_fields": extraction.extracted_fields,
            "extracted_at": firestore.SERVER_TIMESTAMP,
        }
    )
    _log.info("extraction_saved doc_id=%s doc_type=%s", extraction.doc_id, extraction.document_type)


def get_extraction(doc_id: str) -> Extraction | None:
    """Return the extraction for a document, or None if not found."""
    db = get_firestore()
    snap = db.collection(_COLLECTION).document(doc_id).get()
    if not snap.exists:
        return None
    return Extraction(**snap.to_dict())
