from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection

from graph.state import AgentState
from graph.nodes import (
    detect_intent_node,
    rewrite_question_node,
    retrieve_node,
    answer_node,
    guardrail_node,
)

DB_URI = "postgresql://postgres:123@localhost:5432/ailixir"


def route_after_guardrail(state: AgentState):
    return "blocked" if state.get("intent") == "BLOCKED" else "allowed"


def route_after_intent(state: AgentState):
    return "rewrite" if state["intent"] == "FOLLOWUP" else "retrieve"


def build_graph():

    workflow = StateGraph(AgentState)

    # --- Nodes ---
    workflow.add_node("guardrail", guardrail_node)
    workflow.add_node("intent", detect_intent_node)
    workflow.add_node("rewrite", rewrite_question_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("answer", answer_node)

    # --- Entry point ---
    workflow.set_entry_point("guardrail")

    # --- Guardrail: allow → intent, block → END ---
    workflow.add_conditional_edges(
        "guardrail",
        route_after_guardrail,
        {
            "allowed": "intent",
            "blocked": END,
        },
    )

    # --- Intent: followup → rewrite, new → retrieve ---
    workflow.add_conditional_edges(
        "intent",
        route_after_intent,
        {
            "rewrite": "rewrite",
            "retrieve": "retrieve",
        },
    )

    workflow.add_edge("rewrite", "retrieve")
    workflow.add_edge("retrieve", "answer")
    workflow.add_edge("answer", END)

    # --- Postgres checkpointer ---
    conn = Connection.connect(DB_URI)
    conn.autocommit = True

    checkpointer = PostgresSaver(conn)
    checkpointer.setup()

    return workflow.compile(checkpointer=checkpointer)
