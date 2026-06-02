"""
Firestore persistence for the pipeline refinement playground.

Collections (project amos26):
  test_extractions — one document per PDF processed (new doc each time)
  test_summaries   — one document per user_id (created once, updated in place)

Extraction document shape:
  user_id, doc_name, document_type, document_purpose,
  episode_body      ← the narrative paragraph Graphiti will receive
  entity_types      ← LLM-defined schemas (list of {name, description, fields})
  edge_types        ← LLM-defined relationship classes (list of {name, description})
  edge_type_map     ← valid source/target/relations constraints (list of {source, target, relations})
  created_at
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
        "episode_body": extraction.get("episode_body", ""),
        "entity_types": extraction.get("entity_types", []),
        "edge_types": extraction.get("edge_types", []),
        "edge_type_map": extraction.get("edge_type_map", []),
        "created_at": datetime.now(timezone.utc),
    }
    ref = db.collection(_EXTRACTIONS_COL).document()
    ref.set(payload)
    return ref.id


def get_summary(user_id: str) -> dict | None:
    """
    Return the current summary document for a user, or None if not yet created.

    Returned dict contains: summary (str), last_updated, document_count (int).
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
    document_count increments each call so it always reflects total docs processed.
    """
    db = get_firestore()
    ref = db.collection(_SUMMARIES_COL).document(user_id)
    existing = ref.get().to_dict() or {}
    ref.set({
        "user_id": user_id,
        "summary": summary_text,
        "last_updated": datetime.now(timezone.utc),
        "document_count": (existing.get("document_count") or 0) + 1,
        "last_extraction_id": last_extraction_id,
    })
