"""
graph/builder.py
----------------
Assembles the LangGraph StateGraph and wires up the PostgreSQL checkpointer.

Graph shape
-----------

    guardrail_node
         │
    ─────┼──── intent=="BLOCKED" ──▶ END
         │
    intent_node
         │
    ─────┼──── intent=="FOLLOWUP" ──▶ rewrite_node ──┐
         │                                            │
         └────────── NEW_QUESTION ────────────────────┤
                                                      │
                                                 retrieve_node
                                                      │
                                        ─────────────────────────
                                        streaming==True  │  False
                                              END        │  answer_node
                                                         │
                                                        END

The streaming branch skips answer_node so main.py can call Gemini with
stream=True and pipe tokens directly to the SSE client — no wasted non-
streaming LLM call inside the graph.

DB setup
--------
LangGraph's checkpointer.setup() creates the two required tables
(checkpoints, writes) on first run if they don't already exist.
init_db.py is therefore only needed for local dev environments that want
to pre-create the schema before first startup.
"""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

from graph.state import AgentState
from graph.nodes import (
    guardrail_node,
    intent_node,
    rewrite_node,
    retrieve_node,
    answer_node,
)

# ---------------------------------------------------------------------------
# Load .env — lives in ai-playground/ which is:
#   chat-app/graph/builder.py  →  ../../  →  ai-playground/
# load_dotenv is a no-op if the vars are already in the environment,
# so this is safe to call even in production.
# ---------------------------------------------------------------------------

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

# ---------------------------------------------------------------------------
# Database URI — always from environment, never hardcoded
# ---------------------------------------------------------------------------

DB_URI = os.getenv(
    "DB_URI",
    "postgresql://postgres:password@localhost:5432/ailixir",  # fallback for local dev
)


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def _route_after_guardrail(state: AgentState) -> str:
    """Block immediately if guardrail fired; otherwise continue to intent."""
    return END if state.get("intent") == "BLOCKED" else "intent_node"


def _route_after_intent(state: AgentState) -> str:
    """Follow-ups need rewriting; new questions go straight to retrieval."""
    return "rewrite_node" if state.get("intent") == "FOLLOWUP" else "retrieve_node"


def _route_after_retrieve(state: AgentState) -> str:
    """
    If the caller set streaming=True (the /chat/stream endpoint), skip the
    answer node entirely — main.py will stream Gemini directly.
    Otherwise, run the answer node for a complete synchronous response.
    """
    return END if state.get("streaming") else "answer_node"


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------

def build_graph():
    """
    Builds and compiles the LangGraph agent with a PostgreSQL checkpointer.

    Call once on application startup (FastAPI lifespan).
    """
    builder = StateGraph(AgentState)

    # Register nodes
    builder.add_node("guardrail_node", guardrail_node)
    builder.add_node("intent_node",    intent_node)
    builder.add_node("rewrite_node",   rewrite_node)
    builder.add_node("retrieve_node",  retrieve_node)
    builder.add_node("answer_node",    answer_node)

    # Entry point
    builder.set_entry_point("guardrail_node")

    # Edges
    builder.add_conditional_edges(
        "guardrail_node",
        _route_after_guardrail,
        {"intent_node": "intent_node", END: END},
    )

    builder.add_conditional_edges(
        "intent_node",
        _route_after_intent,
        {"rewrite_node": "rewrite_node", "retrieve_node": "retrieve_node"},
    )

    # rewrite always feeds into retrieve
    builder.add_edge("rewrite_node", "retrieve_node")

    builder.add_conditional_edges(
        "retrieve_node",
        _route_after_retrieve,
        {"answer_node": "answer_node", END: END},
    )

    builder.add_edge("answer_node", END)

    # Checkpointer (session memory via PostgreSQL)
    connection = psycopg.connect(DB_URI)
    checkpointer = PostgresSaver(connection)
    checkpointer.setup()   # creates tables if they don't exist — idempotent

    return builder.compile(checkpointer=checkpointer)