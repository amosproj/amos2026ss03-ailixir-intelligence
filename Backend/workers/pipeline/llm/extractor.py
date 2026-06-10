"""
LLM-based document analyzer using Gemini multimodal (Vertex AI).

analyze_document()       — PDF bytes → {document_type, document_purpose, document_date, episode_body}
update_journey_summary() — current summary + extraction → updated summary string

Entity and edge extraction is NOT done here. It is handled by Graphiti's
internal LLM against the fixed medical schema in graph/medical_schema.py.
This separation enables entity merging and temporal updates across documents.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re

from google.genai import types

from workers.connections.gemini_client import get_gemini_client
from workers.connections.paced_gemini import pace_gemini_call
from workers.pipeline.llm.prompts import EXTRACTION_PROMPT, SUMMARY_UPDATE_PROMPT

_log = logging.getLogger(__name__)

# `gemini-2.5-flash` (not -lite) — needs the higher RPM budget for parallel
# multi-doc workloads. Terraform pins the same value via VERTEX_LLM_MODEL;
# this is the local-dev/fallback default. See graphiti_client.py for the
# matching rationale (whole worker should share one model).
_DEFAULT_LLM_MODEL = "gemini-2.5-flash"

# Per-call upper bound. A typical clinical PDF resolves in 5-30s; 120s
# leaves headroom for German pathology reports + Vertex queue jitter
# without letting a genuinely hung call camp on a Cloud Run instance.
# Pub/Sub ack deadline is 600s, so an exception here still gives the
# delivery plenty of slack to be retried.
_LLM_CALL_TIMEOUT_S = float(os.environ.get("LLM_CALL_TIMEOUT_S", "120"))


# ── JSON parsing helpers ──────────────────────────────────────────────────────

def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _extract_json_object(text: str) -> dict:
    """Find and parse the first complete JSON object in the LLM response."""
    text = _strip_markdown_fences(text)
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object in LLM response: {text[:300]}")
    depth, end = 0, -1
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        raise ValueError("LLM returned an unclosed JSON object")
    return json.loads(text[start : end + 1])


def _extract_finish_reason(response: object) -> str | None:
    """Pull the first candidate's finish_reason out of a Gemini response.

    Empty .text is most often MAX_TOKENS (prompt + answer overran the
    token budget — needs a shorter prompt or smaller doc) or SAFETY
    (Vertex's content filter blocked the answer). Different operator
    response than "Vertex is broken", so we surface it in the raised
    exception for the on-call runbook. Returns None if the response
    object is shaped unexpectedly — we never want this helper to throw
    while we're already in an error path.
    """
    try:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return None
        reason = getattr(candidates[0], "finish_reason", None)
        # Vertex returns this as an enum; str() gives a stable, log-friendly form.
        return str(reason) if reason is not None else None
    except Exception:
        return None


# ── Public API ────────────────────────────────────────────────────────────────

async def analyze_document(
    file_bytes: bytes,
    filename: str,
    mime_type: str = "application/pdf",
    previous_summary: str = "",
) -> dict:
    """
    Send a document to Gemini multimodal and extract clinical information.

    Supports any MIME type that Gemini accepts (application/pdf, image/jpeg,
    image/png, image/webp, image/gif). The mime_type should match the actual
    file content — it is forwarded directly to the Gemini API.

    Passes the patient journey summary as context so each new document
    is interpreted relative to the patient's known history.

    Returns a dict with exactly four keys:
      document_type    — e.g. "Laborbericht"
      document_purpose — one-sentence role in the patient journey
      document_date    — YYYY-MM-DD string or None
      episode_body     — rich clinical narrative for Graphiti entity extraction
    """
    model = os.environ.get("VERTEX_LLM_MODEL", _DEFAULT_LLM_MODEL)
    client = await get_gemini_client()
    summary_text = previous_summary.strip() or "No previous documents processed yet."

    prompt_text = EXTRACTION_PROMPT.format(
        filename=filename,
        summary=summary_text,
    )

    # Pace + bound the Vertex call:
    #   - pace_gemini_call() shares the worker's single admission queue with
    #     Graphiti's internal Gemini calls so two parallel document analyses
    #     can't burst past the project's per-minute RPM quota.
    #   - asyncio.wait_for caps wall time so a Vertex hang doesn't squat on a
    #     Cloud Run instance until Pub/Sub redelivers (~600s).
    await pace_gemini_call()
    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                    types.Part.from_text(text=prompt_text),
                ],
            ),
            timeout=_LLM_CALL_TIMEOUT_S,
        )
    except asyncio.TimeoutError as exc:
        # Convert to a domain-appropriate exception so the pipeline's outer
        # except block records a clear FAILED reason rather than a stack
        # frame buried in the Vertex SDK. TimeoutError is also one of the
        # retryable classes in workers/main.py — Pub/Sub will redeliver.
        raise TimeoutError(
            f"Gemini analyze_document timed out after {_LLM_CALL_TIMEOUT_S:.0f}s "
            f"for file {filename!r}"
        ) from exc

    raw = (response.text or "").strip()
    if not raw:
        # Surface the underlying finish reason if Gemini gave us one — most
        # often this is MAX_TOKENS (prompt + answer exceeded the budget) or
        # SAFETY (the document tripped a Vertex safety filter). Treating
        # both as the same "empty response" hides actionable signal.
        finish_reason = _extract_finish_reason(response)
        raise ValueError(
            f"Gemini returned empty response for document: {filename!r} "
            f"(finish_reason={finish_reason!r})"
        )

    result = _extract_json_object(raw)
    _log.info(
        "llm_extract_done filename=%s mime=%s doc_type=%s doc_date=%s episode_len=%d",
        filename,
        mime_type,
        result.get("document_type", "unknown"),
        result.get("document_date"),
        len(result.get("episode_body", "")),
    )
    return result


async def update_journey_summary(
    current_summary: str,
    extraction: dict,
    doc_name: str,
) -> str:
    """
    Produce an updated patient journey summary incorporating the new extraction.
    Returns the updated summary as a plain string.
    """
    model = os.environ.get("VERTEX_LLM_MODEL", _DEFAULT_LLM_MODEL)
    client = await get_gemini_client()

    prompt_text = SUMMARY_UPDATE_PROMPT.format(
        current_summary=current_summary.strip() or "No prior summary — this is the first document.",
        doc_name=doc_name,
        doc_type=extraction.get("document_type", "Unknown"),
        doc_purpose=extraction.get("document_purpose", "Unknown"),
        episode_body=extraction.get("episode_body", ""),
    )

    # Same pacing + timeout discipline as analyze_document(). Calls share
    # the worker's single admission queue so a multi-doc burst can't double
    # the effective Vertex call rate by going through two different code
    # paths.
    await pace_gemini_call()
    try:
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=model,
                contents=[types.Part.from_text(text=prompt_text)],
            ),
            timeout=_LLM_CALL_TIMEOUT_S,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError(
            f"Gemini update_journey_summary timed out after {_LLM_CALL_TIMEOUT_S:.0f}s"
        ) from exc

    updated = (response.text or "").strip()
    if not updated:
        finish_reason = _extract_finish_reason(response)
        raise ValueError(
            f"Gemini returned empty response for summary update "
            f"(finish_reason={finish_reason!r})"
        )

    _log.info(
        "journey_summary_updated doc_name=%s summary_len=%d",
        doc_name,
        len(updated),
    )
    return updated
