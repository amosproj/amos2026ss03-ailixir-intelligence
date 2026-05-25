"""
Google Cloud Document AI — PDF OCR extractor.

Converts raw PDF bytes to the same extraction schema returned by the OpenRouter
vision extractor so the rest of the pipeline is agnostic to file type.

Configure via:
  GCP_PROJECT_ID           — already set by terraform in Cloud Run
  DOCUMENT_AI_LOCATION     — processor region, e.g. "us" or "eu"  (default: us)
  DOCUMENT_AI_PROCESSOR_ID — processor ID from GCP Console (required for PDFs)

The processor type determines what ends up in extracted_fields:
  - Document OCR processor  → only raw_text_blocks populated, extracted_fields empty
  - Form Parser processor   → key-value pairs extracted into extracted_fields
  - Specialized processors  → richest structured data (invoices, receipts, etc.)
"""

from __future__ import annotations

import logging
import os

from google.api_core.client_options import ClientOptions
from google.cloud import documentai

_log = logging.getLogger(__name__)


def extract_pdf(pdf_bytes: bytes) -> dict:
    """
    Run OCR on a PDF using Google Cloud Document AI.

    Returns a dict in the same schema as the OpenRouter image extractor:
      document_type, confidence_score, metadata, extracted_fields, tables,
      raw_text_blocks.

    Raises KeyError if DOCUMENT_AI_PROCESSOR_ID is not set.
    """
    project_id = os.environ["GCP_PROJECT_ID"]
    location = os.getenv("DOCUMENT_AI_LOCATION", "us")
    processor_id = os.environ["DOCUMENT_AI_PROCESSOR_ID"]

    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    client = documentai.DocumentProcessorServiceClient(client_options=opts)
    name = client.processor_path(project_id, location, processor_id)

    result = client.process_document(
        request=documentai.ProcessRequest(
            name=name,
            raw_document=documentai.RawDocument(
                content=pdf_bytes,
                mime_type="application/pdf",
            ),
        )
    )
    doc = result.document

    # Collect per-page text and running confidence average
    pages_text: list[str] = []
    confidence_sum = 0.0
    confidence_count = 0

    for page in doc.pages:
        page_lines: list[str] = []
        for block in page.blocks:
            text = _segment_text(block.layout, doc.text)
            if text.strip():
                page_lines.append(text.strip())
            if block.layout.confidence:
                confidence_sum += block.layout.confidence
                confidence_count += 1
        if page_lines:
            pages_text.append("\n".join(page_lines))

    confidence = (confidence_sum / confidence_count) if confidence_count else None

    # Entities are only populated by Form Parser / specialized processors.
    # Plain Document OCR processor leaves this empty — that's expected.
    extracted_fields: dict = {}
    for entity in doc.entities:
        key = entity.type_.replace("/", "_").replace("-", "_").lower()
        value = entity.mention_text.strip() if entity.mention_text else None
        if key in extracted_fields:
            existing = extracted_fields[key]
            if isinstance(existing, list):
                existing.append(value)
            else:
                extracted_fields[key] = [existing, value]
        else:
            extracted_fields[key] = value

    _log.info(
        "document_ai_complete pages=%d entities=%d confidence=%.3f",
        len(doc.pages),
        len(doc.entities),
        confidence or 0.0,
    )

    return {
        "document_type": "pdf_document",
        "confidence_score": round(confidence, 3) if confidence else None,
        "metadata": {
            "language": None,
            "date_detected": None,
            "page_count": len(doc.pages),
        },
        "extracted_fields": extracted_fields,
        "tables": _extract_tables(doc),
        "raw_text_blocks": pages_text,
    }


def _segment_text(layout: documentai.Document.Page.Layout, full_text: str) -> str:
    """Slice the document's full text string using a layout's text anchors."""
    parts: list[str] = []
    for seg in layout.text_anchor.text_segments:
        start = int(seg.start_index)
        end = int(seg.end_index)
        parts.append(full_text[start:end])
    return "".join(parts)


def _extract_tables(doc: documentai.Document) -> list[list[dict]]:
    """Convert Document AI page tables into a list of row-dicts."""
    tables: list[list[dict]] = []
    for page in doc.pages:
        for table in page.tables:
            if not table.body_rows:
                continue
            headers = [
                _segment_text(cell.layout, doc.text).strip()
                for row in table.header_rows
                for cell in row.cells
            ] if table.header_rows else []

            rows: list[dict] = []
            for row in table.body_rows:
                cells = [
                    _segment_text(cell.layout, doc.text).strip()
                    for cell in row.cells
                ]
                if headers and len(headers) == len(cells):
                    rows.append(dict(zip(headers, cells)))
                else:
                    rows.append({str(i): v for i, v in enumerate(cells)})
            tables.append(rows)
    return tables
