"""
Chat endpoints — POST /chat/query

Three-step hybrid graph+paper-RAG pipeline:
  1. Contextualize: LLM rewrites query if it references conversation history
  2. Retrieve:      TWO retrieval arms run concurrently —
                       (a) Graphiti searches the patient's knowledge graph
                           (group_id=uid) — the primary, patient-specific source.
                       (b) `paper_retriever` vector-searches the scraped
                           research-paper AstraDB collection and reranks via
                           Vertex AI's Ranking API — supplementary general
                           reference material. Never fails the request; a
                           degraded paper corpus falls back to graph-only.
  3. Answer:        LLM synthesises graph facts (+ paper excerpts, if any)
                     into a natural-language response.

The endpoint is async throughout. Graphiti (Neo4j + Vertex AI) is initialised
lazily on first request (or eagerly on lifespan startup if
`CHAT_GRAPHITI_WARMUP=true`) and reused across the service's lifetime.

Error classification
--------------------
Failures are classified into three buckets, each surfaced as a distinct
HTTP status + error code:

  503 / CHAT_RETRIEVAL_TIMEOUT, CHAT_NEO4J_UNAVAILABLE, CHAT_RATE_LIMITED,
        CHAT_RETRIEVAL_FAILED, CHAT_LLM_FAILED
        → transient remote dependency failure. iOS client should auto-retry
          with backoff (e.g. 1s, 5s, 15s).

  504 / CHAT_LLM_TIMEOUT, CHAT_RETRIEVAL_TIMEOUT
        → server-side hard timeout. Same retry strategy as 503 but the
          backoff start is longer (10s, 30s, 60s) because the operation
          known-took longer than the timeout.

  503 / CHAT_LLM_EMPTY
        → Gemini returned no content (SAFETY filter / MAX_TOKENS).
          NOT auto-retryable — the same prompt will produce the same
          empty answer. iOS client should ask the user to rephrase.

All paths log the (request_id, uid, error_class, finish_reason) tuple so
the on-call runbook can correlate user reports with backend logs.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from api.auth import get_current_user
from api.chat_pipeline.answerer import generate_answer
from api.chat_pipeline.contextualizer import contextualize_query
from api.chat_pipeline.paper_retriever import PaperRetrievalResult, retrieve_papers
from api.chat_pipeline.retriever import retrieve
from api.chat_pipeline.titler import generate_and_store_title
from api.errors import APIError
from shared.models.errors import ErrorCode
from shared.retryable_errors import (
    GoogleServiceUnavailable,
    GraphitiRateLimitError,
    Neo4jAuthError,
    Neo4jServiceUnavailable,
    Neo4jSessionExpired,
    ResourceExhausted,
)

_log = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────

class ChatMessage(BaseModel):
    """One turn in the conversation history."""

    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class ChatQueryRequest(BaseModel):
    """
    Body for POST /chat/query.

    `query`   — the user's latest message (required, 1-2000 chars).
    `history` — prior conversation turns in chronological order (optional).
                The contextualizer uses this to rewrite implicit follow-ups
                (e.g. "What are its side effects?" → "What are the side
                effects of Tamoxifen?") before sending to retrieval.
                Capped at 20 turns to prevent token blowup.
                Pipeline-layer code re-validates these caps independently
                in case a future caller bypasses HTTP-layer Pydantic.
    """

    query: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    # Opaque Realtime-DB chat id. Optional: when present AND this is the first
    # turn (empty history), the endpoint schedules background title generation
    # for users/{uid}/chats/{chat_id}. Absent for callers that don't persist a
    # chat session (e.g. one-off / voice flows).
    chat_id: str | None = Field(default=None, max_length=128)


class ChatQueryResponse(BaseModel):
    """
    Response for POST /chat/query.

    `answer`               — natural-language answer from Gemini.
    `contextualized_query` — the query actually used for retrieval (may differ
                             from the original if a rewrite was applied).
    `query_changed`        — True if the contextualizer rewrote the query.
    `facts_used`           — number of knowledge graph facts retrieved.
    `entities_used`        — number of knowledge graph entities retrieved.
    `papers_used`          — number of reranked research-paper chunks used
                             (0 if the paper corpus was unavailable/empty —
                             the answer still comes from the knowledge graph).
    """

    answer: str
    contextualized_query: str
    query_changed: bool
    facts_used: int
    entities_used: int
    papers_used: int = 0
    # True when a background title-generation task was scheduled for this chat
    # (first turn + chat_id present). The title itself lands in RTDB a moment
    # later; the client observes it via its chat-list subscription. Purely
    # informational — clients don't need to act on it.
    title_generation_scheduled: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

# Strong references to in-flight title tasks. asyncio only holds a weak
# reference to a bare create_task, so without this a task can be garbage
# collected mid-flight. We add on launch and discard on completion.
_title_tasks: set[asyncio.Task] = set()

# Same pattern for in-flight paper-retrieval tasks (see `retrieve_papers`
# call site below). Needed because when the KG retrieval arm fails, we don't
# await the paper task before raising — it keeps running in the background
# via this strong reference instead of being garbage-collected mid-flight.
_paper_tasks: set[asyncio.Task] = set()


def _maybe_start_title(payload: ChatQueryRequest, uid: str) -> bool:
    """Kick off best-effort title generation for the first turn of a chat.

    Returns True if a task was launched. Empty history is the cheap "this is
    message #1" signal; the titler's RTDB transaction is the correctness
    backstop (idempotent + rename-safe), so a missed or extra trigger can never
    double-title. The original `payload.query` is used (not the contextualized
    form) so the title reflects what the user actually typed.

    Launched with `create_task` (not a post-response BackgroundTask) so the
    title's Gemini call runs CONCURRENTLY with retrieve+answer. It's a short,
    thinking-disabled call, so it typically finishes before the answer does —
    the title is already in RTDB when the client renders the answer, instead of
    popping in several seconds later. `generate_and_store_title` never raises,
    so the orphaned task can't surface an unhandled exception.
    """
    if not payload.chat_id or payload.history:
        return False
    task = asyncio.create_task(
        generate_and_store_title(uid=uid, chat_id=payload.chat_id, query=payload.query)
    )
    _title_tasks.add(task)
    task.add_done_callback(_title_tasks.discard)
    return True


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post(
    "/query",
    response_model=ChatQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Query the patient's knowledge graph and get an AI answer",
    description="""
Run a three-step graph-RAG pipeline against the authenticated patient's
medical knowledge graph stored in Neo4j (via Graphiti).

**Step 1 — Contextualize**
If the query implicitly references prior conversation (pronouns, follow-up
phrasing), it is rewritten into a self-contained question.
*Example:* "Tell me its drawbacks" after discussing Tamoxifen
→ "What are the drawbacks of Tamoxifen?"

**Step 2 — Retrieve**
Hybrid semantic + keyword search on the patient's knowledge graph
(`group_id = uid`). Returns up to 4 relevant medical facts (relationship
edges with temporal metadata) and entity nodes.

**Step 3 — Answer**
Gemini synthesises the retrieved facts into a precise, temporally-aware
natural-language answer. Facts are clearly marked as current or historical.
    """,
)
async def chat_query(
    payload: ChatQueryRequest,
    user: dict = Depends(get_current_user),
) -> ChatQueryResponse:
    uid = user["uid"]

    _log.info(
        "chat_query_start uid=%s query_chars=%d history_turns=%d",
        uid, len(payload.query), len(payload.history),
    )

    # Kick off title generation up front so it runs concurrently with the
    # retrieve+answer pipeline below. It depends only on the raw query, so
    # starting here (rather than after the answer) means the title is usually
    # written to RTDB before the answer is even ready — the client sees them
    # appear together instead of the title lagging by seconds.
    title_generation_scheduled = _maybe_start_title(payload, uid)

    # Step 1 — Contextualize
    # `contextualize_query` is designed to never raise — it returns the
    # original query on any internal failure (graceful degradation).
    history_dicts = [{"role": m.role, "content": m.content} for m in payload.history]
    ctx = await contextualize_query(
        query=payload.query,
        history=history_dicts,
    )
    contextualized = ctx.query

    # Step 2 — Retrieve
    try:
        retrieval = await retrieve(
            query=contextualized,
            user_id=uid,
        )
    except asyncio.TimeoutError:
        _log.warning("chat_query retrieval_timeout uid=%s", uid)
        raise APIError(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            code=ErrorCode.CHAT_RETRIEVAL_TIMEOUT,
            message=(
                "Knowledge graph retrieval timed out. "
                "Please try again in a moment."
            ),
        )
    except (Neo4jServiceUnavailable, Neo4jSessionExpired, Neo4jAuthError) as exc:
        _log.warning(
            "chat_query neo4j_unavailable uid=%s err_class=%s err=%s",
            uid, type(exc).__name__, exc,
        )
        raise APIError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.CHAT_NEO4J_UNAVAILABLE,
            message=(
                "The medical knowledge graph is temporarily unavailable. "
                "Please try again."
            ),
        )
    except (ResourceExhausted, GraphitiRateLimitError) as exc:
        _log.warning(
            "chat_query retrieval_rate_limited uid=%s err=%s", uid, exc,
        )
        raise APIError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.CHAT_RATE_LIMITED,
            message=(
                "The AI service is briefly rate-limited. "
                "Please try again in a few seconds."
            ),
        )
    except Exception as exc:
        _log.error(
            "chat_query retrieval_failed uid=%s err_class=%s err=%s",
            uid, type(exc).__name__, exc, exc_info=True,
        )
        raise APIError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.CHAT_RETRIEVAL_FAILED,
            message="Knowledge graph retrieval failed. Please try again.",
        )

    # Step 3 — Generate answer
    try:
        answer = await generate_answer(
            query=contextualized,
            result=retrieval,
        )
    except TimeoutError:
        _log.warning("chat_query answer_timeout uid=%s", uid)
        raise APIError(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            code=ErrorCode.CHAT_LLM_TIMEOUT,
            message="The AI response timed out. Please try again.",
        )
    except (ResourceExhausted, GoogleServiceUnavailable, GraphitiRateLimitError) as exc:
        _log.warning(
            "chat_query answer_rate_limited uid=%s err=%s", uid, exc,
        )
        raise APIError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.CHAT_RATE_LIMITED,
            message=(
                "The AI service is briefly rate-limited. "
                "Please try again in a few seconds."
            ),
        )
    except ValueError as exc:
        # `generate_answer` raises ValueError when Gemini returns an empty
        # response — typically because the SAFETY filter blocked the
        # answer or the prompt + answer exceeded the token budget.
        # NOT auto-retryable: the same prompt will produce the same empty
        # answer. iOS should surface a "please rephrase" hint.
        _log.warning(
            "chat_query answer_empty uid=%s err=%s", uid, exc,
        )
        raise APIError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.CHAT_LLM_EMPTY,
            message=(
                "The AI couldn't produce an answer for this question. "
                "Please rephrase or ask something more specific."
            ),
        )
    except Exception as exc:
        _log.error(
            "chat_query answer_failed uid=%s err_class=%s err=%s",
            uid, type(exc).__name__, exc, exc_info=True,
        )
        raise APIError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.CHAT_LLM_FAILED,
            message="Failed to generate an answer. Please try again.",
        )

    _log.info(
        "chat_query_done uid=%s query_changed=%s facts=%d entities=%d answer_len=%d title_scheduled=%s",
        uid, ctx.changed, retrieval.total_edges, retrieval.total_nodes,
        len(answer), title_generation_scheduled,
    )

    return ChatQueryResponse(
        answer=answer,
        contextualized_query=contextualized,
        query_changed=ctx.changed,
        facts_used=retrieval.total_edges,
        entities_used=retrieval.total_nodes,
        title_generation_scheduled=title_generation_scheduled,
    )
