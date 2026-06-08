"""
Repository for the `extractions` Firestore collection.

Each document has at most one extraction record, keyed by doc_id.
Stores clean OCR output and (optionally) the full raw OCR text — no
embeddings, no pipeline internals.
"""

import logging

from firebase_admin import firestore

from shared.firestore import get_firestore
from shared.models.extraction import Extraction

_log = logging.getLogger(__name__)
_COLLECTION = "extractions"

# Firestore enforces a 1 MB hard limit per document. Average UTF-8 char
# encoded text is ~1-3 bytes; 200,000 chars leaves a generous margin for
# the other fields and any multi-byte German diacritics. Documents whose
# OCR exceeds this cap get the leading slice persisted plus a truncated
# flag — the UI surfaces the flag so users aren't misled into thinking
# they're seeing the full document.
_MAX_RAW_TEXT_CHARS = 200_000


def save_extraction(extraction: Extraction) -> None:
    """Upsert the OCR extraction result for a document.

    raw_text is capped at _MAX_RAW_TEXT_CHARS to stay safely under
    Firestore's per-document size limit. raw_text_chars and
    raw_text_truncated are derived from the persisted slice, not from
    the incoming Extraction — callers can pass uncapped text and the
    repository handles the bookkeeping.
    """
    db = get_firestore()
    raw_text_in = extraction.raw_text or ""
    raw_text_out = raw_text_in[:_MAX_RAW_TEXT_CHARS] or None
    db.collection(_COLLECTION).document(extraction.doc_id).set(
        {
            "doc_id": extraction.doc_id,
            "uid": extraction.uid,
            "document_type": extraction.document_type,
            "confidence_score": extraction.confidence_score,
            "extracted_fields": extraction.extracted_fields,
            "raw_text": raw_text_out,
            "raw_text_chars": len(raw_text_out) if raw_text_out else 0,
            "raw_text_truncated": len(raw_text_in) > _MAX_RAW_TEXT_CHARS,
            "extracted_at": firestore.SERVER_TIMESTAMP,
        }
    )
    _log.info(
        "extraction_saved doc_id=%s doc_type=%s raw_text_chars=%d truncated=%s",
        extraction.doc_id,
        extraction.document_type,
        len(raw_text_out) if raw_text_out else 0,
        len(raw_text_in) > _MAX_RAW_TEXT_CHARS,
    )


def get_extraction(doc_id: str) -> Extraction | None:
    """Return the extraction for a document, or None if not found.

    Old extraction records pre-dating the raw_text fields load with
    raw_text=None / raw_text_chars=None / raw_text_truncated=None —
    the Extraction model declares them as optional so this works
    without a migration.
    """
    db = get_firestore()
    snap = db.collection(_COLLECTION).document(doc_id).get()
    if not snap.exists:
        return None
    return Extraction(**snap.to_dict())
