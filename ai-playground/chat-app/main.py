"""
AIlixir – Chat Agent API
FastAPI wrapper around the LangGraph RAG agent.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import vertexai
from vertexai.preview.generative_models import GenerativeModel, GenerationConfig

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from graph.builder import build_graph
from graph.nodes import (
    retrieve_context,
    get_history_text,
    REFUSAL_MESSAGE,
    BLOCKED_PATTERNS,
)

import os

# ---------------------------------------------------------------------------
# Vertex AI (reuse same model as nodes.py)
# ---------------------------------------------------------------------------

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
GEMINI_MODEL = "gemini-2.5-flash"
TEMPERATURE = 0.4

vertexai.init(project=PROJECT_ID, location=LOCATION)
stream_model = GenerativeModel(model_name=GEMINI_MODEL)

# ---------------------------------------------------------------------------
# App lifespan – build the graph once on startup
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
    version="0.1.0",
    lifespan=lifespan,
)

# CORS – required for React Native / web frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to specific domains in production
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
    answer: str = Field(..., description="The agent's answer.")
    session_id: str = Field(..., description="Echo of the session_id used.")
    intent: str = Field(
        ..., description="Detected intent: NEW_QUESTION, FOLLOWUP, or BLOCKED."
    )
    rewritten_question: str = Field(
        ...,
        description="Rewritten question used for retrieval.",
    )


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
    Standard request/response — full answer returned at once.
    Use for testing, scripts, or non-streaming clients.
    """
    if _graph is None:
        raise HTTPException(status_code=503, detail="Agent not initialised yet.")

    initial_state = {
        "question": body.question,
        "intent": "",
        "rewritten_question": "",
        "context": "",
        "answer": "",
        "messages": [],
    }

    config = {"configurable": {"thread_id": body.session_id}}

    try:
        result = _graph.invoke(initial_state, config=config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ChatResponse(
        answer=result["answer"],
        session_id=body.session_id,
        intent=result.get("intent", ""),
        rewritten_question=result.get("rewritten_question") or body.question,
    )


@app.post("/chat/stream", tags=["Chat"])
async def chat_stream(body: ChatRequest):
    """
    Streaming endpoint — tokens arrive word by word from Gemini in real time.

    How it works:
      1. Guardrail check (blocks injection / off-topic) — instant refusal if blocked
      2. Runs the full graph (intent → rewrite → retrieve) to get context
      3. Calls Gemini with stream=True so tokens are sent to the client as generated

    Response format: Server-Sent Events (SSE)
      Each chunk: "data: <text>\\n\\n"
      End signal:  "data: [DONE]\\n\\n"

    React Native usage:
      const res = await fetch('/chat/stream', { method: 'POST', body: ... })
      const reader = res.body.getReader()
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        const chunk = new TextDecoder().decode(value)
        if (chunk.includes('[DONE]')) break
        appendToUI(chunk.replace('data: ', ''))
      }
    """
    if _graph is None:
        raise HTTPException(status_code=503, detail="Agent not initialised yet.")

    async def token_generator() -> AsyncGenerator[str, None]:
        question = body.question
        q_lower = question.lower()

        # ------------------------------------------------------------------
        # Step 1: Guardrail — run before touching the graph
        # ------------------------------------------------------------------
        pharma_keywords = [
            "drug",
            "medicine",
            "patient",
            "dose",
            "side effect",
            "interaction",
            "contraindication",
            "trial",
            "clinical",
            "treatment",
            "diabetes",
            "warfarin",
            "metformin",
            "aspirin",
            "bleeding",
            "adverse",
            "hba1c",
            "summarize",
            "summary",
            "explain",
            "what",
            "how",
            "why",
            "when",
            "document",
            "report",
            "tell",
            "describe",
        ]

        if any(p in q_lower for p in BLOCKED_PATTERNS) or not any(
            kw in q_lower for kw in pharma_keywords
        ):
            yield f"data: {REFUSAL_MESSAGE}\n\n"
            yield "data: [DONE]\n\n"
            return

        # ------------------------------------------------------------------
        # Step 2: Run graph (guardrail → intent → rewrite → retrieve)
        #         but grab context + history before streaming the answer
        # ------------------------------------------------------------------
        initial_state = {
            "question": question,
            "intent": "",
            "rewritten_question": "",
            "context": "",
            "answer": "",
            "messages": [],
        }
        config = {"configurable": {"thread_id": body.session_id}}

        try:
            result = _graph.invoke(initial_state, config=config)
        except Exception as exc:
            yield f"data: [ERROR] {str(exc)}\n\n"
            return

        # If guardrail blocked inside the graph
        if result.get("intent") == "BLOCKED":
            yield f"data: {result['answer']}\n\n"
            yield "data: [DONE]\n\n"
            return

        query = result.get("rewritten_question") or question
        context = result.get("context", "")
        history_text = get_history_text(result.get("messages", []))

        # ------------------------------------------------------------------
        # Step 3: Stream the answer directly from Gemini
        # ------------------------------------------------------------------
        prompt = f"""
You are AIlixir, an AI assistant specialising in pharmaceutical documents.

Use ONLY the provided context to answer. Do not use outside knowledge.
If the answer is not present in the context, say "I don't know based on the documents."

Context:
{context}

Conversation:
{history_text}

Question:
{query}
"""

        try:
            # stream=True makes Gemini return chunks as they are generated
            responses = stream_model.generate_content(
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
                    yield f"data: {text}\n\n"

            yield "data: [DONE]\n\n"

        except Exception as exc:
            yield f"data: [ERROR] {str(exc)}\n\n"

    return StreamingResponse(
        token_generator(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",  # stops nginx from buffering
            "Cache-Control": "no-cache",
        },
    )
