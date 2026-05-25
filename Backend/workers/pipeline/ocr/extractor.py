"""
Document OCR dispatcher.

Routes file bytes to the correct backend based on MIME type:
  application/pdf  → Google Cloud Document AI  (document_ai.py)
  image/*          → OpenRouter vision LLM     (OpenRouter API)

Both backends return the same schema:
  {
    "document_type": str,
    "confidence_score": float | None,
    "metadata": {"language": ..., "date_detected": ..., ...},
    "extracted_fields": {...},
    "tables": [...],
    "raw_text_blocks": [...]
  }

Usage:
    from workers.pipeline.ocr.extractor import extract
    result = extract(file_bytes, mime_type="application/pdf")
    result = extract(file_bytes, mime_type="image/jpeg")
"""

from __future__ import annotations

import base64
import json
import logging
import os

import requests

from workers.pipeline.ocr.prompts import SYSTEM_PROMPT, user_message

_log = logging.getLogger(__name__)

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL = "qwen/qwen2.5-vl-72b-instruct"


def extract(file_bytes: bytes, mime_type: str) -> dict:
    """
    Run OCR on file bytes, routing by MIME type.

    PDFs go to Google Cloud Document AI; images go to the OpenRouter vision LLM.
    Both return the same extraction schema.
    """
    if mime_type == "application/pdf":
        from workers.pipeline.ocr.document_ai import extract_pdf
        return extract_pdf(file_bytes)
    return _extract_image(file_bytes, mime_type)


def _extract_image(image_bytes: bytes, mime_type: str) -> dict:
    """
    Run OCR on raw image bytes via OpenRouter vision LLM.

    Raises requests.HTTPError on API failure.
    Raises json.JSONDecodeError if the model returns malformed JSON.
    """
    api_key = os.environ["OPENROUTER_API_KEY"]
    model = os.getenv("OCR_MODEL", _DEFAULT_MODEL)
    temperature = float(os.getenv("OCR_TEMPERATURE", "0.1"))
    max_tokens = int(os.getenv("OCR_MAX_TOKENS", "4096"))

    data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode()}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": user_message()},
                ],
            },
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    response = requests.post(
        _API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=120,
    )
    response.raise_for_status()

    raw_text: str = response.json()["choices"][0]["message"]["content"]
    tokens = response.json().get("usage", {})
    _log.info("ocr_image_complete model=%s tokens=%s", model, tokens)

    return _parse_json(raw_text)


def _parse_json(raw: str) -> dict:
    """Strip optional markdown fences and parse JSON."""
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```", 1)[1]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.rsplit("```", 1)[0].strip()
    return json.loads(clean)
