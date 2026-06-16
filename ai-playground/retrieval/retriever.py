"""
Core Graphiti search functions for per-user knowledge graph retrieval.

All searches are scoped to a single user via group_ids=[user_id], which
mirrors how the ingestion pipeline stores episodes under group_id=uid.

Three retrieval modes:
  search_facts()    — edge-level search (relationship facts between entities).
                      Fast, returns list[EntityEdge].
  search_entities() — node-level search (medical entities by name/summary).
                      Returns list[EntityNode].
  search_combined() — edges + nodes together using cross-encoder reranking.
                      Most thorough; use when building an LLM context window.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from graphiti_core import Graphiti
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode
from graphiti_core.search.search_config import (
    EdgeReranker,
    EdgeSearchConfig,
    EdgeSearchMethod,
    NodeReranker,
    NodeSearchConfig,
    NodeSearchMethod,
    SearchConfig,
    SearchResults,
)
from graphiti_core.search.search_filters import SearchFilters

_log = logging.getLogger(__name__)

# Pre-built search configs ────────────────────────────────────────────────────

# Hybrid (semantic + keyword) edge search, reranked by a cross-encoder.
# Gives the best fact relevance at the cost of an extra Gemini reranker call.
_EDGE_HYBRID_CROSS_ENCODER = SearchConfig(
    edge_config=EdgeSearchConfig(
        search_methods=[EdgeSearchMethod.cosine_similarity, EdgeSearchMethod.bm25],
        reranker=EdgeReranker.cross_encoder,
    ),
    limit=10,
)

# Hybrid node search, reranked by RRF (no extra LLM call — faster).
_NODE_HYBRID_RRF = SearchConfig(
    node_config=NodeSearchConfig(
        search_methods=[NodeSearchMethod.cosine_similarity, NodeSearchMethod.bm25],
        reranker=NodeReranker.rrf,
    ),
    limit=10,
)

# Combined: edges with cross-encoder + nodes with RRF in a single call.
_COMBINED_HYBRID = SearchConfig(
    edge_config=EdgeSearchConfig(
        search_methods=[EdgeSearchMethod.cosine_similarity, EdgeSearchMethod.bm25],
        reranker=EdgeReranker.cross_encoder,
    ),
    node_config=NodeSearchConfig(
        search_methods=[NodeSearchMethod.cosine_similarity, NodeSearchMethod.bm25],
        reranker=NodeReranker.rrf,
    ),
    limit=10,
)


# Result container ────────────────────────────────────────────────────────────

@dataclass
class RetrievalResult:
    """Structured output from a retrieval call."""

    query: str
    user_id: str
    edges: list[EntityEdge] = field(default_factory=list)
    nodes: list[EntityNode] = field(default_factory=list)


# Public search functions ─────────────────────────────────────────────────────

async def search_facts(
    graphiti: Graphiti,
    query: str,
    user_id: str,
    num_results: int = 10,
    search_filter: SearchFilters | None = None,
) -> list[EntityEdge]:
    """
    Retrieve relationship facts from the user's knowledge graph.

    Returns EntityEdge objects. Each edge has:
      .fact        — the factual statement (e.g. "Patient is prescribed Tamoxifen 20mg daily")
      .name        — relationship type  (e.g. "PRESCRIBED")
      .valid_at    — when this fact became valid (document date)
      .invalid_at  — when superseded by newer data (None = still current)

    This is the fastest retrieval mode — no cross-encoder calls.
    Uses the simple graphiti.search() which defaults to EDGE_HYBRID_SEARCH_RRF.
    """
    _log.info("search_facts query=%r user_id=%s num_results=%d", query, user_id, num_results)

    edges = await graphiti.search(
        query=query,
        group_ids=[user_id],
        num_results=num_results,
        search_filter=search_filter,
    )

    _log.info("search_facts returned %d edges", len(edges))
    return edges


async def search_entities(
    graphiti: Graphiti,
    query: str,
    user_id: str,
    num_results: int = 10,
    search_filter: SearchFilters | None = None,
) -> list[EntityNode]:
    """
    Retrieve entity nodes from the user's knowledge graph.

    Returns EntityNode objects. Each node has:
      .name    — entity name   (e.g. "Tamoxifen", "Prostate Cancer")
      .labels  — entity type   (e.g. ["Medication"], ["Diagnosis"])
      .summary — short summary describing the entity across all episodes

    Use this to discover what entities are stored for a user without
    needing to traverse their relationships.
    """
    _log.info("search_entities query=%r user_id=%s", query, user_id)

    results: SearchResults = await graphiti.search_(
        query=query,
        config=_NODE_HYBRID_RRF,
        group_ids=[user_id],
        search_filter=search_filter,
    )

    _log.info("search_entities returned %d nodes", len(results.nodes))
    return results.nodes


async def search_combined(
    graphiti: Graphiti,
    query: str,
    user_id: str,
    num_results: int = 10,
    search_filter: SearchFilters | None = None,
) -> RetrievalResult:
    """
    Full retrieval: edges (facts) + nodes (entities) in one call.

    Edges use cross-encoder reranking for high relevance.
    Nodes use RRF (no extra LLM call).

    This is the recommended mode for building an LLM context window.
    The pipeline.py module calls this and formats the output.
    """
    config = SearchConfig(
        edge_config=EdgeSearchConfig(
            search_methods=[EdgeSearchMethod.cosine_similarity, EdgeSearchMethod.bm25],
            reranker=EdgeReranker.cross_encoder,
        ),
        node_config=NodeSearchConfig(
            search_methods=[NodeSearchMethod.cosine_similarity, NodeSearchMethod.bm25],
            reranker=NodeReranker.rrf,
        ),
        limit=num_results,
    )

    _log.info("search_combined query=%r user_id=%s num_results=%d", query, user_id, num_results)

    results: SearchResults = await graphiti.search_(
        query=query,
        config=config,
        group_ids=[user_id],
        search_filter=search_filter,
    )

    _log.info(
        "search_combined returned %d edges, %d nodes",
        len(results.edges),
        len(results.nodes),
    )

    return RetrievalResult(
        query=query,
        user_id=user_id,
        edges=results.edges,
        nodes=results.nodes,
    )


def build_medical_filter(
    entity_types: list[str] | None = None,
    edge_types: list[str] | None = None,
    current_only: bool = False,
) -> SearchFilters | None:
    """
    Build a SearchFilters for medical graph queries.

    Args:
        entity_types: List of medical entity labels to restrict node search.
                      Examples: ["Medication", "Diagnosis", "LabTest", "Patient"]
        edge_types:   List of relationship types to restrict edge search.
                      Examples: ["PRESCRIBED", "HAS_DIAGNOSIS", "HAD_LAB_TEST"]
        current_only: If True, only return edges that have not been superseded
                      (invalid_at IS NULL — current/active facts only).

    Returns None if no filters are requested (avoids passing an empty filter).
    """
    if not entity_types and not edge_types and not current_only:
        return None

    filters: dict = {}

    if entity_types:
        filters["node_labels"] = entity_types

    if edge_types:
        filters["edge_types"] = edge_types

    # current_only handled post-retrieval in pipeline.py (Graphiti's DateFilter
    # operates on stored timestamps; simpler to filter in Python after retrieval).

    return SearchFilters(**filters) if filters else None
