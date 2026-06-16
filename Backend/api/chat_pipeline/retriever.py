"""
Graphiti retrieval — Step 2 of the chat pipeline.

Runs a hybrid semantic+keyword search on the patient's knowledge graph,
scoped to group_id=uid. Returns relationship facts (EntityEdge) and
medical entities (EntityNode) relevant to the query.

Uses RRF reranking (no cross-encoder LLM call) to keep API latency low.
The answering step's LLM handles selecting the most relevant facts from
the returned set.

Max 4 results by default — graph facts are much denser than text chunks,
so 4 well-ranked facts are sufficient for most medical queries.
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
)
from graphiti_core.search.search_filters import SearchFilters

from api.chat_pipeline.graphiti_client import get_graphiti

_log = logging.getLogger(__name__)

_DEFAULT_NUM_RESULTS = 4

# Hybrid search config used for all chat queries:
# - Cosine similarity + BM25 on both edges and nodes
# - RRF reranking (no cross-encoder to keep latency low; the answerer
#   LLM does the final relevance selection)
_CHAT_SEARCH_CONFIG = SearchConfig(
    edge_config=EdgeSearchConfig(
        search_methods=[EdgeSearchMethod.cosine_similarity, EdgeSearchMethod.bm25],
        reranker=EdgeReranker.rrf,
    ),
    node_config=NodeSearchConfig(
        search_methods=[NodeSearchMethod.cosine_similarity, NodeSearchMethod.bm25],
        reranker=NodeReranker.rrf,
    ),
    limit=_DEFAULT_NUM_RESULTS,
)


@dataclass
class RetrievalResult:
    """Structured output from a knowledge graph retrieval call."""

    query: str
    user_id: str
    edges: list[EntityEdge] = field(default_factory=list)
    nodes: list[EntityNode] = field(default_factory=list)

    @property
    def total_edges(self) -> int:
        return len(self.edges)

    @property
    def total_nodes(self) -> int:
        return len(self.nodes)


async def retrieve(
    query: str,
    user_id: str,
    num_results: int = _DEFAULT_NUM_RESULTS,
    graphiti: Graphiti | None = None,
) -> RetrievalResult:
    """
    Search the user's Graphiti knowledge graph for facts relevant to `query`.

    Args:
        query:       The (possibly contextualized) natural-language query.
        user_id:     Firebase UID — scopes results to this patient's graph only
                     via group_ids=[user_id].
        num_results: Max facts/entities returned (default 4).
        graphiti:    Optional pre-built Graphiti instance. If None, the
                     module-level singleton is used (typical for API routes).

    Returns:
        RetrievalResult with edges (facts) and nodes (entities).
    """
    _log.info("retrieve query=%r user_id=%s num_results=%d", query, user_id, num_results)

    config = SearchConfig(
        edge_config=EdgeSearchConfig(
            search_methods=[EdgeSearchMethod.cosine_similarity, EdgeSearchMethod.bm25],
            reranker=EdgeReranker.rrf,
        ),
        node_config=NodeSearchConfig(
            search_methods=[NodeSearchMethod.cosine_similarity, NodeSearchMethod.bm25],
            reranker=NodeReranker.rrf,
        ),
        limit=num_results,
    )

    g = graphiti or await get_graphiti()

    results = await g.search_(
        query=query,
        config=config,
        group_ids=[user_id],
    )

    _log.info(
        "retrieve done user_id=%s edges=%d nodes=%d",
        user_id, len(results.edges), len(results.nodes),
    )

    return RetrievalResult(
        query=query,
        user_id=user_id,
        edges=results.edges,
        nodes=results.nodes,
    )
