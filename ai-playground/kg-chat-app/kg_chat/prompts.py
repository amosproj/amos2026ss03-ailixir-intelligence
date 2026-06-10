from __future__ import annotations

import json
from typing import Any


def build_query_prompt(
    *,
    question: str,
    schema_text: str,
    history_text: str,
    default_limit: int,
) -> str:
    return f"""
You are a Neo4j Cypher query generator for a knowledge-graph chat backend.

Use only the graph schema below. Do not invent labels, relationship types, or
properties that are not present in the schema. Prefer the observed relationship
patterns when choosing a traversal.

GRAPH SCHEMA:
{schema_text}

CONVERSATION HISTORY:
{history_text or "(none)"}

Rules:
- Return JSON only. No markdown fences and no explanation outside JSON.
- Generate exactly one read-only Cypher query. The "cypher" value must always
  be a non-empty string, never null.
- Base the query only on the schema, properties, and observed relationship
  patterns shown above.
- Use parameters for user-provided names and values.
- Use only MATCH, OPTIONAL MATCH, WHERE, WITH, RETURN, ORDER BY, SKIP, LIMIT,
  UNWIND, collect, count, properties, labels, type, coalesce, toLower, and
  string/list functions.
- Do not use CREATE, MERGE, DELETE, DETACH, SET, REMOVE, DROP, LOAD CSV, CALL,
  APOC, GDS, dbms, or admin procedures.
- Include LIMIT {default_limit} unless the query is a pure count.
- If the question is broad or the exact path is unclear, use the most relevant
  observed relationship pattern from the schema and return neighboring facts.
- Prefer text-bearing properties shown in the schema, such as name, summary,
  content, fact, source_description, or labels, when filtering and returning
  results.

Return this exact JSON shape:
{{
  "cypher": "MATCH ... RETURN ... LIMIT {default_limit}",
  "parameters": {{}},
  "reason": "short reason"
}}

User question:
{question}
""".strip()


def build_query_repair_prompt(
    *,
    question: str,
    schema_text: str,
    history_text: str,
    default_limit: int,
    invalid_response: str,
    error: str,
) -> str:
    return f"""
Your previous response could not be used by the backend.

Validation error:
{error}

Previous response:
{invalid_response}

Repair the response for this Neo4j graph query task.

GRAPH SCHEMA:
{schema_text}

CONVERSATION HISTORY:
{history_text or "(none)"}

Rules:
- Return JSON only.
- The "cypher" field must be a non-empty string.
- The "parameters" field must be an object.
- Generate one read-only Cypher query using only the schema above.
- Do not return null for any required field.
- Use parameters for user-provided names and values.
- Include LIMIT {default_limit} unless the query is a pure count.
- Do not use CREATE, MERGE, DELETE, DETACH, SET, REMOVE, DROP, LOAD CSV, CALL,
  APOC, GDS, dbms, or admin procedures.

Return exactly:
{{
  "cypher": "MATCH ... RETURN ... LIMIT {default_limit}",
  "parameters": {{}},
  "reason": "short reason"
}}

User question:
{question}
""".strip()


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
