"""
Chat endpoints — POST /chat/query

Three-step graph-RAG pipeline:
  1. Contextualize: LLM rewrites query if it references conversation history
  2. Retrieve:      Graphiti searches the patient's knowledge graph (group_id=uid)
  3. Answer:        LLM synthesises graph facts into a natural-language response

The endpoint is async throughout. Graphiti (Neo4j + Vertex AI) is initialised
lazily on first request and reused across the service's lifetime.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from api.auth import get_current_user
from api.chat_pipeline.answerer import generate_answer
from api.chat_pipeline.contextualizer import contextualize_query
from api.chat_pipeline.retriever import retrieve
from api.errors import APIError
from shared.models.errors import ErrorCode

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

    `query`   — the user's latest message (required).
    `history` — prior conversation turns in chronological order (optional).
                The contextualizer uses this to rewrite implicit follow-ups
                (e.g. "What are its side effects?" → "What are the side
                effects of Tamoxifen?") before sending to retrieval.
                Capped at 20 turns to prevent token blowup.
    """

    query: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)


class ChatQueryResponse(BaseModel):
    """
    Response for POST /chat/query.

    `answer`               — natural-language answer from Gemini.
    `contextualized_query` — the query actually used for retrieval (may differ
                             from the original if a rewrite was applied).
    `query_changed`        — True if the contextualizer rewrote the query.
    `facts_used`           — number of knowledge graph facts retrieved.
    `entities_used`        — number of knowledge graph entities retrieved.
    """

    answer: str
    contextualized_query: str
    query_changed: bool
    facts_used: int
    entities_used: int


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
        "chat_query_start uid=%s query=%r history_turns=%d",
        uid, payload.query, len(payload.history),
    )

    # Step 1 — Contextualize
    history_dicts = [{"role": m.role, "content": m.content} for m in payload.history]
    ctx = await contextualize_query(
        query=payload.query,
        history=history_dicts,
    )
    contextualized = ctx.query

    # Step 2 — Retrieve from knowledge graph
    try:
        retrieval = await retrieve(
            query=contextualized,
            user_id=uid,
        )
    except Exception as exc:
        _log.error("chat_query retrieval_failed uid=%s error=%s", uid, exc)
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
        _log.error("chat_query answer_timeout uid=%s", uid)
        raise APIError(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            code=ErrorCode.CHAT_LLM_TIMEOUT,
            message="The AI response timed out. Please try again.",
        )
    except Exception as exc:
        _log.error("chat_query answer_failed uid=%s error=%s", uid, exc)
        raise APIError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.CHAT_LLM_FAILED,
            message="Failed to generate an answer. Please try again.",
        )

    _log.info(
        "chat_query_done uid=%s query_changed=%s facts=%d entities=%d answer_len=%d",
        uid, ctx.changed, retrieval.total_edges, retrieval.total_nodes, len(answer),
    )

    return ChatQueryResponse(
        answer=answer,
        contextualized_query=contextualized,
        query_changed=ctx.changed,
        facts_used=retrieval.total_edges,
        entities_used=retrieval.total_nodes,
    )
