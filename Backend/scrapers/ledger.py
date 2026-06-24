"""Dedup ledger adapter for the scraper.

Primary backend is the global Firestore collection `literature_papers` (via
shared.repositories.literature_papers) — durable and shared across instances, which
is what a Cloud Run deployment needs (the local filesystem is ephemeral there).

If Firebase is not configured / reachable (e.g. local dev without an admin key), this
falls back to the local `data/pubmed/index.json` file so the scraper still runs and
dedups within a single machine. The backend is decided once per process and cached.
"""

from __future__ import annotations

import json
import logging

from . import INDEX_FILE_PATH

_log = logging.getLogger(__name__)

_repo = None       # the shared Firestore repo module, or None for the file fallback
_decided = False   # whether we've chosen a backend yet


def _backend():
    """Return the Firestore repo module, or None to use the local-file fallback."""
    global _repo, _decided
    if _decided:
        return _repo
    _decided = True
    try:
        from shared.firestore import get_firestore
        from shared.repositories import literature_papers as repo

        get_firestore()  # raises if Firebase creds are missing/invalid
        _repo = repo
        _log.info("literature ledger: using Firestore collection 'literature_papers'")
    except Exception as e:  # ImportError, FileNotFoundError, auth/network errors
        _repo = None
        _log.warning(
            "literature ledger: Firestore unavailable (%s); "
            "falling back to local index file %s",
            e,
            INDEX_FILE_PATH,
        )
    return _repo


# ── local-file fallback helpers ───────────────────────────────────────────────

def _local_seen() -> set[str]:
    try:
        with open(INDEX_FILE_PATH, encoding="utf-8-sig") as f:
            return {str(x) for x in json.load(f).get("indexes", [])}
    except Exception:
        return set()


def _local_add(pmid: str) -> None:
    seen = _local_seen()
    seen.add(str(pmid))
    with open(INDEX_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump({"indexes": sorted(seen)}, f, indent=2)


# ── public API used by the scraper ────────────────────────────────────────────

def filter_new(pmids) -> set[str]:
    """Return the subset of `pmids` not yet embedded (the ones worth scraping)."""
    pmids = {str(p) for p in pmids}
    repo = _backend()
    if repo is not None:
        return pmids - repo.get_indexed_pmids(pmids)
    return pmids - _local_seen()


def record(
    pmid,
    *,
    doi: str | None = None,
    title: str | None = None,
    disease: str | None = None,
    chunk_count: int = 0,
    full_text: bool = False,
    source: str = "pubmed",
) -> None:
    """Mark a paper as embedded (or append a new disease to an existing entry)."""
    repo = _backend()
    if repo is not None:
        repo.record_paper(
            str(pmid),
            doi=doi,
            title=title,
            disease=disease,
            chunk_count=chunk_count,
            full_text=full_text,
            source=source,
        )
    else:
        _local_add(pmid)
