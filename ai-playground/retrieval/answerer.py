"""
LLM answering step for the retrieval pipeline.

Takes the facts (EntityEdge) and entities (EntityNode) retrieved from
the user's Graphiti knowledge graph and sends them to Gemini (Vertex AI)
to produce a natural-language answer.

This is pure graph-RAG: instead of raw text chunks, the context is
structured FACTS extracted during ingestion — each fact is a temporal
relationship between two medical entities (e.g. "Patient is prescribed
Tamoxifen 20mg daily as of 2024-01-15"). This gives the LLM precise,
de-duplicated, temporally-aware medical information to reason over.

Graphiti itself has no built-in answer step — retrieval and answering
are intentionally separate so you can swap the LLM independently.

Auth: same Application Default Credentials as the rest of the pipeline.
  Local:  gcloud auth application-default login
  GCP:    Cloud Run service account is used automatically
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from retrieval.pipeline import RetrievalOutput

_HERE = Path(__file__).resolve().parent
load_dotenv(dotenv_path=_HERE.parent / ".env")  # ai-playground/.env

_log = logging.getLogger(__name__)

_DEFAULT_LLM_MODEL = "gemini-2.5-flash"
_QA_TIMEOUT_S      = 60.0


# ── Prompts ───────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a medical AI assistant for the Ailixir health application.

You have been given a set of FACTS and ENTITIES extracted from a patient's
medical knowledge graph. These facts were derived from real uploaded medical
documents (lab reports, pathology results, physician letters, etc.).

Your task: answer the user's question using ONLY the provided facts and entities.

Guidelines:
- Be precise and factual. Cite dates when they are relevant to the answer.
- Distinguish between CURRENT facts (still valid) and HISTORICAL facts
  (superseded by newer data). Make it clear if something is no longer current.
- If the provided context does not contain enough information to fully answer
  the question, say so explicitly. Do NOT guess or fabricate.
- Use clear, plain language suitable for a patient reading their own health data.
  Avoid unexplained medical jargon unless the question itself uses it.
- Keep the answer focused and concise — use bullet points where helpful.\
"""

_QA_PROMPT = """\
{context}

---
PATIENT QUESTION: {query}

Answer based strictly on the facts and entities above.\
"""


# ── Context formatter (LLM-optimised) ────────────────────────────────────────

def _fmt(dt: datetime | None) -> str:
    if dt is None:
        return "unknown date"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def format_context_for_llm(retrieval: RetrievalOutput) -> str:
    """
    Format retrieved facts + entities into a compact, structured prompt block.

    Separates current facts (invalid_at is None) from historical ones so the
    LLM can reason about the temporal state of the patient's health.
    """
    lines: list[str] = []

    lines.append("PATIENT KNOWLEDGE GRAPH CONTEXT")
    lines.append("=" * 50)

    # ── Facts split by temporal status ───────────────────────────────────────
    current   = [e for e in retrieval.edges if e.invalid_at is None]
    historical = [e for e in retrieval.edges if e.invalid_at is not None]

    if current:
        lines.append(f"\n[CURRENT FACTS — {len(current)} result(s)]")
        for i, edge in enumerate(current, start=1):
            lines.append(
                f"{i}. [{edge.name}] (from {_fmt(edge.valid_at)})"
            )
            lines.append(f"   {edge.fact}")
    else:
        lines.append("\n[CURRENT FACTS]\nNone found for this query.")

    if historical:
        lines.append(f"\n[HISTORICAL FACTS — superseded, {len(historical)} result(s)]")
        for i, edge in enumerate(historical, start=1):
            lines.append(
                f"{i}. [{edge.name}] ({_fmt(edge.valid_at)} → {_fmt(edge.invalid_at)})"
            )
            lines.append(f"   {edge.fact}")

    # ── Entities ─────────────────────────────────────────────────────────────
    if retrieval.nodes:
        lines.append(f"\n[RELEVANT MEDICAL ENTITIES — {len(retrieval.nodes)} result(s)]")
        for i, node in enumerate(retrieval.nodes, start=1):
            labels = ", ".join(node.labels) if node.labels else "Entity"
            lines.append(f"{i}. [{labels}] {node.name}")
            if node.summary:
                lines.append(f"   {node.summary}")
    else:
        lines.append("\n[RELEVANT MEDICAL ENTITIES]\nNone found for this query.")

    lines.append("\n" + "=" * 50)
    return "\n".join(lines)


# ── Gemini client (lazy, created per-call in playground) ─────────────────────

def _make_vertex_client() -> genai.Client:
    project  = os.environ.get("VERTEX_PROJECT", "")
    location = os.environ.get("VERTEX_LOCATION", "us-central1")
    if not project:
        raise EnvironmentError(
            "VERTEX_PROJECT is not set. Add it to ai-playground/.env"
        )
    return genai.Client(vertexai=True, project=project, location=location)


# ── Public API ────────────────────────────────────────────────────────────────

async def generate_answer(
    query: str,
    retrieval: RetrievalOutput,
) -> str:
    """
    Send retrieved knowledge graph context to Gemini and return a natural-
    language answer to the user's query.

    Uses client.aio.models.generate_content() (async, non-blocking).
    Temperature=0.1 for factual, low-hallucination medical responses.

    Args:
        query:     The original user question.
        retrieval: RetrievalOutput from run_retrieval() containing edges + nodes.

    Returns:
        A natural-language string answering the query based on graph facts.

    Raises:
        ValueError: If Gemini returns an empty response.
        TimeoutError: If the Gemini call exceeds _QA_TIMEOUT_S.
        EnvironmentError: If VERTEX_PROJECT is missing from env.
    """
    model  = os.environ.get("VERTEX_LLM_MODEL", _DEFAULT_LLM_MODEL)
    client = _make_vertex_client()

    context = format_context_for_llm(retrieval)
    prompt  = _QA_PROMPT.format(context=context, query=query)

    _log.info(
        "generate_answer user_id=%s model=%s facts=%d entities=%d",
        retrieval.user_id, model, retrieval.total_edges, retrieval.total_nodes,
    )

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
            timeout=_QA_TIMEOUT_S,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError(
            f"Gemini QA call timed out after {_QA_TIMEOUT_S:.0f}s"
        ) from exc

    answer = (response.text or "").strip()
    if not answer:
        candidates = getattr(response, "candidates", [])
        finish_reason = None
        if candidates:
            finish_reason = str(getattr(candidates[0], "finish_reason", None))
        raise ValueError(
            f"Gemini returned an empty answer (finish_reason={finish_reason!r}). "
            "This may be due to a safety filter or token budget issue."
        )

    _log.info("generate_answer done answer_len=%d", len(answer))
    return answer
