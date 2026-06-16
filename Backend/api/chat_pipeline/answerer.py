"""
LLM answering — Step 3 of the chat pipeline.

Takes the retrieved facts (EntityEdge) and entities (EntityNode) from
Step 2 and asks Gemini to produce a natural-language answer to the query.

This is graph-RAG: the LLM reasons over structured relationship facts
("Patient is prescribed Tamoxifen 20mg daily from 2024-01-15") rather
than raw text chunks. This gives temporally-aware, de-duplicated answers
with lower hallucination risk than naive chunk-based retrieval.

History is NOT passed here because the query was already contextualized
in Step 1 — the LLM sees a self-contained query and focused graph facts.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from google.genai import types

from api.chat_pipeline.gemini_client import get_gemini_client
from api.chat_pipeline.retriever import RetrievalResult

_log = logging.getLogger(__name__)

_DEFAULT_LLM_MODEL = "gemini-2.5-flash"
_TIMEOUT_S         = 60.0


_SYSTEM_PROMPT = """\
You are a medical AI assistant for the Ailixir health application.

You have been given FACTS and ENTITIES from a patient's medical knowledge graph.
These facts were extracted from real uploaded medical documents (lab reports,
pathology results, physician letters, imaging results, etc.).

Answer the user's question using ONLY the provided facts and entities.

Guidelines:
- Be precise and cite dates when temporally relevant (e.g. "As of January 2024...").
- Distinguish CURRENT facts (invalid_at = "current") from HISTORICAL ones
  (superseded by newer data). Make it clear when something is no longer active.
- If the context does not contain enough information to fully answer, say so
  clearly — do NOT fabricate or guess.
- Use clear, plain language suitable for a patient reading their own records.
  Avoid unexplained clinical jargon unless the query uses it.
- Keep the answer focused and well-structured. Use bullet points where helpful.\
"""

_QA_PROMPT = """\
{context}

---
PATIENT QUESTION: {query}

Answer based strictly on the facts and entities provided above.\
"""


def _fmt(dt: datetime | None) -> str:
    if dt is None:
        return "unknown date"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def _build_llm_context(result: RetrievalResult) -> str:
    """
    Format graph retrieval results into a compact, structured prompt block.

    Separates current facts (invalid_at is None) from historical ones so
    the LLM can reason accurately about the patient's current health state.
    """
    lines: list[str] = []
    lines.append("PATIENT KNOWLEDGE GRAPH CONTEXT")
    lines.append("=" * 50)

    current    = [e for e in result.edges if e.invalid_at is None]
    historical = [e for e in result.edges if e.invalid_at is not None]

    if current:
        lines.append(f"\n[CURRENT FACTS — {len(current)}]")
        for i, edge in enumerate(current, start=1):
            lines.append(f"{i}. [{edge.name}] (from {_fmt(edge.valid_at)})")
            lines.append(f"   {edge.fact}")
    else:
        lines.append("\n[CURRENT FACTS]\nNone found.")

    if historical:
        lines.append(f"\n[HISTORICAL FACTS — superseded, {len(historical)}]")
        for i, edge in enumerate(historical, start=1):
            lines.append(
                f"{i}. [{edge.name}] ({_fmt(edge.valid_at)} → {_fmt(edge.invalid_at)})"
            )
            lines.append(f"   {edge.fact}")

    if result.nodes:
        lines.append(f"\n[RELEVANT MEDICAL ENTITIES — {len(result.nodes)}]")
        for i, node in enumerate(result.nodes, start=1):
            labels = ", ".join(node.labels) if node.labels else "Entity"
            lines.append(f"{i}. [{labels}] {node.name}")
            if node.summary:
                lines.append(f"   {node.summary}")
    else:
        lines.append("\n[RELEVANT MEDICAL ENTITIES]\nNone found.")

    lines.append("\n" + "=" * 50)
    return "\n".join(lines)


async def generate_answer(
    query: str,
    result: RetrievalResult,
) -> str:
    """
    Call Gemini with the retrieved graph context and return a natural-language answer.

    Args:
        query:  The (contextualized) user question.
        result: RetrievalResult from retrieve() containing edges + nodes.

    Returns:
        Natural-language answer string.

    Raises:
        ValueError:   If Gemini returns an empty response.
        TimeoutError: If the call exceeds _TIMEOUT_S.
    """
    import os
    model = os.environ.get("VERTEX_LLM_MODEL", _DEFAULT_LLM_MODEL)

    context = _build_llm_context(result)
    prompt  = _QA_PROMPT.format(context=context, query=query)

    _log.info(
        "generate_answer user_id=%s model=%s facts=%d entities=%d",
        result.user_id, model, result.total_edges, result.total_nodes,
    )

    client = await get_gemini_client()

    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model,
                contents=[types.Part.from_text(text=prompt)],
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_PROMPT,
                    temperature=0.1,
                ),
            ),
            timeout=_TIMEOUT_S,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError(
            f"Gemini answer call timed out after {_TIMEOUT_S:.0f}s"
        ) from exc

    answer = (response.text or "").strip()
    if not answer:
        candidates = getattr(response, "candidates", [])
        finish_reason = None
        if candidates:
            finish_reason = str(getattr(candidates[0], "finish_reason", None))
        raise ValueError(
            f"Gemini returned empty answer (finish_reason={finish_reason!r})"
        )

    _log.info("generate_answer done answer_len=%d", len(answer))
    return answer
