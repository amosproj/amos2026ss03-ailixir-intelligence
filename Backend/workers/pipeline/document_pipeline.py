"""
Document processing pipeline — orchestrator.

Called by the Pub/Sub handler in workers/main.py with the document_id and uid
from the DocumentUploaded event. The pipeline looks up the Document from
Firestore, downloads each uploaded file from GCS, and runs the full pipeline.

Full flow with status updates (frontend polls document status):

  PROCESSING
    ↓ step: downloading
  Download file bytes from GCS_DOCUMENTS_BUCKET
    ↓ step: analyzing
  Gemini multimodal analysis — produces episode_body, document_type, document_date
    ↓ step: saving_extraction
  Save extraction to Firestore (extractions collection)
    ↓ step: building_graph
  Graphiti → fixed medical schema → entity/relationship extraction → Neo4j
    ↓ step: updating_summary
  Update patient journey summary in Firestore (journey_summaries collection)
    ↓ step: exporting_cypher
  Generate Cypher script → upload to GCS_CYPHER_BUCKET
    ↓
  Attach cypher_gcs_uri to Firestore document record
  EXTRACTED

Key improvements over the old OCR pipeline:
  - Gemini multimodal reads PDFs directly — richer, context-aware narratives
  - Fixed medical schema enables entity merging across all patient documents
  - reference_time set to the document's own date (not ingestion time)
  - Journey summary provides context to each new document's extraction
  - Patient ID header anchors all episodes to one Patient node in Neo4j

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
from shared.repositories.journey_summaries import get_summary, upsert_summary
from workers.connections.gcs import download_document
from workers.connections.graphiti_client import get_graphiti
from workers.pipeline.graph.builder import ingest as graph_ingest
from workers.pipeline.graph.exporter import generate_and_upload as cypher_export
from workers.pipeline.llm.extractor import analyze_document, update_journey_summary

_log = logging.getLogger(__name__)


async def run(*, document_id: str, uid: str) -> None:
    """
    Process one uploaded document end-to-end.

    Looks up the Document from Firestore, then for each uploaded file:
    downloads from GCS → Gemini analysis → saves extraction → builds graph
    → updates journey summary → exports Cypher.
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
        # ── 1. Validate uploaded files ─────────────────────────────────────────
        uploaded_files = [f for f in document.files if f.upload_completed_at is not None]
        if not uploaded_files:
            raise ValueError(f"Document {document_id} has no uploaded files to process")

        _log.info(
            "pipeline_files document_id=%s file_count=%d",
            document_id, len(uploaded_files),
        )

        # ── 2. Load patient journey context ────────────────────────────────────
        # The summary of previously processed documents is passed as context to
        # the LLM so it can interpret each new document relative to the patient's
        # known history — producing richer episode bodies.
        journey = get_summary(uid)
        current_summary = journey.summary if journey else ""
        _log.info(
            "pipeline_journey_context uid=%s has_summary=%s doc_count=%d",
            uid,
            bool(current_summary),
            journey.document_count if journey else 0,
        )

        # ── 3. Download + LLM analysis for each file ──────────────────────────
        # Collect per-file episode bodies, then combine them into one unified
        # extraction record and one Graphiti episode for the whole document.
        all_episode_bodies: list[str] = []
        last_extraction: dict = {}
        last_file_name: str = uploaded_files[0].file_name

        for file in uploaded_files:
            update_processing_step(document_id, "downloading")
            file_bytes, _ = download_document(file.gcs_object_path)
            _log.info(
                "pipeline_downloaded document_id=%s file=%s bytes=%d",
                document_id, file.file_name, len(file_bytes),
            )
            if len(file_bytes) < 100:
                raise ValueError(
                    f"File {file.file_name!r} is only {len(file_bytes)} bytes — "
                    "the upload likely sent a URL or metadata instead of the actual file."
                )

            # Gemini multimodal: reads the PDF and produces a rich clinical narrative.
            # The current journey summary is passed as context so the LLM can refer
            # back to previous findings (e.g. "PSA changed from 7.6 to 5.2").
            update_processing_step(document_id, "analyzing")
            extraction = await analyze_document(
                pdf_bytes=file_bytes,
                filename=file.file_name,
                previous_summary=current_summary,
            )

            all_episode_bodies.append(extraction.get("episode_body", ""))
            last_extraction = extraction
            last_file_name = file.file_name

        # ── 4. Aggregate extraction across all files ───────────────────────────
        # For multi-file documents, combine episode bodies with a separator so
        # Graphiti receives the full clinical content in one episode. Document
        # metadata (type, purpose, date) is taken from the last file processed.
        combined_episode_body = "\n\n".join(b for b in all_episode_bodies if b)
        merged_extraction: dict = {
            "document_type":    last_extraction.get("document_type", "Unknown"),
            "document_purpose": last_extraction.get("document_purpose", ""),
            "document_date":    last_extraction.get("document_date"),
            "episode_body":     combined_episode_body,
        }

        # ── 5. Save extraction to Firestore ────────────────────────────────────
        update_processing_step(document_id, "saving_extraction")
        save_extraction(
            Extraction(
                doc_id=document_id,
                uid=uid,
                document_type=merged_extraction["document_type"],
                document_purpose=merged_extraction["document_purpose"],
                document_date=merged_extraction["document_date"],
                episode_body=combined_episode_body,
                extracted_at=datetime.now(timezone.utc),
            )
        )

        # ── 6. Build knowledge graph ───────────────────────────────────────────
        # Fixed medical schema enables cross-document entity merging and temporal
        # fact updates. Patient ID header ensures one consistent Patient node.
        update_processing_step(document_id, "building_graph")
        graphiti = await get_graphiti()
        episode_name = await graph_ingest(
            graphiti,
            uid=uid,
            doc_id=document_id,
            doc_name=last_file_name,
            extraction=merged_extraction,
        )

        # ── 7. Update patient journey summary ──────────────────────────────────
        # Summarise the new document into the running patient narrative. The
        # updated summary becomes context for the next document's LLM call.
        update_processing_step(document_id, "updating_summary")
        new_summary = await update_journey_summary(
            current_summary=current_summary,
            extraction=merged_extraction,
            doc_name=last_file_name,
        )
        upsert_summary(
            uid=uid,
            summary_text=new_summary,
            last_extraction_id=document_id,
        )
        _log.info(
            "pipeline_summary_updated document_id=%s summary_len=%d",
            document_id, len(new_summary),
        )

        # ── 8. Export Cypher → GCS ─────────────────────────────────────────────
        update_processing_step(document_id, "exporting_cypher")
        doc_type = merged_extraction["document_type"]
        cypher_gcs_uri = cypher_export(
            episode_name, document_id, last_file_name, doc_type
        )

        # ── 9. Attach cypher link + mark complete ──────────────────────────────
        update_cypher_uri(document_id, cypher_gcs_uri)
        update_status(document_id, DocumentStatus.EXTRACTED)
        _log.info(
            "pipeline_done document_id=%s cypher_gcs=%s",
            document_id, cypher_gcs_uri,
        )

    except Exception as exc:
        _log.error(
            "pipeline_failed document_id=%s error=%s", document_id, exc, exc_info=True
        )
        update_status(document_id, DocumentStatus.FAILED, error=str(exc))
        raise
