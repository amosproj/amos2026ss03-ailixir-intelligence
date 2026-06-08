"""
LLM-based document analyzer using Gemini multimodal (Vertex AI).

analyze_document()       — PDF bytes → {document_type, document_purpose, document_date, episode_body}
update_journey_summary() — current summary + extraction → updated summary string

Entity and edge extraction is NOT done here. It is handled by Graphiti's
internal LLM against the fixed medical schema in graph/medical_schema.py.
This separation enables entity merging and temporal updates across documents.
"""

from __future__ import annotations

import json
import logging
import os
import re

from google.genai import types

from workers.connections.gemini_client import get_gemini_client
from workers.pipeline.llm.prompts import EXTRACTION_PROMPT, SUMMARY_UPDATE_PROMPT

_log = logging.getLogger(__name__)
_DEFAULT_LLM_MODEL = "gemini-2.5-flash"


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


# ── Public API ────────────────────────────────────────────────────────────────

async def analyze_document(
    pdf_bytes: bytes,
    filename: str,
    previous_summary: str = "",
) -> dict:
    """
    Send a PDF to Gemini multimodal and extract clinical information.

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

    response = await client.aio.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            types.Part.from_text(text=prompt_text),
        ],
    )

    raw = (response.text or "").strip()
    if not raw:
        raise ValueError(f"Gemini returned empty response for document: {filename!r}")

    result = _extract_json_object(raw)
    _log.info(
        "llm_extract_done filename=%s doc_type=%s doc_date=%s episode_len=%d",
        filename,
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

    response = await client.aio.models.generate_content(
        model=model,
        contents=[types.Part.from_text(text=prompt_text)],
    )

    updated = (response.text or "").strip()
    if not updated:
        raise ValueError("Gemini returned empty response for summary update")

    _log.info(
        "journey_summary_updated doc_name=%s summary_len=%d",
        doc_name,
        len(updated),
    )
    return updated
