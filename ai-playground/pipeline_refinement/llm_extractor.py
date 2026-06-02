"""
LLM-based document analyzer.

Public functions:
  analyze_document()      — PDF bytes → extraction dict containing episode_body,
                            entity_types defs, edge_types defs, edge_type_map defs
  build_graphiti_types()  — converts LLM output into actual Pydantic classes and
                            dicts that can be passed directly to graphiti.add_episode()
  update_journey_summary() — current summary + extraction → updated summary string
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, create_model
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

    Returns a dict with keys:
      document_type     — e.g. "Laborbericht"
      document_purpose  — one-sentence description
      episode_body      — rich narrative paragraph ready for Graphiti
      entity_types      — list of {name, description, fields[]}
      edge_types        — list of {name, description}
      edge_type_map     — list of {source, target, relations[]}
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


def build_graphiti_types(extraction: dict) -> tuple[
    dict[str, type[BaseModel]],
    dict[str, type[BaseModel]],
    dict[tuple[str, str], list[str]],
]:
    """
    Convert the LLM extraction output into Pydantic classes and dicts that
    can be passed directly to graphiti.add_episode().

    Returns:
      entity_types  — dict[str, type[BaseModel]]  e.g. {"Diagnosis": DiagnosisModel}
      edge_types    — dict[str, type[BaseModel]]  e.g. {"HAS_DIAGNOSIS": HasDiagnosisModel}
      edge_type_map — dict[tuple[str,str], list[str]]
                      e.g. {("Patient","Diagnosis"): ["HAS_DIAGNOSIS"]}
    """
    # ── entity_types ──────────────────────────────────────────────────────────
    entity_types: dict[str, type[BaseModel]] = {}
    for et in extraction.get("entity_types", []):
        name: str = et["name"]
        description: str = et.get("description", name)
        field_defs: dict[str, Any] = {}
        for f in et.get("fields", []):
            fname = f["name"]
            fdesc = f.get("description", fname)
            # All fields are optional strings; Graphiti fills them from the narrative
            field_defs[fname] = (
                str | None,
                Field(default=None, description=fdesc),
            )
        model_cls = create_model(name, **field_defs)
        model_cls.__doc__ = description
        entity_types[name] = model_cls

    # ── edge_types ────────────────────────────────────────────────────────────
    edge_types: dict[str, type[BaseModel]] = {}
    for ed in extraction.get("edge_types", []):
        name = ed["name"]
        description = ed.get("description", name)
        edge_cls = create_model(name)
        edge_cls.__doc__ = description
        edge_types[name] = edge_cls

    # ── edge_type_map ─────────────────────────────────────────────────────────
    edge_type_map: dict[tuple[str, str], list[str]] = {}
    for entry in extraction.get("edge_type_map", []):
        key = (entry["source"], entry["target"])
        edge_type_map[key] = entry.get("relations", [])

    return entity_types, edge_types, edge_type_map


def update_journey_summary(
    current_summary: str,
    extraction: dict,
    doc_name: str,
) -> str:
    """
    Produce an updated patient journey summary from the current summary and
    the newly extracted episode_body.

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
