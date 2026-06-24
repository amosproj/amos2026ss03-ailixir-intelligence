"""
Repository for the `literature_papers` Firestore collection — the global dedup
ledger for the scraped literature corpus.

One document per unique paper, keyed by PubMed ID. This is a *global* collection
(not per-user): it sits alongside `users` in the same Firestore project and records
which papers have already been embedded into the AstraDB vector store, so the scraper
can skip re-downloading / re-embedding papers it already has.

Disease associations are append-only (`ArrayUnion`): when a paper that already exists
is found again under a different disease, we add the disease tag rather than
re-embedding — the chunk vectors in AstraDB are untouched.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from google.cloud import firestore as gcp_firestore

from shared.firestore import get_firestore
from shared.models.literature_paper import LiteraturePaper

_log = logging.getLogger(__name__)
_COLLECTION = "literature_papers"


def get_paper(pmid: str) -> LiteraturePaper | None:
    """Return the ledger entry for a paper, or None if it has not been embedded."""
    db = get_firestore()
    doc = db.collection(_COLLECTION).document(str(pmid)).get()
    if not doc.exists:
        return None
    return LiteraturePaper(**doc.to_dict())


def get_indexed_pmids(pmids: set[str]) -> set[str]:
    """Return the subset of `pmids` already present in the ledger.

    Uses a single batched `get_all` read rather than one round-trip per id, so the
    scraper's "which of these candidates are new?" diff costs one call regardless of
    how many candidates a search returned.
    """
    pmids = {str(p) for p in pmids}
    if not pmids:
        return set()
    db = get_firestore()
    col = db.collection(_COLLECTION)
    snapshots = db.get_all([col.document(p) for p in pmids])
    return {snap.id for snap in snapshots if snap.exists}


def record_paper(
    pmid: str,
    *,
    doi: str | None = None,
    title: str | None = None,
    disease: str | None = None,
    chunk_count: int = 0,
    full_text: bool = False,
    source: str = "pubmed",
) -> None:
    """Record a freshly embedded paper, or append a disease to an existing one.

    Transactional so two scrape runs touching the same pmid concurrently can't tear
    the document. On first sight the full record is written (with `embedded_at`); on
    later sights only `diseases` (ArrayUnion) and `updated_at` are touched —
    `chunk_count` / `embedded_at` are preserved, because the vectors are not re-created.
    """
    pmid = str(pmid)
    db = get_firestore()
    ref = db.collection(_COLLECTION).document(pmid)
    now = datetime.now(timezone.utc)
    new_diseases = [disease] if disease else []

    @gcp_firestore.transactional
    def _txn(transaction: gcp_firestore.Transaction) -> bool:
        snapshot = ref.get(transaction=transaction)
        if snapshot.exists:
            transaction.update(
                ref,
                {
                    "diseases": gcp_firestore.ArrayUnion(new_diseases),
                    "updated_at": now,
                },
            )
            return False
        transaction.set(
            ref,
            {
                "pmid": pmid,
                "doi": doi,
                "title": title,
                "diseases": new_diseases,
                "chunk_count": chunk_count,
                "full_text": full_text,
                "source": source,
                "embedded_at": now,
                "updated_at": now,
            },
        )
        return True

    created = _txn(db.transaction())
    _log.info(
        "literature_paper_%s pmid=%s disease=%s chunks=%d",
        "created" if created else "updated",
        pmid,
        disease,
        chunk_count,
    )
