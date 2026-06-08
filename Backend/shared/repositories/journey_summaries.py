"""
Repository for the `journey_summaries` Firestore collection.

One document per user (keyed by uid). Created when the first document is
processed; updated in-place after each subsequent document.

The summary text is fed back to the LLM extraction step as context for the
next document, so each new document is interpreted relative to the patient's
known history — producing richer episode bodies and better entity merging.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from firebase_admin import firestore

from shared.firestore import get_firestore
from shared.models.journey_summary import JourneySummary

_log = logging.getLogger(__name__)
_COLLECTION = "journey_summaries"


def get_summary(uid: str) -> JourneySummary | None:
    """Return the current journey summary for a user, or None if not yet created."""
    db = get_firestore()
    doc = db.collection(_COLLECTION).document(uid).get()
    if not doc.exists:
        return None
    return JourneySummary(**doc.to_dict())


def upsert_summary(
    uid: str,
    summary_text: str,
    last_extraction_id: str,
) -> None:
    """Create or overwrite the journey summary for a user."""
    db = get_firestore()
    ref = db.collection(_COLLECTION).document(uid)
    existing = ref.get().to_dict() or {}
    new_count = (existing.get("document_count") or 0) + 1
    ref.set({
        "uid": uid,
        "summary": summary_text,
        "last_updated": datetime.now(timezone.utc),
        "document_count": new_count,
        "last_extraction_id": last_extraction_id,
    })
    _log.info(
        "journey_summary_saved uid=%s document_count=%d",
        uid,
        new_count,
    )
