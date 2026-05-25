"""
Document OCR via Google Cloud Document AI.

Handles all supported file types — PDF, JPEG, PNG, TIFF, BMP, WebP — with a
single backend. Returns a consistent extraction schema for the rest of the pipeline:

  {
    "document_type": str,
    "confidence_score": float | None,
    "metadata": {"language": ..., "date_detected": ..., "page_count": int},
    "extracted_fields": {...},
    "tables": [...],
    "raw_text_blocks": [...]
  }

Configure via:
  GCP_PROJECT_ID           — already set by terraform in Cloud Run
  DOCUMENT_AI_LOCATION     — processor region, e.g. "us" or "eu"  (default: us)
  DOCUMENT_AI_PROCESSOR_ID — processor ID from GCP Console
"""

from __future__ import annotations

from workers.pipeline.ocr.document_ai import extract_document


def extract(file_bytes: bytes, mime_type: str) -> dict:
    """Run OCR on any supported file (PDF or image) via Document AI."""
    return extract_document(file_bytes, mime_type)
