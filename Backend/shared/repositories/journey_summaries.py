"""
Repository for the `journey_summaries` Firestore collection.

One document per user (keyed by uid). Created when the first document is
processed; updated in-place after each subsequent document.

The summary text is fed back to the LLM extraction step as context for the
next document, so each new document is interpreted relative to the patient's
known history — producing richer episode bodies and better entity merging.

Concurrency model
-----------------
The writes use a Firestore transaction so that two extractions for the same
user processed in parallel (multi-file uploads, or two PDFs landing close
together in time) can't:

  - Lose updates to `document_count` (classic read-modify-write race).
  - Stomp each other's `last_extraction_id` arbitrarily.

The summary text itself is "latest writer wins" by design — each writer's
summary text was generated from a possibly-stale read of the journey, so
deterministically choosing one of them is the only sane option without
serialising LLM calls. The transaction guarantees we at least pick ONE of
the writers' summaries cleanly rather than tearing the document.

A stronger guarantee (no concurrent summary updates per user at all) would
require Pub/Sub message ordering keyed by uid; tracked as a follow-up.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from google.cloud import firestore as gcp_firestore

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
    """Create or atomically update the journey summary for a user.

    Uses a Firestore transaction to make the document_count increment
    race-safe: the read of the current count and the write of count+1
    are atomic at the storage layer. Without this, two concurrent
    workers processing the same user's documents would both read N and
    both write N+1, dropping one of the increments on the floor.

    The summary text is overwritten (last writer wins). See module
    docstring for the trade-off and how to escalate further if needed.
    """
    db = get_firestore()
    ref = db.collection(_COLLECTION).document(uid)

    @gcp_firestore.transactional
    def _txn(transaction: gcp_firestore.Transaction) -> int:
        # All reads in a Firestore transaction must precede any writes.
        snapshot = ref.get(transaction=transaction)
        existing = snapshot.to_dict() or {}
        new_count = int(existing.get("document_count") or 0) + 1
        # Re-stamp `last_updated` inside the transaction so a retry on
        # conflict carries the correct write-time, not the pre-retry time.
        transaction.set(
            ref,
            {
                "uid":                uid,
                "summary":            summary_text,
                "last_updated":       datetime.now(timezone.utc),
                "document_count":     new_count,
                "last_extraction_id": last_extraction_id,
            },
        )
        return new_count

    transaction = db.transaction()
    new_count = _txn(transaction)
    _log.info(
        "journey_summary_saved uid=%s document_count=%d last_extraction_id=%s",
        uid,
        new_count,
        last_extraction_id,
    )
