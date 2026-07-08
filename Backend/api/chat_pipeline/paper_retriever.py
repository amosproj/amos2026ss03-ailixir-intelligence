"""
Research-paper retrieval — the hybrid arm of the chat pipeline.

Runs CONCURRENTLY with Graphiti knowledge-graph retrieval (see
retriever.py), not instead of it — `chat.py` fires both with
`asyncio.create_task` and awaits them together. Two stages:

  1. Vector search — top `_VECTOR_TOP_K` chunks from the AstraDB collection
     the `scrapers/` subsystem ingests (PubMed papers, Archive preprints,
     YouTube transcripts, ...), pre-filtered on the `domain`/`sub_domain`
     metadata fields the scraper attaches to every chunk.
  2. Rerank — Vertex AI's Ranking API (a stateless cross-encoder) narrows
     those candidates down to the `_RERANK_TOP_N` most relevant, which is
     more precise than the vector search's cosine-distance ordering alone.

The reranked chunks are handed to `answerer.generate_answer` as
supplementary reference material alongside the patient's graph facts — see
that module's updated system prompt for how the two sources are weighted.

Domain/sub_domain scoping
--------------------------
Hardcoded via env-overridable constants (`_PAPER_DOMAIN`, `_PAPER_SUB_DOMAIN`)
rather than derived per-request: every current user is an oncology patient,
so there is nothing to key off yet. Swap in a per-user/per-query lookup here
once other domains onboard — no caller-side change needed.

Graceful degradation
---------------------
Mirrors contextualizer.py: `retrieve_papers` MUST NOT raise. AstraDB being
down, an OpenAI embedding error, a Ranking API quota trip, or a timeout all
resolve to an empty `PaperRetrievalResult` — the chat pipeline then answers
from the knowledge graph alone. A degraded or unavailable paper corpus must
never take down the primary (graph-RAG) answer path.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field

from google.cloud import discoveryengine_v1 as discoveryengine

from api.chat_pipeline.astra_client import get_astra_store
from api.chat_pipeline.reranker_client import get_reranker_client, ranking_config_path

_log = logging.getLogger(__name__)


# ── Tunables (env-overridable) ────────────────────────────────────────────────

# All current users are oncology patients — hardcoded per product decision
# (see conversation with the scraper's author). Replace with a per-user
# lookup once other domains onboard.
_PAPER_DOMAIN = os.environ.get("CHAT_PAPER_DOMAIN", "medical")
_PAPER_SUB_DOMAIN = os.environ.get("CHAT_PAPER_SUB_DOMAIN", "oncology")

_VECTOR_TOP_K = int(os.environ.get("CHAT_PAPER_VECTOR_TOP_K", "4"))
_RERANK_TOP_N = int(os.environ.get("CHAT_PAPER_RERANK_TOP_N", "2"))
_RERANK_MODEL = os.environ.get("CHAT_PAPER_RERANK_MODEL", "semantic-ranker-default@latest")

# Wall-time ceilings per stage. Kept well under the answerer's own timeout so
# a slow paper corpus can't dominate total request latency — the KG arm runs
# concurrently and usually finishes first anyway.
_VECTOR_TIMEOUT_S = float(os.environ.get("CHAT_PAPER_VECTOR_TIMEOUT_S", "8.0"))
_RERANK_TIMEOUT_S = float(os.environ.get("CHAT_PAPER_RERANK_TIMEOUT_S", "8.0"))

# Pipeline-layer defence in depth, same rationale as retriever.py.
_MAX_QUERY_CHARS = int(os.environ.get("CHAT_PAPER_MAX_QUERY_CHARS", "2000"))

# Per-chunk content cap sent to the Ranking API. Vector chunks are already
# ~512 chars (scraper's splitter), this just guards against a pathological
# outlier inflating the rank request.
_MAX_CHUNK_CHARS = 2000


@dataclass
class PaperChunk:
    """One reranked research-paper chunk, ready for the answerer prompt."""

    content: str
    source: str | None = None        # e.g. "pubmed", "archive", "youtube"
    source_type: str | None = None   # e.g. "paper", "video"
    source_id: str | None = None
    published_date: str | None = None
    score: float | None = None       # Ranking API relevance score


@dataclass
class PaperRetrievalResult:
    """Structured output from a hybrid paper retrieval call."""

    query: str
    chunks: list[PaperChunk] = field(default_factory=list)

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)


async def _vector_search(query: str) -> list:
    """Top-K AstraDB similarity search, pre-filtered on domain/sub_domain."""
    store = await get_astra_store()
    metadata_filter = {"domain": _PAPER_DOMAIN, "sub_domain": _PAPER_SUB_DOMAIN}
    return await asyncio.wait_for(
        store.asimilarity_search(query, k=_VECTOR_TOP_K, filter=metadata_filter),
        timeout=_VECTOR_TIMEOUT_S,
    )


def _rank_sync(query: str, documents: list) -> discoveryengine.RankResponse:
    """Blocking Ranking API call — always invoked via `asyncio.to_thread`.

    Uses the sync `RankServiceClient` (see reranker_client.py docstring for
    why: the gapic-generated async client has an open event-loop bug).
    """
    client = get_reranker_client()
    records = [
        discoveryengine.RankingRecord(
            id=str(i),
            content=doc.page_content[:_MAX_CHUNK_CHARS],
        )
        for i, doc in enumerate(documents)
    ]
    request = discoveryengine.RankRequest(
        ranking_config=ranking_config_path(),
        model=_RERANK_MODEL,
        query=query,
        records=records,
        top_n=_RERANK_TOP_N,
    )
    return client.rank(request=request)


async def _rerank(query: str, documents: list) -> list[PaperChunk]:
    """Cross-encoder rerank via Vertex AI Ranking API; returns top `_RERANK_TOP_N`."""
    response = await asyncio.wait_for(
        asyncio.to_thread(_rank_sync, query, documents), timeout=_RERANK_TIMEOUT_S
    )

    by_id = {str(i): doc for i, doc in enumerate(documents)}
    chunks: list[PaperChunk] = []
    for record in response.records:
        doc = by_id.get(record.id)
        if doc is None:
            continue
        meta = doc.metadata or {}
        chunks.append(
            PaperChunk(
                content=doc.page_content,
                source=meta.get("source"),
                source_type=meta.get("source_type"),
                source_id=meta.get("source_id"),
                published_date=meta.get("published_date"),
                score=record.score,
            )
        )
    return chunks


async def retrieve_papers(query: str) -> PaperRetrievalResult:
    """
    Hybrid arm of chat retrieval: top research-paper chunks for `query`,
    vector-searched then reranked. See module docstring for the two stages.

    Never raises — any failure degrades to an empty result so the caller
    can still answer from the knowledge graph alone. Callers run this
    concurrently with `retriever.retrieve()` via `asyncio.create_task`.
    """
    if len(query) > _MAX_QUERY_CHARS:
        _log.warning(
            "retrieve_papers_query_truncated original_chars=%d cap=%d",
            len(query), _MAX_QUERY_CHARS,
        )
        query = query[:_MAX_QUERY_CHARS]

    try:
        documents = await _vector_search(query)
    except asyncio.TimeoutError:
        _log.warning("paper_vector_search_timeout after=%.1fs", _VECTOR_TIMEOUT_S)
        return PaperRetrievalResult(query=query)
    except Exception as exc:
        _log.warning(
            "paper_vector_search_failed err_class=%s err=%s", type(exc).__name__, exc,
        )
        return PaperRetrievalResult(query=query)

    if not documents:
        _log.info(
            "retrieve_papers_no_vector_hits domain=%s sub_domain=%s",
            _PAPER_DOMAIN, _PAPER_SUB_DOMAIN,
        )
        return PaperRetrievalResult(query=query)

    try:
        chunks = await _rerank(query, documents)
    except asyncio.TimeoutError:
        _log.warning("paper_rerank_timeout after=%.1fs", _RERANK_TIMEOUT_S)
        return PaperRetrievalResult(query=query)
    except Exception as exc:
        _log.warning(
            "paper_rerank_failed err_class=%s err=%s", type(exc).__name__, exc,
        )
        return PaperRetrievalResult(query=query)

    _log.info(
        "retrieve_papers_done domain=%s sub_domain=%s vector_hits=%d reranked=%d",
        _PAPER_DOMAIN, _PAPER_SUB_DOMAIN, len(documents), len(chunks),
    )
    return PaperRetrievalResult(query=query, chunks=chunks)
