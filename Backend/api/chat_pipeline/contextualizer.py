"""
Query contextualizer — Step 1 of the chat pipeline.

Determines whether a user's query is self-contained or refers to previous
conversation history (via pronouns, implicit references, follow-up phrasing).

  Self-contained query:
    "What medications is the patient on?"
    → returned unchanged (changed=False)

  Follow-up query (refers to history):
    History: "User asked about Tamoxifen; assistant described it."
    Query:   "Tell me its side effects"
    → rewritten to "What are the side effects of Tamoxifen?" (changed=True)

The LLM returns a JSON object:
    {"query": "<original or rewritten>", "changed": true|false}

We extract and validate this JSON. If the LLM response is malformed we fall
back to the original query (safe degradation — retrieval may be slightly less
accurate but the pipeline does not fail).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re

from google.genai import types

from api.chat_pipeline.gemini_client import get_gemini_client

_log = logging.getLogger(__name__)

_DEFAULT_LLM_MODEL = "gemini-2.5-flash"
_TIMEOUT_S = 30.0
_MAX_HISTORY_TURNS = 10  # last N turns passed to LLM to cap token spend

_SYSTEM_PROMPT = """\
You are a query contextualizer for a medical AI assistant.

Your task: given a conversation history and a new user query, decide whether
the query is self-contained or implicitly refers to something in the history.

A query refers to history if it contains:
- Pronouns: "it", "this", "that", "they", "its", "their"
- Implicit references: "the medication", "the test", "the diagnosis", "the results"
- Follow-up phrasing: "tell me more", "what about", "and also", "what were they"
- Comparative references: "compared to last time", "is it better"

If the query is ALREADY self-contained (no reference to history):
  Return: {"query": "<original query unchanged>", "changed": false}

If the query REFERS to history:
  Rewrite it to include all necessary context so it is fully self-contained.
  Return: {"query": "<rewritten self-contained query>", "changed": true}

Rules:
- Respond ONLY with valid JSON — no explanation, no markdown.
- Keep rewrites concise. Add just enough context to make the query standalone.
- Preserve the user's original intent and phrasing where possible.
- Never change a self-contained query even if history is provided.\
"""

_USER_PROMPT = """\
Conversation history:
{history}

New query: {query}

Return JSON only: {{"query": "...", "changed": true/false}}\
"""


def _format_history(history: list[dict]) -> str:
    """Format last N turns of history as a readable dialogue."""
    turns = history[-_MAX_HISTORY_TURNS:]
    if not turns:
        return "(no prior conversation)"
    lines = []
    for msg in turns:
        role    = msg.get("role", "user").capitalize()
        content = msg.get("content", "").strip()
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """Find and parse the first JSON object in the LLM response."""
    text = text.strip()
    # Strip markdown fences if present
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    text = text.strip()

    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object in response: {text[:200]}")
    depth = 0
    end   = -1
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        raise ValueError("Unclosed JSON object in response")

    return json.loads(text[start : end + 1])


class ContextualizeResult:
    """Result of contextualizing a query."""

    __slots__ = ("query", "changed")

    def __init__(self, query: str, changed: bool) -> None:
        self.query   = query
        self.changed = changed


async def contextualize_query(
    query: str,
    history: list[dict],
) -> ContextualizeResult:
    """
    Rewrite `query` to be self-contained if it references `history`.

    Args:
        query:   The user's latest message.
        history: List of prior turns, each a dict with "role" and "content".
                 Role is "user" or "assistant".

    Returns:
        ContextualizeResult with:
          .query   — original or rewritten query (always a string)
          .changed — True if rewrite was applied, False if passed through

    Never raises: on any error returns the original query unchanged (safe fallback).
    """
    import os
    model = os.environ.get("VERTEX_LLM_MODEL", _DEFAULT_LLM_MODEL)

    # Short-circuit: no history means nothing to refer to
    if not history:
        _log.debug("contextualize: no history, pass-through query=%r", query)
        return ContextualizeResult(query=query, changed=False)

    history_text = _format_history(history)
    prompt       = _USER_PROMPT.format(history=history_text, query=query)

    try:
        client = await get_gemini_client()
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model,
                contents=[types.Part.from_text(text=prompt)],
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_PROMPT,
                    temperature=0.0,   # deterministic — this is classification, not generation
                ),
            ),
            timeout=_TIMEOUT_S,
        )

        raw = (response.text or "").strip()
        if not raw:
            _log.warning("contextualize: empty response, using original query")
            return ContextualizeResult(query=query, changed=False)

        data = _extract_json(raw)

        rewritten = str(data.get("query", query)).strip() or query
        changed   = bool(data.get("changed", False))

        if changed:
            _log.info(
                "contextualize: rewritten query=%r → %r",
                query, rewritten,
            )
        else:
            _log.debug("contextualize: query is self-contained, pass-through")

        return ContextualizeResult(query=rewritten, changed=changed)

    except asyncio.TimeoutError:
        _log.warning("contextualize: timed out after %.0fs, using original query", _TIMEOUT_S)
        return ContextualizeResult(query=query, changed=False)

    except Exception as exc:
        _log.warning("contextualize: failed (%s), using original query", exc)
        return ContextualizeResult(query=query, changed=False)
