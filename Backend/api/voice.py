"""
ElevenLabs Custom LLM integration — POST /voice/v1/chat/completions

ElevenLabs Conversational AI agents can be pointed at an external,
OpenAI-compatible "Custom LLM" instead of a hosted model. This endpoint plays
that role for voice queries: it runs the same three-step graph-RAG pipeline
used by POST /chat/query (contextualize -> retrieve -> answer), scoped to the
calling patient's Neo4j knowledge graph, and replies in the OpenAI Chat
Completions wire format ElevenLabs expects.

Why a separate endpoint instead of reusing /chat/query
--------------------------------------------------------
ElevenLabs does not send our `ChatQueryRequest` shape — it sends an
OpenAI-style `{model, messages, stream, ...}` body, and it cannot hold a
Firebase ID token the way the mobile client does. Reusing /chat/query would
mean overloading one endpoint with two incompatible request/auth contracts.

How the patient is identified
------------------------------
The mobile client (already Firebase-authenticated) is responsible for
including the patient's Firebase UID as a dynamic variable when it asks
ElevenLabs to start a conversation. ElevenLabs' "dynamic variables" docs
recommend a `secret__` prefix for values that must never reach the LLM
transcript/prompt — and secret dynamic variables can ONLY be forwarded as
request headers on tool / custom-LLM calls. So the recommended dashboard
setup is:

    Custom LLM -> Request headers -> name: X-User-Id (configurable below)
                                      value: {{secret__user_id}}

We read that header first. ElevenLabs' exact body shape for dynamic
variables is not consistently documented across their docs pages (some show
`dynamic_variables`, others `elevenlabs_extra_body` or
`custom_llm_extra_body`) — so as a fallback, and per explicit product
instruction, we also scan the handful of plausible body locations. Whichever
path matches is logged (`uid_source=...`) so the real integration path can
be confirmed from logs and this can be trimmed later.

Authenticating the caller
--------------------------
The API's Cloud Run service allows unauthenticated invocations (the mobile
app authenticates itself per-request via Firebase token; the service
boundary is open). This endpoint has no per-request user credential to
verify, so without an additional check, anyone who can reach this public URL
and learn/guess a Firebase UID could read that patient's medical graph.
ElevenLabs' Custom LLM config has an "API key" field whose value is sent to
the custom LLM server as `Authorization: Bearer <value>` — we reuse that
field to hold a shared secret (`ELEVENLABS_CUSTOM_LLM_SECRET`) and reject
any request that doesn't present it.

Error handling philosophy
--------------------------
/chat/query returns granular HTTP error codes because the iOS client reads
them to decide retry/backoff behaviour. A voice agent has no such loop —
ElevenLabs just speaks whatever text we return. So pipeline failures
(retrieval/answer) are caught broadly and converted into one apologetic
spoken sentence delivered through a normal 200 response, rather than an HTTP
error the patient would experience as dead air mid-conversation. Hard
configuration failures (bad shared secret, no resolvable patient id) still
surface as HTTP errors — those mean the integration is misconfigured and
should be loud in logs/monitoring, not spoken to a patient.

Known limitation
-----------------
`generate_answer` returns a complete string, not a token stream, so the SSE
response below delivers the whole answer as a single delta chunk rather than
incrementally. This satisfies the OpenAI/ElevenLabs streaming contract (and
ElevenLabs still gets to start TTS as soon as the one chunk arrives) but
isn't true token-by-token streaming. Revisit if time-to-first-audio becomes
a problem.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
import uuid
from typing import Any, AsyncIterator

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from api.chat_pipeline.answerer import generate_answer
from api.chat_pipeline.contextualizer import contextualize_query
from api.chat_pipeline.retriever import retrieve
from api.errors import APIError
from shared.models.errors import ErrorCode

_log = logging.getLogger(__name__)

router = APIRouter()


# ── Config (env-overridable) ──────────────────────────────────────────────────

# Sent by ElevenLabs as `Authorization: Bearer <value>` when this URL is
# configured as the agent's Custom LLM with this value as its "API key".
# Required — see module docstring "Authenticating the caller".
_SHARED_SECRET = os.environ.get("ELEVENLABS_CUSTOM_LLM_SECRET", "")

# Name of the request header ElevenLabs is configured to send the patient's
# Firebase UID in (as a `secret__` dynamic variable — see module docstring).
_USER_ID_HEADER = os.environ.get("ELEVENLABS_USER_ID_HEADER", "X-User-Id")

_FALLBACK_ANSWER = (
    "I'm sorry, I'm having trouble reaching your health records right now. "
    "Please try again in a moment."
)


# ── Request models ────────────────────────────────────────────────────────────

class _VoiceMessage(BaseModel):
    role: str
    content: str | None = None

    model_config = ConfigDict(extra="allow")


class VoiceChatCompletionRequest(BaseModel):
    """Permissive OpenAI-Chat-Completions-shaped body.

    `extra="allow"` because ElevenLabs' exact field set for dynamic
    variables / extra body isn't consistently documented — rejecting unknown
    fields would risk hard-failing on a legitimate ElevenLabs payload.
    """

    model: str | None = None
    messages: list[_VoiceMessage] = Field(default_factory=list)
    stream: bool = True
    temperature: float | None = None
    max_tokens: int | None = None
    user_id: str | None = None
    user: str | None = None
    dynamic_variables: dict[str, Any] | None = None
    elevenlabs_extra_body: dict[str, Any] | None = None
    custom_llm_extra_body: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")


# ── Auth ──────────────────────────────────────────────────────────────────────

def _verify_shared_secret(authorization: str | None) -> None:
    if not _SHARED_SECRET:
        # Fail closed: an unset secret must never silently disable auth.
        _log.error("voice_auth_misconfigured: ELEVENLABS_CUSTOM_LLM_SECRET is not set")
        raise APIError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=ErrorCode.VOICE_NOT_CONFIGURED,
            message="Voice integration is not configured.",
        )
    presented = ""
    if authorization and authorization.lower().startswith("bearer "):
        presented = authorization[7:].strip()
    if not presented or not secrets.compare_digest(presented, _SHARED_SECRET):
        _log.warning("voice_auth_rejected")
        raise APIError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=ErrorCode.VOICE_UNAUTHORIZED,
            message="Invalid or missing credentials.",
        )


# ── Patient identification ────────────────────────────────────────────────────

def _first_nonempty_str(*values: Any) -> str | None:
    for v in values:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _extract_uid(
    payload: VoiceChatCompletionRequest, header_uid: str | None
) -> tuple[str | None, str]:
    """Resolve the patient's Firebase UID. Returns (uid, source) for logging.

    Checked in order: the configured header (preferred — see module
    docstring), then the handful of body locations different ElevenLabs docs
    pages describe for dynamic variables.
    """
    if header_uid and header_uid.strip():
        return header_uid.strip(), "header"

    dv = payload.dynamic_variables or {}
    eb = payload.elevenlabs_extra_body or {}
    cb = payload.custom_llm_extra_body or {}

    candidates: list[tuple[str, Any]] = [
        ("body.user_id", payload.user_id),
        ("body.user", payload.user),
        ("body.dynamic_variables.user_id", dv.get("user_id")),
        ("body.dynamic_variables.secret__user_id", dv.get("secret__user_id")),
        ("body.elevenlabs_extra_body.user_id", eb.get("user_id")),
        (
            "body.elevenlabs_extra_body.dynamic_variables.user_id",
            (eb.get("dynamic_variables") or {}).get("user_id"),
        ),
        ("body.custom_llm_extra_body.user_id", cb.get("user_id")),
        (
            "body.custom_llm_extra_body.dynamic_variables.user_id",
            (cb.get("dynamic_variables") or {}).get("user_id"),
        ),
    ]
    for source, value in candidates:
        found = _first_nonempty_str(value)
        if found:
            return found, source
    return None, "none"


def _messages_to_query_and_history(
    messages: list[_VoiceMessage],
) -> tuple[str, list[dict[str, str]]]:
    """Split OpenAI-style messages into (latest user query, prior turns).

    System messages are dropped — our pipeline's own system prompts
    (contextualizer/answerer) already encode the assistant's behaviour;
    forwarding ElevenLabs' agent system prompt as conversation history would
    just confuse the contextualizer's pronoun-resolution step.
    """
    turns = [
        {"role": m.role, "content": (m.content or "").strip()}
        for m in messages
        if m.role in ("user", "assistant") and (m.content or "").strip()
    ]
    if not turns or turns[-1]["role"] != "user":
        return "", turns
    return turns[-1]["content"], turns[:-1]


# ── OpenAI-compatible response framing ────────────────────────────────────────

def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def _stream_answer(completion_id: str, model: str, answer: str) -> AsyncIterator[str]:
    created = int(time.time())
    yield _sse_event(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": answer},
                    "finish_reason": None,
                }
            ],
        }
    )
    yield _sse_event(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
    )
    yield "data: [DONE]\n\n"


def _completion_json(completion_id: str, model: str, answer: str) -> dict:
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
    }


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def _run_pipeline(uid: str, query: str, history: list[dict[str, str]]) -> str:
    """Run contextualize -> retrieve -> answer, degrading to a spoken
    apology on any retrieval/answer failure. See module docstring "Error
    handling philosophy" for why this collapses /chat/query's granular
    error taxonomy into one fallback."""
    ctx = await contextualize_query(query=query, history=history)

    try:
        retrieval = await retrieve(query=ctx.query, user_id=uid)
        answer = await generate_answer(query=ctx.query, result=retrieval)
    except Exception as exc:
        _log.error(
            "voice_pipeline_failed uid=%s err_class=%s err=%s",
            uid, type(exc).__name__, exc, exc_info=True,
        )
        return _FALLBACK_ANSWER

    _log.info("voice_query_done uid=%s answer_len=%d", uid, len(answer))
    return answer


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post(
    "/v1/chat/completions",
    response_model=None,
    summary="ElevenLabs Custom LLM endpoint (OpenAI-compatible)",
    description=(
        "Server-to-server endpoint called by ElevenLabs Conversational AI "
        "when this URL is configured as an agent's Custom LLM. Not intended "
        "for direct use by the mobile/web client. See api/voice.py module "
        "docstring for the full integration contract."
    ),
)
async def voice_chat_completions(
    request: Request,
    payload: VoiceChatCompletionRequest,
    authorization: str | None = Header(default=None),
) -> StreamingResponse | JSONResponse:
    _verify_shared_secret(authorization)

    header_uid = request.headers.get(_USER_ID_HEADER)
    uid, uid_source = _extract_uid(payload, header_uid)
    if not uid:
        _log.warning("voice_query_missing_uid header=%s", _USER_ID_HEADER)
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.VOICE_USER_ID_MISSING,
            message=(
                f"No patient id found in header '{_USER_ID_HEADER}' or any "
                "known dynamic-variable body location."
            ),
        )

    query, history = _messages_to_query_and_history(payload.messages)
    if not query:
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.VALIDATION_FAILED,
            message="No user message found in `messages`.",
        )

    _log.info(
        "voice_query_start uid=%s uid_source=%s query_chars=%d history_turns=%d",
        uid, uid_source, len(query), len(history),
    )

    answer = await _run_pipeline(uid=uid, query=query, history=history)

    model = payload.model or "ailixir-voice"
    completion_id = _completion_id()

    if payload.stream:
        return StreamingResponse(
            _stream_answer(completion_id, model, answer),
            media_type="text/event-stream",
        )
    return JSONResponse(_completion_json(completion_id, model, answer))
