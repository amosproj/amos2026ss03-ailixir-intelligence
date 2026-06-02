"""
LLM-based document analyzer.

analyze_document()       — PDF bytes → {document_type, document_purpose, episode_body}
update_journey_summary() — current summary + extraction → updated summary string

Entity and edge type schemas are NOT generated here anymore.
They are defined once in medical_schema.py so Graphiti can merge entities
and apply temporal updates consistently across all documents.
"""

from __future__ import annotations

import json
import re

from google.genai import types

from pipeline_refinement.config import LLM_MODEL, get_gemini_client
from pipeline_refinement.prompts import EXTRACTION_PROMPT, SUMMARY_UPDATE_PROMPT


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
        raise ValueError(f"No JSON object found in LLM response:\n{text[:300]}")
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

def analyze_document(
    pdf_bytes: bytes,
    filename: str,
    previous_summary: str = "",
) -> dict:
    """
    Send a PDF to Gemini with journey context.

    Returns a dict with exactly three keys:
      document_type    — e.g. "Laborbericht"
      document_purpose — one-sentence description
      episode_body     — rich clinical narrative for Graphiti to extract from
    """
    client = get_gemini_client()
    summary_text = previous_summary.strip() or "No previous documents processed yet."

    prompt_text = EXTRACTION_PROMPT.format(
        filename=filename,
        summary=summary_text,
    )

    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            types.Part.from_text(text=prompt_text),
        ],
    )

    raw = (response.text or "").strip()
    if not raw:
        raise ValueError("Gemini returned an empty response for document analysis")

    return _extract_json_object(raw)


def update_journey_summary(
    current_summary: str,
    extraction: dict,
    doc_name: str,
) -> str:
    """
    Produce an updated patient journey summary incorporating the new extraction.
    Returns the updated summary as a plain string.
    """
    client = get_gemini_client()

    prompt_text = SUMMARY_UPDATE_PROMPT.format(
        current_summary=current_summary.strip() or "No prior summary — this is the first document.",
        doc_name=doc_name,
        doc_type=extraction.get("document_type", "Unknown"),
        doc_purpose=extraction.get("document_purpose", "Unknown"),
        episode_body=extraction.get("episode_body", ""),
    )

    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=[types.Part.from_text(text=prompt_text)],
    )

    updated = (response.text or "").strip()
    if not updated:
        raise ValueError("Gemini returned an empty response for summary update")

    return updated
