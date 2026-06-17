"""
Graphiti retrieval — Step 2 of the chat pipeline.

Hybrid semantic + keyword search on the patient's knowledge graph,
scoped to `group_id=uid`. Returns:
  - relationship facts (EntityEdge) — these carry the temporal metadata
  - medical entities (EntityNode)   — for the LLM to anchor its answer

RRF reranking is used (NOT cross-encoder) to keep per-request latency
low — the answerer's LLM handles the final relevance selection across
the top-K facts anyway.

Defence-in-depth applied here:

  - `asyncio.wait_for` caps the Graphiti call at `_SEARCH_TIMEOUT_S`.
    Without this, a Neo4j outage takes ~31 seconds to surface (the driver
    retries internally). User-perceived latency must be predictable; we
    fail fast and let the caller surface a 503 + retry hint.

  - `_MAX_QUERY_CHARS` caps the query string the pipeline forwards to
    Graphiti. The API-layer Pydantic model already caps at 2000, but the
    pipeline must self-defend: a future caller (CLI, internal job,
    test harness) could bypass HTTP validation. Vertex embedding tokens
    are billable; truncate before we spend money on adversarial input.
"""

from __future__ import annotations

import asyncio
import logging
import os
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

from api.chat_pipeline.graphiti_client import get_graphiti

_log = logging.getLogger(__name__)


# ── Tunables (env-overridable) ────────────────────────────────────────────────

_DEFAULT_NUM_RESULTS = int(os.environ.get("CHAT_RETRIEVE_NUM_RESULTS", "4"))

# Wall-time ceiling for one Graphiti search. Default 15s is comfortably above
# typical local performance (~0.4s) and Aura performance (~1-2s under load),
# while short enough that a Neo4j outage surfaces to the caller as a clean 503
# instead of a 30+ second hang (the Neo4j driver's internal retry loop).
_SEARCH_TIMEOUT_S = float(os.environ.get("CHAT_RETRIEVE_TIMEOUT_S", "15.0"))

# Pipeline-layer defence in depth. The HTTP layer's Pydantic model caps at 2000
# chars but the pipeline must not trust its caller — a CLI tool, scheduled job,
# or future internal endpoint might bypass that validation. We truncate rather
# than reject so a slightly oversize legitimate query still gets a result.
_MAX_QUERY_CHARS = int(os.environ.get("CHAT_RETRIEVE_MAX_QUERY_CHARS", "2000"))


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


def _build_search_config(num_results: int) -> SearchConfig:
    """Compose the hybrid search config.

    Cosine + BM25 on both edges and nodes, RRF reranking (no cross-encoder
    LLM call to keep latency low). The answerer's LLM selects the final
    relevant subset across the returned top-K.
    """
    return SearchConfig(
        edge_config=EdgeSearchConfig(
            search_methods=[
                EdgeSearchMethod.cosine_similarity,
                EdgeSearchMethod.bm25,
            ],
            reranker=EdgeReranker.rrf,
        ),
        node_config=NodeSearchConfig(
            search_methods=[
                NodeSearchMethod.cosine_similarity,
                NodeSearchMethod.bm25,
            ],
            reranker=NodeReranker.rrf,
        ),
        limit=num_results,
    )


async def retrieve(
    query: str,
    user_id: str,
    num_results: int = _DEFAULT_NUM_RESULTS,
    graphiti: Graphiti | None = None,
) -> RetrievalResult:
    """
    Search the user's Graphiti knowledge graph for facts relevant to `query`.

    Args:
        query:        Natural-language query (typically contextualized).
        user_id:      Firebase UID — scopes results to this patient's graph
                      via Graphiti's group_ids parameter. Per-user isolation
                      is enforced at the graph query level; no other call
                      site can override this.
        num_results:  Max facts/entities returned. Default 4 (graph facts
                      are dense; 4 well-ranked facts beats 20 raw chunks).
        graphiti:     Optional pre-built Graphiti instance. Defaults to the
                      module-level singleton initialised by `get_graphiti()`.

    Returns:
        RetrievalResult with `edges` (facts) and `nodes` (entities).

    Raises:
        asyncio.TimeoutError: if Graphiti search exceeds `_SEARCH_TIMEOUT_S`.
                              Caller should surface this as a retryable 503;
                              the same exception type is in
                              `shared.retryable_errors.RETRYABLE_PIPELINE_ERRORS`.
        Various Neo4j / Vertex errors: see Graphiti's underlying calls.
                                       All transient kinds are classified as
                                       retryable by the chat endpoint.
    """
    # Pipeline-layer input cap. See module docstring.
    if len(query) > _MAX_QUERY_CHARS:
        _log.warning(
            "retrieve_query_truncated user_id=%s original_chars=%d cap=%d",
            user_id, len(query), _MAX_QUERY_CHARS,
        )
        query = query[:_MAX_QUERY_CHARS]

    _log.info(
        "retrieve query=%r user_id=%s num_results=%d",
        query, user_id, num_results,
    )

    config = _build_search_config(num_results)
    g = graphiti or await get_graphiti()

    # Hard timeout. Without this, Neo4j outages hang the user request for
    # 30+ seconds (driver's internal retries). 15s is well above typical
    # search latency and short enough to surface as a clean error.
    try:
        results = await asyncio.wait_for(
            g.search_(
                query=query,
                config=config,
                group_ids=[user_id],
            ),
            timeout=_SEARCH_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        # Re-raise as the same type but with chat-pipeline context. The
        # caller's try/except sees a TimeoutError, which is in
        # RETRYABLE_PIPELINE_ERRORS and gets converted to a 503.
        _log.warning(
            "retrieve_timeout user_id=%s after=%.1fs", user_id, _SEARCH_TIMEOUT_S,
        )
        raise

    _log.info(
        "retrieve_done user_id=%s edges=%d nodes=%d",
        user_id, len(results.edges), len(results.nodes),
    )

    return RetrievalResult(
        query=query,
        user_id=user_id,
        edges=results.edges,
        nodes=results.nodes,
    )
