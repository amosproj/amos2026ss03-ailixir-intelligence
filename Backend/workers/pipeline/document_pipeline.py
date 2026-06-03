"""
Document processing pipeline — orchestrator.

Called by the Pub/Sub handler in workers/main.py with the document_id and uid
from the DocumentUploaded event. The pipeline looks up the Document from
Firestore, downloads each uploaded file from GCS, and runs the full pipeline.

Full flow with status updates (frontend polls document status):

  PROCESSING
    ↓ step: downloading
  Download file bytes from GCS_DOCUMENTS_BUCKET
    ↓ step: ocr
  OCR extraction (OpenRouter vision LLM) per file
    ↓ step: saving_extraction
  Save clean extracted_fields to Firestore (extractions collection)
    ↓ step: building_graph
  Graphiti → entity/relationship extraction → Neo4j knowledge graph
    ↓ step: exporting_cypher
  Generate Cypher script → upload to GCS_CYPHER_BUCKET
    ↓
  Attach cypher_gcs_uri to Firestore document record
  EXTRACTED

Any exception → FAILED (error message recorded in Firestore).
Pub/Sub retries on any non-2xx response from the worker endpoint.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from shared.models.document import DocumentStatus
from shared.models.extraction import Extraction
from shared.repositories.documents import (
    find_document_for_user,
    update_cypher_uri,
    update_processing_step,
    update_status,
)
from shared.repositories.extractions import save_extraction
from workers.connections.gcs import download_document
from workers.connections.graphiti_client import get_graphiti
from workers.pipeline.graph.builder import ingest as graph_ingest
from workers.pipeline.graph.exporter import generate_and_upload as cypher_export
from workers.pipeline.ocr.extractor import extract as ocr_extract

_log = logging.getLogger(__name__)

# Cap on raw OCR text sent into Graphiti's episode body. Graphiti issues one
# Gemini "resolve_extracted_node" call per candidate entity in the body — a
# 5k-char German clinical report yields 30+ candidates and bursts past the
# Vertex AI Gemini rate limit (currently ~200 RPM project-wide). Capping the
# input keeps the candidate count low enough that the burst stays under
# quota. The proper fix is configuring Graphiti with an `entity_types`
# schema (planned migration from ai-playground/pipeline_refinement) which
# constrains extraction to a defined set rather than free-form candidates.
_MAX_OCR_CHARS_FOR_GRAPH = 2500


async def run(*, document_id: str, uid: str) -> None:
    """
    Process one uploaded document end-to-end.

    Looks up the Document from Firestore, then for each uploaded file:
    downloads from GCS → OCR → saves extraction → builds graph → exports Cypher.
    """
    _log.info("pipeline_start document_id=%s uid=%s", document_id, uid)

    # ── 0. Dedup: skip if a prior delivery already claimed this document ───────
    # Pub/Sub is at-least-once; a duplicate delivery would re-run all LLM calls.
    document = find_document_for_user(document_id, uid)
    if document is None:
        _log.warning("pipeline_skip_not_found document_id=%s uid=%s", document_id, uid)
        return
    if document.status in (DocumentStatus.PROCESSING, DocumentStatus.EXTRACTED):
        _log.warning(
            "pipeline_skip_duplicate document_id=%s status=%s",
            document_id, document.status.value,
        )
        return

    update_status(document_id, DocumentStatus.PROCESSING)

    try:
        # ── 1. Validate uploaded files (document already fetched above) ────────
        uploaded_files = [f for f in document.files if f.upload_completed_at is not None]
        if not uploaded_files:
            raise ValueError(f"Document {document_id} has no uploaded files to process")

        _log.info(
            "pipeline_files document_id=%s file_count=%d",
            document_id, len(uploaded_files),
        )

        # ── 2. Process each file ──────────────────────────────────────────────
        # Collect OCR results across all files then build one unified graph.
        #
        # Two distinct payloads accumulate here:
        #
        #   combined_fields    — the structured key/value pairs `extracted_fields`
        #                        emits. Populated only by Form Parser / specialised
        #                        Document AI processors; empty for the basic
        #                        Document OCR processor we use today.
        #
        #   combined_raw_blocks— the per-page raw text Document OCR returns. THIS
        #                        is where the actual document content lives for
        #                        the OCR processor type. Dropping it (as we did
        #                        before this fix) meant Gemini received only the
        #                        filename in the episode body — every graph
        #                        collapsed to a single Entity with summary
        #                        'This document is from file <name>.pdf'.
        #
        # Both flow into the Graphiti episode body via build_episode_body() so
        # Gemini has actual content to extract entities from.
        combined_fields: dict = {}
        combined_raw_blocks: list[str] = []
        combined_tables: list = []
        doc_type = "unknown"
        confidence: float | None = None
        last_file_name = uploaded_files[0].file_name

        for file in uploaded_files:
            # Download — use the content_type declared at upload time (validated by the
            # API), not the GCS blob metadata (often application/octet-stream when the
            # client omits the Content-Type header during the presigned PUT).
            update_processing_step(document_id, "downloading")
            file_bytes, _ = download_document(file.gcs_object_path)
            mime_type = file.content_type
            _log.info(
                "pipeline_downloaded document_id=%s file=%s mime=%s bytes=%d",
                document_id, file.file_name, mime_type, len(file_bytes),
            )
            if len(file_bytes) < 100:
                raise ValueError(
                    f"File {file.file_name!r} is only {len(file_bytes)} bytes — "
                    "the upload likely sent a URL or metadata instead of the actual file."
                )

            # OCR — routed by mime_type: PDF → Document AI, image → OpenRouter
            update_processing_step(document_id, "ocr")
            ocr_data = ocr_extract(file_bytes, mime_type)
            doc_type = ocr_data.get("document_type", doc_type)
            confidence = ocr_data.get("confidence_score", confidence)
            last_file_name = file.file_name

            # Structured fields (Form Parser shape)
            file_fields = ocr_data.get("extracted_fields", {}) or {}
            if len(uploaded_files) == 1:
                combined_fields = file_fields
            else:
                combined_fields[file.file_name] = file_fields

            # Raw OCR text — where the actual content is for the Document OCR processor.
            # Cap accumulation: see _MAX_OCR_CHARS_FOR_GRAPH note. Once the budget
            # is exhausted we stop appending new blocks (rather than truncating
            # mid-block, which would split a German word and confuse Gemini).
            current_chars = sum(len(b) for b in combined_raw_blocks)
            for block in ocr_data.get("raw_text_blocks", []) or []:
                if not (block and isinstance(block, str) and block.strip()):
                    continue
                if current_chars >= _MAX_OCR_CHARS_FOR_GRAPH:
                    break
                cleaned = block.strip()
                combined_raw_blocks.append(cleaned)
                current_chars += len(cleaned)

            # Tables — secondary content source
            for table in ocr_data.get("tables", []) or []:
                if table:
                    combined_tables.append(table)

        _log.info(
            "pipeline_ocr_done document_id=%s doc_type=%s "
            "raw_blocks=%d raw_chars=%d tables=%d structured_keys=%d cap=%d",
            document_id, doc_type,
            len(combined_raw_blocks),
            sum(len(b) for b in combined_raw_blocks),
            len(combined_tables), len(combined_fields),
            _MAX_OCR_CHARS_FOR_GRAPH,
        )

        # ── 3. Save extraction to Firestore ───────────────────────────────────
        update_processing_step(document_id, "saving_extraction")
        save_extraction(
            Extraction(
                doc_id=document_id,
                uid=uid,
                document_type=doc_type,
                confidence_score=confidence,
                extracted_fields=combined_fields,
                extracted_at=datetime.now(timezone.utc),
            )
        )

        # ── 4. Build knowledge graph ──────────────────────────────────────────
        update_processing_step(document_id, "building_graph")
        graphiti = await get_graphiti()

        # The merged_ocr dict goes into build_episode_body() — every key here
        # is a content source the prompt template knows how to render. Missing
        # any of them means Gemini gets a thinner prompt and produces a thinner
        # graph.
        merged_ocr = {
            "document_type": doc_type,
            "confidence_score": confidence,
            "extracted_fields": combined_fields,
            "raw_text_blocks": combined_raw_blocks,
            "tables": combined_tables,
        }
        episode_name = await graph_ingest(
            graphiti,
            doc_id=document_id,
            file_name=last_file_name,
            doc_type=doc_type,
            ocr_data=merged_ocr,
        )

        # ── 5. Export Cypher → GCS ────────────────────────────────────────────
        update_processing_step(document_id, "exporting_cypher")
        cypher_gcs_uri = cypher_export(
            episode_name, document_id, last_file_name, doc_type
        )

        # ── 6. Attach cypher link + mark complete ─────────────────────────────
        update_cypher_uri(document_id, cypher_gcs_uri)
        update_status(document_id, DocumentStatus.EXTRACTED)
        _log.info(
            "pipeline_done document_id=%s cypher_gcs=%s", document_id, cypher_gcs_uri
        )

    except Exception as exc:
        _log.error(
            "pipeline_failed document_id=%s error=%s", document_id, exc, exc_info=True
        )
        update_status(document_id, DocumentStatus.FAILED, error=str(exc))
        raise
