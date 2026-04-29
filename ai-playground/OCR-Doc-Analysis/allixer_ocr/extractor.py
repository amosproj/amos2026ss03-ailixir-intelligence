"""
Domain-agnostic document extraction engine for the Allixer project.

Usage
-----
from allixer_ocr.extractor import DocumentExtractor

extractor = DocumentExtractor(api_key="sk-or-v1-...")

# Medical
result = extractor.extract("scan.jpg", domain="medical")
print(result.json(indent=2))

# Financial
result = extractor.extract("invoice.png", domain="financial")
print(result.json(indent=2))
"""

from __future__ import annotations
import json
import logging
from typing import Any

from openai import OpenAI

from .preprocessor import preprocess
from .prompts import get_prompt_factory
from .schemas.medical import MedicalDocument
from .schemas.financial import FinancialDocument

logger = logging.getLogger(__name__)

# Map domain name → Pydantic root model
DOMAIN_SCHEMA_MAP = {
    "medical": MedicalDocument,
    "financial": FinancialDocument,
}

DEFAULT_MODEL = "baidu/qianfan-ocr-fast:free"


class ExtractionError(Exception):
    """Raised when extraction or validation fails."""


class DocumentExtractor:
    """
    Domain-agnostic document extractor.

    Responsibilities
    ----------------
    1. Pre-process the image (resize → grayscale → CLAHE).
    2. Build the domain-specific prompt.
    3. Call the vision LLM via OpenRouter.
    4. Parse and validate the JSON response with Pydantic.
    5. Return a validated, normalised Pydantic model.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str = "https://openrouter.ai/api/v1",
    ) -> None:
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    # ── Public API ──────────────────────────────────────────────────────────

    def extract(
        self,
        source: str | bytes,
        *,
        domain: str,
        preprocess_kwargs: dict | None = None,
    ) -> MedicalDocument | FinancialDocument:
        """
        Full pipeline: preprocess → prompt → call LLM → validate.

        Parameters
        ----------
        source : str | bytes
            File path or raw image bytes.
        domain : str
            'medical' or 'financial'
        preprocess_kwargs : dict, optional
            Override preprocessing defaults.

        Returns
        -------
        Validated Pydantic model instance.
        """
        # 1. Pre-process
        pp_kwargs = preprocess_kwargs or {}
        b64_image, meta = preprocess(source, **pp_kwargs)
        logger.info("Preprocessed image: %s", meta)

        # 2. Build prompts
        factory = get_prompt_factory(domain)
        system = factory.system_prompt()
        user_text = factory.user_prompt()
        data_url = f"data:image/jpeg;base64,{b64_image}"

        # 3. Call LLM
        raw_json = self._call_model(system, user_text, data_url)

        # 4. Parse & validate
        return self._validate(raw_json, domain)

    def extract_raw(
        self,
        source: str | bytes,
        *,
        domain: str,
        preprocess_kwargs: dict | None = None,
    ) -> dict:
        """Same as extract() but returns a plain dict (no Pydantic validation)."""
        pp_kwargs = preprocess_kwargs or {}
        b64_image, meta = preprocess(source, **pp_kwargs)
        factory = get_prompt_factory(domain)
        data_url = f"data:image/jpeg;base64,{b64_image}"
        return json.loads(self._call_model(factory.system_prompt(), factory.user_prompt(), data_url))

    # ── Private helpers ─────────────────────────────────────────────────────

    def _call_model(self, system: str, user_text: str, data_url: str) -> str:
        """Send the multimodal request and return raw response text."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": user_text},
                    ],
                },
            ],
        )
        return response.choices[0].message.content

    def _validate(self, raw: str, domain: str) -> Any:
        """Strip markdown fences, parse JSON, validate with Pydantic."""
        # Strip ```json ... ``` fences if the model added them
        clean = raw.strip()
        if clean.startswith("```"):
            lines = clean.splitlines()
            clean = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        try:
            data = json.loads(clean)
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"Model returned invalid JSON: {exc}\n---\n{raw}") from exc

        schema_cls = DOMAIN_SCHEMA_MAP.get(domain.lower())
        if schema_cls is None:
            return data  # unknown domain – return raw dict

        try:
            return schema_cls(**data)
        except Exception as exc:
            raise ExtractionError(f"Pydantic validation failed for domain '{domain}': {exc}") from exc
