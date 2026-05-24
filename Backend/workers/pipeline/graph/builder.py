"""
Graphiti episode ingestion.

Converts the OCR output into a Graphiti episode and commits it to Neo4j.
Entity and relationship extraction is handled internally by Graphiti's LLM.
The episode_name returned here is the stable key used by exporter.py.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType

from workers.pipeline.graph.prompts import build_episode_body, source_description

_log = logging.getLogger(__name__)


async def ingest(
    graphiti: Graphiti,
    *,
    doc_id: str,
    file_name: str,
    doc_type: str,
    ocr_data: dict,
) -> str:
    """
    Add one document to the knowledge graph.

    Returns the episode_name, which the Cypher exporter uses to query the
    nodes and relationships that belong to this specific document.
    """
    episode_name = f"{doc_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    await graphiti.add_episode(
        name=episode_name,
        episode_body=build_episode_body(doc_id, file_name, ocr_data),
        source=EpisodeType.text,
        source_description=source_description(file_name, doc_type),
        reference_time=datetime.now(timezone.utc),
    )

    _log.info("graph_episode_ingested doc_id=%s episode=%s", doc_id, episode_name)
    return episode_name
