"""
graph/state.py
--------------
Defines the shared state that flows through every LangGraph node.

Adding a field here is the ONLY change needed to pass new data between nodes.

KG integration note
-------------------
When knowledge-graph retrieval lands (issue #75), add fields here:
  kg_subgraph : str   — which KG subgraph was queried
  kg_entities : list  — top entities returned by the KG client
Everything downstream (answer node, API response) will automatically have
access to them without touching other files.
"""

from typing import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # ── Input ─────────────────────────────────────────────────────────────────
    question: str                  # raw question from the user

    # ── Pipeline fields (filled by nodes) ────────────────────────────────────
    intent: str                    # NEW_QUESTION | FOLLOWUP | BLOCKED
    rewritten_question: str        # disambiguated query used for retrieval

    # ── Retrieval ─────────────────────────────────────────────────────────────
    context: str                   # retrieved text passages
    source: str                    # "documents.json" | "knowledge_graph" | "hybrid"
                                   # ↑ used for logging and future routing

    # ── Answer ────────────────────────────────────────────────────────────────
    answer: str                    # final answer (filled by answer node OR streamed)
    streaming: bool                # True  → answer node is skipped (stream endpoint)
                                   #         Gemini is called directly in main.py
                                   # False → answer node runs and fills answer

    # ── Memory ────────────────────────────────────────────────────────────────
    messages: Annotated[list, add_messages]   # full conversation, persisted by Postgres