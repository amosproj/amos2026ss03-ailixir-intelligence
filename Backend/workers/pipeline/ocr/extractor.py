"""
Document OCR dispatcher.

Routes file bytes to the correct backend by MIME type:
  application/pdf  → Google Cloud Document AI  (document_ai.py)
  image/*          → Gemini vision via Vertex AI (same ADC credentials as the rest)

Both backends return the same schema:
  {
    "document_type": str,
    "confidence_score": float | None,
    "metadata": {"language": ..., "date_detected": ...},
    "extracted_fields": {...},
    "tables": [...],
    "raw_text_blocks": [...]
  }

Image path configured via:
  VERTEX_PROJECT     — GCP project ID
  VERTEX_LOCATION    — region (default: us-central1)
  VERTEX_LLM_MODEL   — Gemini model slug (default: gemini-2.0-flash-001)
"""

from __future__ import annotations

import json
import logging
import os

from google import genai
from google.genai import types

from workers.pipeline.ocr.prompts import SYSTEM_PROMPT, user_message

_log = logging.getLogger(__name__)


def extract(file_bytes: bytes, mime_type: str) -> dict:
    """
    Run OCR on file bytes, routing by MIME type.

    PDFs go to Google Cloud Document AI.
    Images go to Gemini vision via Vertex AI.
    Both return the same extraction schema.
    """
    if mime_type == "application/pdf":
        from workers.pipeline.ocr.document_ai import extract_pdf
        return extract_pdf(file_bytes)
    return _extract_image(file_bytes, mime_type)


def _extract_image(image_bytes: bytes, mime_type: str) -> dict:
    """Run OCR on an image using Gemini vision via Vertex AI (ADC auth)."""
    project = os.environ["VERTEX_PROJECT"]
    location = os.environ.get("VERTEX_LOCATION", "us-central1")
    model = os.environ.get("VERTEX_LLM_MODEL", "gemini-2.0-flash-001")

    client = genai.Client(vertexai=True, project=project, location=location)

    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            types.Part.from_text(text=user_message()),
        ],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.1,
            max_output_tokens=4096,
        ),
    )

    raw_text = response.text or ""
    _log.info("ocr_image_complete model=%s chars=%d", model, len(raw_text))
    return _parse_json(raw_text)


def _parse_json(raw: str) -> dict:
    """Strip optional markdown fences then parse JSON."""
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```", 1)[1]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.rsplit("```", 1)[0].strip()
    return json.loads(clean)
