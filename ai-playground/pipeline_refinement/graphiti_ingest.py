"""
Graphiti episode ingestion for the pipeline_refinement playground.

Each document upload = one Graphiti episode.
group_id = user_id gives every patient their own namespace in Neo4j.

The FIXED medical schema from medical_schema.py is used for every episode.
This is what enables Graphiti to:
  - Merge "Patient-1" from doc 1 with "Patient-1" from doc 5 into one node
  - Update entity properties when new documents provide newer values
  - Expire old fact-edges and create new ones when data changes (temporal effect)

Patient identity header (name, DOB) is prepended to every episode body so that
Graphiti always sees a consistent anchor and extracts ONE Patient entity across
all documents, even when individual documents refer to the patient differently
(e.g. "H. Schmidt" vs "Hans Schmidt" vs "Herr Schmidt").

reference_time is set to the document's own date (extracted by Gemini from the PDF),
so the temporal graph reflects the REAL medical timeline rather than ingestion time.
If PSA was measured in January and another in March, Graphiti will correctly order
those facts and expire the earlier value when the newer one arrives.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType

from pipeline_refinement.medical_schema import (
    MEDICAL_EDGE_TYPE_MAP,
    MEDICAL_EDGE_TYPES,
    MEDICAL_ENTITY_TYPES,
)

_log = logging.getLogger(__name__)


def _build_patient_header(user_id: str, patient_info: dict) -> str:
    """
    Build a fixed identity sentence prepended to every episode body.

    Graphiti's internal LLM reads this text before any document content, so it
    always extracts ONE Patient entity with a consistent anchor ID. Without this,
    two documents that refer to the same person differently (abbreviations, titles,
    German vs English name order) would produce separate Patient nodes that never
    merge — breaking the patient-centred graph.

    patient_info keys (all optional):
      name — canonical full name  (e.g. "Hans Schmidt")
      dob  — date of birth string (e.g. "1979-03-12")
    """
    parts: list[str] = []
    if patient_info.get("name"):
        parts.append(f"Patient: {patient_info['name']}")
    parts.append(f"Patient ID: {user_id}")
    if patient_info.get("dob"):
        parts.append(f"DOB: {patient_info['dob']}")
    return ", ".join(parts) + ".\n"


def _parse_doc_date(extraction: dict) -> datetime:
    """
    Parse the document date that Gemini extracted from the PDF.

    Tries multiple date formats that appear in German/international medical documents.
    Falls back to UTC now if the field is absent or unparseable — this means if Gemini
    could not find a date in the document, the ingestion timestamp is used instead.
    """
    raw = extraction.get("document_date")
    if not raw or str(raw).strip().lower() in ("null", "none", ""):
        _log.warning("No document_date in extraction — using ingestion time as reference_time")
        return datetime.now(timezone.utc)

    for fmt in (
        "%Y-%m-%d",      # ISO: 2024-03-15
        "%d.%m.%Y",      # German: 15.03.2024
        "%d/%m/%Y",      # European: 15/03/2024
        "%m/%d/%Y",      # US: 03/15/2024
        "%B %d, %Y",     # English long: March 15, 2024
        "%d %B %Y",      # European long: 15 March 2024
        "%Y/%m/%d",      # 2024/03/15
    ):
        try:
            return datetime.strptime(str(raw).strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    _log.warning("Could not parse document_date=%r — using ingestion time", raw)
    return datetime.now(timezone.utc)


async def ingest_document_episode(
    graphiti: Graphiti,
    *,
    user_id: str,
    doc_name: str,
    extraction: dict,
    patient_info: dict | None = None,
) -> str:
    """
    Add one document to the Graphiti knowledge graph as a single episode.

    patient_info (optional dict):
      name — canonical patient name  (set via PATIENT_NAME env var)
      dob  — patient date of birth   (set via PATIENT_DOB  env var)
    If provided, a fixed identity header is prepended to the episode body so
    Graphiti always anchors to ONE Patient node across all documents.

    reference_time is set to the actual document date (extracted by Gemini),
    not the ingestion timestamp. This ensures temporal ordering in the graph
    matches the real medical timeline.

    Returns the episode_name (stable key visible in Neo4j).
    """
    doc_date = _parse_doc_date(extraction)
    episode_name = f"{user_id}__{doc_name}__{doc_date.strftime('%Y%m%d_%H%M%S')}"

    doc_type    = extraction.get("document_type", "document")
    doc_purpose = extraction.get("document_purpose", "")
    episode_body = extraction.get("episode_body", "")

    if not episode_body:
        raise ValueError(f"extraction has no episode_body for doc '{doc_name}'")

    # Prepend patient header so Graphiti always extracts one consistent Patient entity
    header = _build_patient_header(user_id, patient_info or {})
    episode_body = header + episode_body

    _log.info(
        "graphiti_ingest_start episode=%s user=%s doc_date=%s",
        episode_name, user_id, doc_date.date(),
    )

    await graphiti.add_episode(
        name=episode_name,
        episode_body=episode_body,
        source=EpisodeType.text,
        source_description=f"{doc_type} — {doc_purpose}",
        reference_time=doc_date,            # real document date, not ingestion time
        group_id=user_id,                    # patient namespace for cross-doc merging
        entity_types=MEDICAL_ENTITY_TYPES,  # fixed schema enables entity merging
        edge_types=MEDICAL_EDGE_TYPES,
        edge_type_map=MEDICAL_EDGE_TYPE_MAP,
    )

    _log.info("graphiti_ingest_done episode=%s doc_date=%s", episode_name, doc_date.date())
    return episode_name
