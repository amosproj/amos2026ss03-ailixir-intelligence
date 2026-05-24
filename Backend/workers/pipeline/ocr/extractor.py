"""
OpenRouter vision-based document OCR.

Sends raw image bytes to a vision LLM and returns the structured dict
defined by the schema in prompts.py.

Usage:
    from workers.pipeline.ocr.extractor import extract
    result = extract(image_bytes, mime_type="image/jpeg")
    # result["extracted_fields"] → clean key/value dict
    # result["document_type"]   → detected type string
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


def extract(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Run OCR on raw image bytes via OpenRouter.

    Returns the full structured dict from the model.
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
    _log.info("ocr_complete model=%s tokens=%s", model, tokens)

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
