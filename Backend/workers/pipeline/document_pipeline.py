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
        # Collect per-file extractions, then aggregate into one extraction
        # record and one Graphiti episode for the whole document.
        per_file_extractions: list[dict] = []
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

            # Gemini multimodal: reads the document and produces a rich clinical
            # narrative. The current journey summary is passed as context so the
            # LLM can refer back to previous findings (e.g. "PSA changed from X to Y").
            # mime_type from file.content_type (validated by the API at upload time)
            # is forwarded so Gemini receives the correct format hint.
            update_processing_step(document_id, "analyzing")
            extraction = await analyze_document(
                file_bytes=file_bytes,
                filename=file.file_name,
                mime_type=file.content_type,
                previous_summary=current_summary,
            )

            per_file_extractions.append(extraction)
            last_file_name = file.file_name

        # ── 4. Aggregate extraction across all files ───────────────────────────
        # Single-file case: pass-through. Multi-file case: combine without
        # silently dropping per-file metadata (the old code took only the
        # *last* file's type/purpose/date, which broke when a user uploaded
        # e.g. lab report + imaging report + referral as one document).
        merged_extraction = _aggregate_extractions(per_file_extractions)

        # ── 5. Save extraction to Firestore ────────────────────────────────────
        update_processing_step(document_id, "saving_extraction")
        save_extraction(
            Extraction(
                doc_id=document_id,
                uid=uid,
                document_type=merged_extraction["document_type"],
                document_purpose=merged_extraction["document_purpose"],
                document_date=merged_extraction["document_date"],
                episode_body=merged_extraction["episode_body"],
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

        # ── 7. Update patient journey summary (best-effort) ────────────────────
        # The extraction record is saved and the knowledge graph is built. The
        # journey summary is *context for the NEXT document's analysis*, not
        # output a user sees on this one. If the LLM call here fails (Vertex
        # hiccup, MAX_TOKENS, safety filter), we DO NOT mark this document
        # FAILED — that would invalidate work the user can already see in the
        # graph and on the OCR/narrative card. We log loudly so the failure
        # is visible to ops, but the document still reaches EXTRACTED.
        #
        # Downside accepted: the next document for this user will be analysed
        # against the previous summary, missing this document's contribution.
        # That's recoverable on the next successful summary update.
        update_processing_step(document_id, "updating_summary")
        try:
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
        except Exception as summary_exc:
            # Log with full traceback so it shows up in Cloud Logging at WARNING
            # severity. WARNING (not ERROR) because the document IS extracted;
            # only the next-doc-context is degraded.
            _log.warning(
                "pipeline_summary_update_failed_nonfatal document_id=%s err=%s",
                document_id, summary_exc, exc_info=True,
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _aggregate_extractions(per_file: list[dict]) -> dict:
    """Combine per-file LLM extractions into one record for the whole document.

    Single-file: pass-through with the canonical key shape.

    Multi-file: applies deterministic rules so two unrelated files attached to
    the same document (e.g. lab report + imaging report bundled by the user)
    don't silently lose one file's metadata to the other.

      document_type    — first non-empty / non-"Unknown" value across files
      document_purpose — concatenation in upload order, deduplicated, "; " joined
      document_date    — earliest non-null date across files (medical context:
                         the document's earliest signal is the most clinically
                         meaningful anchor for temporal ordering)
      episode_body     — concatenation in upload order, separated by blank lines
                         so Graphiti sees one continuous narrative
    """
    if not per_file:
        return {
            "document_type":    "Unknown",
            "document_purpose": "",
            "document_date":    None,
            "episode_body":     "",
        }

    if len(per_file) == 1:
        e = per_file[0]
        return {
            "document_type":    e.get("document_type") or "Unknown",
            "document_purpose": e.get("document_purpose") or "",
            "document_date":    e.get("document_date"),
            "episode_body":     e.get("episode_body") or "",
        }

    # Multi-file aggregation.
    def _first_meaningful(values, *, generic=("", "Unknown", "unknown", None)):
        for v in values:
            if v not in generic:
                return v
        return values[0] if values else None

    doc_type = _first_meaningful([e.get("document_type") for e in per_file]) or "Unknown"

    # Preserve purpose order, drop duplicates, drop empties.
    purposes_seen: set[str] = set()
    purposes_ordered: list[str] = []
    for e in per_file:
        p = (e.get("document_purpose") or "").strip()
        if p and p not in purposes_seen:
            purposes_seen.add(p)
            purposes_ordered.append(p)
    doc_purpose = "; ".join(purposes_ordered)

    # Earliest non-null date wins. Compare as strings; ISO/YYYY-MM-DD sorts
    # correctly lexicographically, and non-ISO dates compare safely vs each
    # other (consistency, not correctness) — the per-file LLM is prompted to
    # emit ISO, so non-ISO is an edge case we tolerate without ranking.
    dates = [e.get("document_date") for e in per_file if e.get("document_date")]
    doc_date = min(dates) if dates else None

    episode_body = "\n\n".join(
        (e.get("episode_body") or "").strip() for e in per_file
        if (e.get("episode_body") or "").strip()
    )

    return {
        "document_type":    doc_type,
        "document_purpose": doc_purpose,
        "document_date":    doc_date,
        "episode_body":     episode_body,
    }
