"""
AIlixir – Chat Agent API (stateless)
=====================================

The frontend manages all session and history state.
We receive the question + chat history, run the pipeline, return the answer.

Endpoints
---------
GET  /health
POST /chat

Pipeline (lives in graph/nodes.py)
-----------------------------------
  1. guardrail  — blocks injection attempts and off-topic questions
  2. intent     — classifies as NEW_QUESTION or FOLLOWUP
  3. rewrite    — if FOLLOWUP, rewrites into a self-contained query
  4. retrieve   — keyword search over documents.json
  5. answer     — Gemini 2.5 Flash generates the response

Request format
--------------
{
  "question": "What is the dosage?",
  "chat_history": [
    {"role": "user", "content": "What are the side effects of Metformin?"},
    {"role": "assistant", "content": "Common side effects include nausea..."}
  ]
}

chat_history is oldest-first. Omit it (or pass []) for the first message.
The backend uses it only as context — it is never stored.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Load .env before imports that may use environment variables
load_dotenv(Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from graph.nodes import (
    classify_intent,
    generate_answer,
    history_to_text,
    retrieve_context,
    rewrite_question,
    run_guardrail,
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("✅ AIlixir stateless chat API ready")
    yield


app = FastAPI(
    title="AIlixir Chat Agent API",
    description=(
        "Ask questions about pharmaceutical documents. "
        "Pass your full chat history with each request — no server-side sessions."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"] = Field(
        ...,
        description="Who sent this message."
    )
    content: str = Field(
        ...,
        description="Message text."
    )


class ChatRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The user's current question.",
        examples=["What are the side effects of Metformin?"],
    )

    chat_history: list[ChatMessage] = Field(
        default=[],
        description=(
            "Previous messages, oldest first. "
            "Pass [] or omit for the first message."
        ),
        examples=[[
            {
                "role": "user",
                "content": "What are the side effects of Metformin?"
            },
            {
                "role": "assistant",
                "content": "Common side effects include nausea, diarrhoea..."
            }
        ]],
    )


class ChatResponse(BaseModel):
    answer: str = Field(..., description="The agent's answer.")
    intent: str = Field(..., description="NEW_QUESTION, FOLLOWUP, or BLOCKED.")
    rewritten_question: str = Field(
        ...,
        description="The query actually sent to retrieval."
    )
    source: str = Field(..., description="Retrieval source.")


# ---------------------------------------------------------------------------
# Pipeline helper
# ---------------------------------------------------------------------------


def _run_pipeline_to_retrieval(question: str, history: list[dict]) -> dict:
    """
    Runs steps 1–4 and returns everything needed for answer generation.

    Steps
    -----
    1. guardrail
    2. intent classification
    3. rewrite (FOLLOWUP only)
    4. retrieval
    """

    # Step 1 — Guardrail
    refusal = run_guardrail(question)

    if refusal:
        return {
            "blocked": True,
            "refusal": refusal,
            "intent": "BLOCKED",
            "rewritten_question": question,
            "context": "",
            "source": "",
            "history_text": "",
        }

    # Step 2 — Intent Classification
    intent = classify_intent(question, history)

    # Step 3 — Rewrite
    rewritten_question = (
        rewrite_question(question, history)
        if intent == "FOLLOWUP"
        else question
    )

    # Step 4 — Retrieval
    context, source = retrieve_context(rewritten_question)

    return {
        "blocked": False,
        "refusal": None,
        "intent": intent,
        "rewritten_question": rewritten_question,
        "context": context,
        "source": source,
        "history_text": history_to_text(history),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", tags=["Ops"])
def health():
    """
    Liveness check.
    """
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
def chat(body: ChatRequest):
    """
    Synchronous endpoint.

    Runs all five pipeline steps and returns the full answer.
    """

    history = [msg.model_dump() for msg in body.chat_history]

    pipeline = _run_pipeline_to_retrieval(
        question=body.question,
        history=history,
    )

    if pipeline["blocked"]:
        return ChatResponse(
            answer=pipeline["refusal"],
            intent="BLOCKED",
            rewritten_question=body.question,
            source="",
        )

    try:
        answer = generate_answer(
            context=pipeline["context"],
            history_text=pipeline["history_text"],
            question=pipeline["rewritten_question"],
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    return ChatResponse(
        answer=answer,
        intent=pipeline["intent"],
        rewritten_question=pipeline["rewritten_question"],
        source=pipeline["source"],
    )