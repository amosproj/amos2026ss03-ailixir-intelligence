"""
AIlixir – Chat Agent API
========================
FastAPI wrapper around the LangGraph RAG agent.

Endpoint summary
----------------
GET  /health          — liveness check
POST /chat            — synchronous, full answer at once
POST /chat/stream     — streaming via Server-Sent Events (SSE)

Streaming design
----------------
The /chat/stream endpoint works in two phases:

  Phase 1 — Graph (runs synchronously, fast):
    guardrail_node → intent_node → [rewrite_node] → retrieve_node → END
    Because state.streaming=True, the graph skips answer_node and returns
    immediately after retrieval.  This gives us:
      • guardrail result (BLOCKED or allowed)
      • rewritten question
      • retrieved context
      • conversation history

  Phase 2 — Gemini stream:
    Calls Gemini with stream=True using build_answer_prompt() from nodes.py
    (single source of truth for the prompt template).
    Tokens are yielded as SSE "data:" chunks the moment Gemini produces them.

    React Native sees:
      data: {"type":"meta","intent":"NEW_QUESTION","rewritten_question":"...","source":"documents.json"}\n\n
      data: {"type":"token","text":"Common "}\n\n
      data: {"type":"token","text":"side effects "}\n\n
      ...
      data: {"type":"done"}\n\n

    This gives the frontend both the token stream AND the metadata it needs
    (intent, source, rewritten_question) without a second HTTP call.

Why no guardrail duplication
-----------------------------
The guardrail_node in graph/nodes.py is the ONLY place that validates
questions.  main.py never re-implements that logic.  If the guardrail blocks
the question, state.intent == "BLOCKED" and this file simply forwards the
refusal message to the client.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from dotenv import load_dotenv

# Load .env from the ai-playground/ folder (one level above chat-app/).
# This must happen before ANY os.getenv() call in this file or any import
# that calls os.getenv() at module level (nodes.py, builder.py).
_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)

import vertexai
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from vertexai.preview.generative_models import GenerationConfig, GenerativeModel

from graph.builder import build_graph
from graph.nodes import (
    REFUSAL_MESSAGE,
    build_answer_prompt,
    get_history_text,
)

# ---------------------------------------------------------------------------
# Vertex AI — one model instance for streaming (non-streaming uses nodes.py)
# ---------------------------------------------------------------------------

# Support both VERTEX_PROJECT (your .env) and GOOGLE_CLOUD_PROJECT (GCP standard)
PROJECT_ID   = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("VERTEX_PROJECT")
LOCATION     = os.getenv("GOOGLE_CLOUD_LOCATION") or os.getenv("VERTEX_LOCATION", "us-central1")
GEMINI_MODEL = "gemini-2.5-flash"
TEMPERATURE  = 0.4

vertexai.init(project=PROJECT_ID, location=LOCATION)
_stream_model = GenerativeModel(model_name=GEMINI_MODEL)

# ---------------------------------------------------------------------------
# App lifespan — build the graph once on startup
# ---------------------------------------------------------------------------

_graph = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph
    _graph = build_graph()
    print("✅ LangGraph agent ready")
    yield


app = FastAPI(
    title="AIlixir Chat Agent API",
    description=(
        "Ask questions about uploaded pharmaceutical documents. "
        "Conversations are persisted per session via PostgreSQL."
    ),
    version="0.2.0",
    lifespan=lifespan,
)

# CORS — required for React Native / web frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     # tighten to specific domains in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The user's question or prompt.",
        examples=["What are the side effects of Metformin?"],
    )
    session_id: str = Field(
        default="default-session",
        description=(
            "Identifies the conversation thread. "
            "Use the same value across turns to maintain context."
        ),
        examples=["user-42", "demo-session-1"],
    )


class ChatResponse(BaseModel):
    answer: str              = Field(..., description="The agent's answer.")
    session_id: str          = Field(..., description="Echo of the session_id used.")
    intent: str              = Field(..., description="NEW_QUESTION, FOLLOWUP, or BLOCKED.")
    rewritten_question: str  = Field(..., description="Query used for retrieval.")
    source: str              = Field(..., description="Retrieval source (documents.json / knowledge_graph / hybrid).")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_prior_messages(session_id: str) -> list:
    """
    Explicitly fetch the persisted message history for this session from the
    Postgres checkpoint BEFORE invoking the graph.

    Why this is necessary
    ---------------------
    LangGraph's add_messages reducer merges the checkpoint's messages with
    whatever we pass as "messages" in the initial state. However, in some
    LangGraph versions the merge only happens at the reducer level AFTER the
    first node has already executed — meaning guardrail_node and intent_node
    would see an empty list. Fetching history explicitly and passing it in
    the initial state guarantees every node sees the full prior conversation
    from the very first node.
    """
    if _graph is None:
        return []
    try:
        config = _graph_config(session_id)
        snapshot = _graph.get_state(config)
        if snapshot and snapshot.values:
            return snapshot.values.get("messages", [])
    except Exception:
        pass
    return []


def _build_initial_state(question: str, streaming: bool, prior_messages: list) -> dict:
    """Returns a clean initial AgentState dict for one graph invocation."""
    return {
        "question":           question,
        "intent":             "",
        "rewritten_question": "",
        "context":            "",
        "source":             "",
        "answer":             "",
        "streaming":          streaming,
        "messages":           prior_messages,   # ← history loaded explicitly
    }


def _graph_config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def _require_graph():
    if _graph is None:
        raise HTTPException(status_code=503, detail="Agent not initialised yet.")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Ops"])
def health():
    """Liveness check."""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
def chat(body: ChatRequest):
    """
    Synchronous endpoint — full answer returned at once.
    Use for testing, scripts, or non-streaming clients.

    The graph runs all five nodes:
      guardrail → intent → [rewrite] → retrieve → answer
    """
    _require_graph()

    prior_messages = _get_prior_messages(body.session_id)
    try:
        result = _graph.invoke(
            _build_initial_state(body.question, streaming=False, prior_messages=prior_messages),
            config=_graph_config(body.session_id),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChatResponse(
        answer=result["answer"],
        session_id=body.session_id,
        intent=result.get("intent", ""),
        rewritten_question=result.get("rewritten_question") or body.question,
        source=result.get("source", "documents.json"),
    )


@app.post("/chat/stream", tags=["Chat"])
async def chat_stream(body: ChatRequest):
    """
    Streaming endpoint — tokens arrive word by word from Gemini in real time.

    SSE format
    ----------
    Each message is a JSON object on a "data:" line:

      data: {"type":"meta","intent":"NEW_QUESTION","rewritten_question":"...","source":"..."}\n\n
      data: {"type":"token","text":"Some text chunk"}\n\n
      data: {"type":"done"}\n\n

    On error or block:
      data: {"type":"error","text":"..."}\n\n
      data: {"type":"blocked","text":"..."}\n\n

    React Native example
    --------------------
      const res = await fetch('/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, session_id }),
      })
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const raw = decoder.decode(value)
        // each SSE chunk starts with "data: "
        for (const line of raw.split('\\n')) {
          if (!line.startsWith('data: ')) continue
          const msg = JSON.parse(line.slice(6))
          if (msg.type === 'meta')    setMeta(msg)
          if (msg.type === 'token')   appendText(msg.text)
          if (msg.type === 'done')    markComplete()
          if (msg.type === 'blocked') showRefusal(msg.text)
          if (msg.type === 'error')   showError(msg.text)
        }
      }
    """
    _require_graph()

    async def token_generator() -> AsyncGenerator[str, None]:

        def sse(payload: dict) -> str:
            """Encode a dict as a single SSE data line."""
            return f"data: {json.dumps(payload)}\n\n"

        # ── Phase 1: run the graph up to (and including) retrieve_node ────────
        # streaming=True tells the graph to skip answer_node and return early.
        # The guardrail, intent, rewrite, and retrieve nodes all run normally.
        prior_messages = _get_prior_messages(body.session_id)
        try:
            result = _graph.invoke(
                _build_initial_state(body.question, streaming=True, prior_messages=prior_messages),
                config=_graph_config(body.session_id),
            )
        except Exception as exc:
            yield sse({"type": "error", "text": str(exc)})
            return

        # ── Guardrail fired inside the graph ──────────────────────────────────
        if result.get("intent") == "BLOCKED":
            yield sse({"type": "blocked", "text": result.get("answer", REFUSAL_MESSAGE)})
            yield sse({"type": "done"})
            return

        # ── Emit metadata so the frontend has it immediately ──────────────────
        # The frontend receives this BEFORE the first token — it can use it to
        # show intent indicators, source badges, etc. without waiting for the
        # full answer.
        rewritten_q = result.get("rewritten_question") or body.question
        yield sse({
            "type":               "meta",
            "intent":             result.get("intent", "NEW_QUESTION"),
            "rewritten_question": rewritten_q,
            "source":             result.get("source", "documents.json"),
        })

        # ── Phase 2: stream the answer directly from Gemini ───────────────────
        # We use build_answer_prompt() from nodes.py — same template the
        # answer_node uses — so there is zero prompt duplication.
        prompt = build_answer_prompt(
            context=result.get("context", ""),
            history_text=get_history_text(result.get("messages", [])),
            question=rewritten_q,
        )

        try:
            responses = _stream_model.generate_content(
                prompt,
                generation_config=GenerationConfig(
                    temperature=TEMPERATURE,
                    max_output_tokens=1024,
                ),
                stream=True,
            )

            for chunk in responses:
                text = chunk.text
                if text:
                    yield sse({"type": "token", "text": text})

            yield sse({"type": "done"})

        except Exception as exc:
            yield sse({"type": "error", "text": str(exc)})

    return StreamingResponse(
        token_generator(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",    # stops nginx from buffering SSE
            "Cache-Control":     "no-cache",
            "Connection":        "keep-alive",
        },
    )