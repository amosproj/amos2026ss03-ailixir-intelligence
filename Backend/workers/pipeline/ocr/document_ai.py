"""
Google Cloud Document AI — universal document OCR extractor.

Supports PDFs and images (JPEG, PNG, TIFF, BMP, WebP) through the same
processor. Returns a consistent extraction schema for the rest of the pipeline.

Configure via:
  GCP_PROJECT_ID           — already set by terraform in Cloud Run
  DOCUMENT_AI_LOCATION     — processor region, e.g. "us" or "eu"  (default: us)
  DOCUMENT_AI_PROCESSOR_ID — processor ID from GCP Console

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

# MIME types accepted by Document AI processors.
# GCS may return application/octet-stream; we detect the real type from magic bytes.
_SUPPORTED_MIMES = frozenset({
    "application/pdf",
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/tiff",
    "image/tif",
    "image/bmp",
    "image/webp",
    "image/gif",
})


def extract_document(file_bytes: bytes, mime_type: str) -> dict:
    """
    Run OCR on a PDF or image using Google Cloud Document AI.

    Returns:
      document_type, confidence_score, metadata, extracted_fields, tables,
      raw_text_blocks.

    Raises KeyError if DOCUMENT_AI_PROCESSOR_ID is not set.
    """
    project_id = os.environ["GCP_PROJECT_ID"]
    location = os.getenv("DOCUMENT_AI_LOCATION", "us")
    processor_id = os.environ["DOCUMENT_AI_PROCESSOR_ID"]

    effective_mime = _resolve_mime(file_bytes, mime_type)

    opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    client = documentai.DocumentProcessorServiceClient(client_options=opts)
    name = client.processor_path(project_id, location, processor_id)

    # imageless_mode=True raises Document AI's sync per-call page limit from
    # 15 to 30 pages (and bypasses the rendered-image generation that drives
    # that limit). We only consume `raw_text_blocks` downstream — never the
    # rendered page images — so dropping them is free. Without this flag,
    # any PDF with >15 pages (typical for multi-page pathology reports)
    # fails with InvalidArgument PAGE_LIMIT_EXCEEDED on the very first call.
    #
    # Beyond 30 pages we'd need Document AI's batch_process_documents API,
    # which is async and a much bigger change. Tracked as a follow-up:
    # if we see PAGE_LIMIT_EXCEEDED logs after this fix, the batch path
    # is next.
    result = client.process_document(
        request=documentai.ProcessRequest(
            name=name,
            raw_document=documentai.RawDocument(
                content=file_bytes,
                mime_type=effective_mime,
            ),
            imageless_mode=True,
        )
    )
    doc = result.document

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

    # Entities populated by Form Parser / specialized processors only.
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
        "document_ai_complete mime=%s pages=%d entities=%d confidence=%.3f",
        effective_mime,
        len(doc.pages),
        len(doc.entities),
        confidence or 0.0,
    )

    return {
        "document_type": "document",
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


def _resolve_mime(file_bytes: bytes, declared: str) -> str:
    """Return the best-guess MIME type, correcting GCS metadata gaps via magic bytes."""
    if declared and declared in _SUPPORTED_MIMES:
        return declared
    # PDF: %PDF
    if file_bytes[:4] == b"%PDF":
        return "application/pdf"
    # PNG: \x89PNG\r\n\x1a\n
    if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    # JPEG: \xff\xd8
    if file_bytes[:2] == b"\xff\xd8":
        return "image/jpeg"
    # TIFF: II* or MM
    if file_bytes[:4] in (b"II\x2a\x00", b"MM\x00\x2a"):
        return "image/tiff"
    # BMP: BM
    if file_bytes[:2] == b"BM":
        return "image/bmp"
    # Magic bytes didn't match anything — fall back to pdf rather than passing
    # application/octet-stream (which Document AI always rejects).
    return "application/pdf"


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
