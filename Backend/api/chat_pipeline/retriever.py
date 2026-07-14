"""
Graphiti retrieval — Step 2 of the chat pipeline.

Hybrid semantic + keyword search on the patient's knowledge graph,
scoped to `group_id=uid`. Returns:
  - relationship facts (EntityEdge) — these carry the temporal metadata
  - medical entities (EntityNode)   — for the LLM to anchor its answer

RRF reranking is used (NOT cross-encoder) to keep per-request latency
low — the answerer's LLM handles the final relevance selection across
the top-K facts anyway.

Graceful degradation
--------------------
`retrieve` MUST NOT raise. Neo4j being unconfigured (no NEO4J_* env vars —
a fresh checkout, a staging deploy without a graph), unreachable, or slow all
resolve to a RetrievalResult with `degraded=True`, an empty fact list, and a
`degraded_reason` explaining what went wrong. The answerer renders that reason
into its prompt and the LLM tells the user their records could not be read —
which is a different statement from "you have no records", and the distinction
matters to a patient asking about their own lab results.

Consequently a graph outage no longer fails the request. The research-paper
arm (paper_retriever.py) still runs, and the user still gets an answer plus an
honest account of what was missing from it. See `availability.py`.

Defence-in-depth applied here:

  - `asyncio.wait_for` caps the Graphiti call at `_SEARCH_TIMEOUT_S`.
    Without this, a Neo4j outage takes ~31 seconds to surface (the driver
    retries internally). User-perceived latency must be predictable, so we
    fail fast, degrade, and let the answer explain itself.

  - A `CircuitBreaker` latches the arm out for a cooldown after a failure, so
    request #2 during an outage skips the graph instantly instead of paying
    the 15s timeout again.

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

from api.chat_pipeline.availability import (
    CircuitBreaker,
    classify,
    failure_reason,
    missing_env_vars,
    should_trip,
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

# Env vars without which there is no graph to talk to at all. `VERTEX_PROJECT`
# is included because Graphiti embeds the query through Vertex before it ever
# reaches Neo4j — no project, no search, however healthy Neo4j is.
_REQUIRED_ENV = ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD", "VERTEX_PROJECT")

# Process-wide latch. See availability.py — after a failure the graph arm is
# skipped for the cooldown window rather than re-timing-out on every request.
_breaker = CircuitBreaker("knowledge_graph")


@dataclass
class RetrievalResult:
    """Structured output from a knowledge graph retrieval call.

    `degraded` is the load-bearing field for callers: it distinguishes "the
    graph was searched and this patient genuinely has no matching facts"
    (degraded=False, edges=[]) from "the graph could not be searched"
    (degraded=True, edges=[]). Both yield an empty fact list, and conflating
    them would have the assistant confidently tell a patient they have no
    records during an outage.
    """

    query: str
    user_id: str
    edges: list[EntityEdge] = field(default_factory=list)
    nodes: list[EntityNode] = field(default_factory=list)
    degraded: bool = False
    degraded_reason: str | None = None

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


def _degraded(query: str, user_id: str, reason: str) -> RetrievalResult:
    """An empty result carrying the reason the graph could not be read."""
    return RetrievalResult(
        query=query, user_id=user_id, degraded=True, degraded_reason=reason,
    )


async def retrieve(
    query: str,
    user_id: str,
    num_results: int = _DEFAULT_NUM_RESULTS,
    graphiti: Graphiti | None = None,
) -> RetrievalResult:
    """
    Search the user's Graphiti knowledge graph for facts relevant to `query`.

    Never raises. If the graph is unconfigured, unreachable, or slow, the
    returned RetrievalResult has `degraded=True`, no edges/nodes, and a
    `degraded_reason` — the caller answers from whatever else it has and the
    answerer tells the user the records could not be read. See the module
    docstring and `availability.py`.

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
                      When passed, the env-var precheck is skipped — the
                      caller has already built a working client, so the vars
                      it would check are irrelevant (this is also what lets
                      tests inject a fake).

    Returns:
        RetrievalResult — with `edges` (facts) and `nodes` (entities) on
        success, or empty and `degraded=True` on any failure.
    """
    # Pipeline-layer input cap. See module docstring.
    if len(query) > _MAX_QUERY_CHARS:
        _log.warning(
            "retrieve_query_truncated user_id=%s original_chars=%d cap=%d",
            user_id, len(query), _MAX_QUERY_CHARS,
        )
        query = query[:_MAX_QUERY_CHARS]

    # Cheapest checks first: an unconfigured or known-down graph costs nothing.
    if graphiti is None:
        missing = missing_env_vars(_REQUIRED_ENV)
        if missing:
            _log.warning("retrieve_unconfigured missing_env=%s", ",".join(missing))
            return _degraded(
                query, user_id,
                "the medical knowledge graph is not configured on this server",
            )

        if _breaker.is_open():
            _log.info("retrieve_skipped_circuit_open user_id=%s", user_id)
            return _degraded(query, user_id, _breaker.reason)

    _log.info(
        "retrieve query=%r user_id=%s num_results=%d",
        query, user_id, num_results,
    )

    config = _build_search_config(num_results)

    # Client construction is inside the try: a bad NEO4J_URI or missing ADC
    # blows up here, not in search_, and it degrades exactly the same way.
    try:
        g = graphiti or await get_graphiti()

        # Hard timeout. Without this, Neo4j outages hang the user request for
        # 30+ seconds (the driver's internal retries). 15s is well above
        # typical search latency and short enough to degrade promptly.
        results = await asyncio.wait_for(
            g.search_(
                query=query,
                config=config,
                group_ids=[user_id],
            ),
            timeout=_SEARCH_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        _log.warning(
            "retrieve_timeout user_id=%s after=%.1fs", user_id, _SEARCH_TIMEOUT_S,
        )
        reason = "the medical knowledge graph did not respond in time"
        _breaker.trip(reason)
        return _degraded(query, user_id, reason)
    except Exception as exc:
        # Everything else — Neo4j down, credentials rotated, Vertex 429 on the
        # query embedding, a driver bug. The user gets an answer either way;
        # exc_info keeps the real cause in the logs for on-call.
        _log.error(
            "retrieve_failed user_id=%s err_class=%s kind=%s err=%s",
            user_id, type(exc).__name__, classify(exc), exc, exc_info=True,
        )
        reason = f"the medical knowledge graph is unavailable: {failure_reason(exc)}"
        # Only latch the arm out when the STORE is down. A rate limit or a
        # one-off bug degrades THIS request only — tripping on those would
        # take the graph away from every other user for the cooldown window
        # over a failure the next request would likely have survived.
        if should_trip(exc):
            _breaker.trip(reason)
        return _degraded(query, user_id, reason)

    _breaker.reset()

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
