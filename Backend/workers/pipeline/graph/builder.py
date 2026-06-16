"""
Graphiti episode ingestion with fixed medical schema.

Each document upload = one Graphiti episode. group_id = uid gives every patient
their own namespace in Neo4j, enabling cross-document entity merging.

The FIXED medical schema from medical_schema.py is passed to add_episode() on
every call. This is what enables Graphiti to:
  - Merge the same Patient/Diagnosis across multiple documents into one node
  - Expire old fact-edges and create new ones when newer data arrives (temporal)
  - Use consistent relationship types regardless of the document type

reference_time is set to the actual document date extracted by the LLM, not the
ingestion timestamp. This ensures the temporal graph reflects the real medical
timeline (e.g. a PSA from January is correctly ordered before one from March).

A patient identity header is prepended to every episode body so Graphiti always
anchors to ONE Patient entity across all documents, even when individual
documents refer to the patient differently (abbreviations, titles, name order).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType

from workers.pipeline.graph.medical_schema import (
    MEDICAL_EDGE_TYPE_MAP,
    MEDICAL_EDGE_TYPES,
    MEDICAL_ENTITY_TYPES,
)

_log = logging.getLogger(__name__)


def _build_patient_header(uid: str) -> str:
    """
    Fixed identity sentence prepended to every episode body.

    Graphiti's internal LLM reads this before any document content, so it
    always extracts ONE Patient entity anchored to the user's Firebase UID.
    Without this, two documents that refer to the same person differently
    (abbreviations, German vs English name order) would produce separate
    Patient nodes that never merge.
    """
    return f"Patient ID: {uid}.\n"


def _parse_doc_date(extraction: dict) -> datetime:
    """
    Parse the document date extracted by the LLM from the PDF.

    Tries multiple date formats found in German/international medical documents.
    Falls back to UTC now if the field is absent or unparseable.
    """
    raw = extraction.get("document_date")
    if not raw or str(raw).strip().lower() in ("null", "none", ""):
        _log.warning("No document_date in extraction — using ingestion time as reference_time")
        return datetime.now(timezone.utc)

    for fmt in (
        "%Y-%m-%d",     # ISO: 2024-03-15
        "%d.%m.%Y",     # German: 15.03.2024
        "%d/%m/%Y",     # European: 15/03/2024
        "%m/%d/%Y",     # US: 03/15/2024
        "%B %d, %Y",    # English long: March 15, 2024
        "%d %B %Y",     # European long: 15 March 2024
        "%Y/%m/%d",     # 2024/03/15
    ):
        try:
            return datetime.strptime(str(raw).strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    _log.warning("Could not parse document_date=%r — using ingestion time", raw)
    return datetime.now(timezone.utc)


async def ingest(
    graphiti: Graphiti,
    *,
    uid: str,
    doc_id: str,
    doc_name: str,
    extraction: dict,
) -> str:
    """
    Add one document to the Graphiti knowledge graph as a single episode.

    extraction must contain:
      episode_body     — rich clinical narrative (built by the LLM extraction step)
      document_type    — used for the episode source_description
      document_purpose — used for the episode source_description
      document_date    — YYYY-MM-DD or similar; sets the temporal reference

    Returns the episode_name, which the Cypher exporter uses to query the
    nodes and relationships that belong to this specific document.
    """
    doc_date = _parse_doc_date(extraction)
    episode_name = f"{uid}__{doc_id}__{doc_date.strftime('%Y%m%d_%H%M%S')}"

    episode_body = extraction.get("episode_body", "")
    if not episode_body:
        raise ValueError(f"extraction has no episode_body for doc '{doc_name}'")

    # Prepend patient identity header so Graphiti extracts one consistent Patient node.
    episode_body = _build_patient_header(uid) + episode_body

    doc_type = extraction.get("document_type", "document")
    doc_purpose = extraction.get("document_purpose", "")

    _log.info(
        "graph_ingest_start episode=%s uid=%s doc_date=%s body_len=%d",
        episode_name, uid, doc_date.date(), len(episode_body),
    )

    await graphiti.add_episode(
        name=episode_name,
        episode_body=episode_body,
        source=EpisodeType.text,
        source_description=f"{doc_type} — {doc_purpose}",
        reference_time=doc_date,           # real document date, not ingestion time
        group_id=uid,                       # patient namespace for cross-doc merging
        entity_types=MEDICAL_ENTITY_TYPES, # fixed schema enables entity merging
        edge_types=MEDICAL_EDGE_TYPES,
        edge_type_map=MEDICAL_EDGE_TYPE_MAP,
    )

    _log.info("graph_ingest_done episode=%s doc_date=%s", episode_name, doc_date.date())
    return episode_name
