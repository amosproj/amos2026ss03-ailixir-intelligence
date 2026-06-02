"""
Firestore persistence for the pipeline refinement playground.

Collections used (under project amos26):
  test_extractions  — one document per PDF processed (new doc each time)
  test_summaries    — one document per user_id (created once, updated in place)
"""

from __future__ import annotations

from datetime import datetime, timezone

from pipeline_refinement.config import get_firestore

_EXTRACTIONS_COL = "test_extractions"
_SUMMARIES_COL = "test_summaries"


def save_extraction(user_id: str, doc_name: str, extraction: dict) -> str:
    """
    Persist one extraction result as a new Firestore document.
    A new document is created on every call — nothing is overwritten.

    Returns the auto-generated Firestore document ID.
    """
    db = get_firestore()
    payload = {
        "user_id": user_id,
        "doc_name": doc_name,
        "document_type": extraction.get("document_type"),
        "document_purpose": extraction.get("document_purpose"),
        "entity_types": extraction.get("entity_types", {}),
        "edge_types": extraction.get("edge_types", []),
        "entities": extraction.get("entities", []),
        "relationships": extraction.get("relationships", []),
        "created_at": datetime.now(timezone.utc),
    }
    ref = db.collection(_EXTRACTIONS_COL).document()
    ref.set(payload)
    return ref.id


def get_summary(user_id: str) -> dict | None:
    """
    Return the current summary document for a user, or None if not yet created.

    Returned dict contains at minimum:
      summary (str), last_updated (datetime), document_count (int)
    """
    db = get_firestore()
    doc = db.collection(_SUMMARIES_COL).document(user_id).get()
    return doc.to_dict() if doc.exists else None


def upsert_summary(
    user_id: str,
    summary_text: str,
    last_extraction_id: str,
) -> None:
    """
    Create or overwrite the summary document for a user.

    document_count is incremented from whatever exists in Firestore,
    so it always reflects the total number of documents processed.
    """
    db = get_firestore()
    ref = db.collection(_SUMMARIES_COL).document(user_id)

    existing = ref.get().to_dict() or {}
    prev_count: int = existing.get("document_count") or 0

    ref.set({
        "user_id": user_id,
        "summary": summary_text,
        "last_updated": datetime.now(timezone.utc),
        "document_count": prev_count + 1,
        "last_extraction_id": last_extraction_id,
    })
