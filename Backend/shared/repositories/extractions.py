"""
Repository for the `extractions` Firestore collection.

Each document has at most one extraction record, keyed by doc_id.

The new LLM pipeline populates: document_type, document_purpose, document_date,
episode_body. The old OCR fields (raw_text, extracted_fields, confidence_score)
are preserved as optional for backward compatibility with existing records.
"""

import logging

from firebase_admin import firestore

from shared.firestore import get_firestore
from shared.models.extraction import Extraction

_log = logging.getLogger(__name__)
_COLLECTION = "extractions"

# Firestore hard limit is 1 MB per document. The episode_body from the LLM
# extraction is typically 150-350 words (~2 KB), well within the limit.
# The old raw_text field could be up to 200K chars; that cap is kept for
# any callers that still populate raw_text.
_MAX_RAW_TEXT_CHARS = 200_000


def save_extraction(extraction: Extraction) -> None:
    """Upsert the extraction result for a document.

    Persists both old OCR fields (for backward compat) and new LLM fields.
    raw_text is capped at _MAX_RAW_TEXT_CHARS; other fields are stored as-is.
    """
    db = get_firestore()

    raw_text_in = extraction.raw_text or ""
    raw_text_out = raw_text_in[:_MAX_RAW_TEXT_CHARS] or None

    db.collection(_COLLECTION).document(extraction.doc_id).set(
        {
            "doc_id":             extraction.doc_id,
            "uid":                extraction.uid,
            "document_type":      extraction.document_type,
            # Old OCR fields
            "confidence_score":   extraction.confidence_score,
            "extracted_fields":   extraction.extracted_fields,
            "raw_text":           raw_text_out,
            "raw_text_chars":     len(raw_text_out) if raw_text_out else 0,
            "raw_text_truncated": len(raw_text_in) > _MAX_RAW_TEXT_CHARS,
            # New LLM fields
            "document_purpose":   extraction.document_purpose,
            "document_date":      extraction.document_date,
            "episode_body":       extraction.episode_body,
            "extracted_at":       firestore.SERVER_TIMESTAMP,
        }
    )
    _log.info(
        "extraction_saved doc_id=%s doc_type=%s purpose=%s doc_date=%s episode_len=%d",
        extraction.doc_id,
        extraction.document_type,
        extraction.document_purpose or "",
        extraction.document_date or "",
        len(extraction.episode_body or ""),
    )


def get_extraction(doc_id: str) -> Extraction | None:
    """Return the extraction for a document, or None if not found.

    Old extraction records pre-dating the new LLM fields load with those
    fields as None — the Extraction model declares them optional so this
    works without a migration.
    """
    db = get_firestore()
    snap = db.collection(_COLLECTION).document(doc_id).get()
    if not snap.exists:
        return None
    return Extraction(**snap.to_dict())
