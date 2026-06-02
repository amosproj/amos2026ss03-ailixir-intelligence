"""
Graphiti episode ingestion for the pipeline_refinement playground.

Each document upload = one Graphiti episode.
group_id = user_id gives every patient their own namespace in Neo4j.

The FIXED medical schema from medical_schema.py is used for every episode.
This is what enables Graphiti to:
  - Merge "Patient-1" from doc 1 with "Patient-1" from doc 5 into one node
  - Update entity properties when new documents provide newer values
  - Expire old fact-edges and create new ones when data changes (temporal effect)
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


async def ingest_document_episode(
    graphiti: Graphiti,
    *,
    user_id: str,
    doc_name: str,
    extraction: dict,
) -> str:
    """
    Add one document to the Graphiti knowledge graph as a single episode.

    Returns the episode_name (stable key visible in Neo4j).
    """
    ts = datetime.now(timezone.utc)
    episode_name = f"{user_id}__{doc_name}__{ts.strftime('%Y%m%d_%H%M%S')}"

    doc_type    = extraction.get("document_type", "document")
    doc_purpose = extraction.get("document_purpose", "")
    episode_body = extraction.get("episode_body", "")

    if not episode_body:
        raise ValueError(f"extraction has no episode_body for doc '{doc_name}'")

    _log.info("graphiti_ingest_start episode=%s user=%s", episode_name, user_id)

    await graphiti.add_episode(
        name=episode_name,
        episode_body=episode_body,
        source=EpisodeType.text,
        source_description=f"{doc_type} — {doc_purpose}",
        reference_time=ts,
        group_id=user_id,                      # patient namespace
        entity_types=MEDICAL_ENTITY_TYPES,     # fixed schema → enables merging
        edge_types=MEDICAL_EDGE_TYPES,
        edge_type_map=MEDICAL_EDGE_TYPE_MAP,
    )

    _log.info("graphiti_ingest_done episode=%s", episode_name)
    return episode_name
