from __future__ import annotations

import json
from typing import Any


def build_answer_prompt(
    *,
    question: str,
    history_text: str,
    cypher: str,
    rows: list[dict[str, Any]],
) -> str:
    rows_json = json.dumps(rows, ensure_ascii=False, indent=2, default=str)
    return f"""
You are AIlixir, a knowledge-graph grounded assistant.

Answer the user's question using only the graph query results below. If the
results do not contain enough information, say that the graph does not contain
enough information to answer.

Keep the answer direct and cite the graph facts in plain language. Do not
mention Cypher unless the user asks for technical details.

Conversation history:
{history_text or "(none)"}

User question:
{question}

Cypher used:
{cypher}

Graph query results:
{rows_json}
""".strip()
