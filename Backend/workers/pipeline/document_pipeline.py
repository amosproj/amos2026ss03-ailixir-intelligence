"""
Document processing pipeline — orchestrator.

Called by the Pub/Sub handler in workers/main.py.

Full flow with status updates (frontend polls document status):

  PROCESSING
    ↓ step: downloading
  Download document bytes from GCS
    ↓ step: ocr
  OCR extraction (OpenRouter vision LLM)
    ↓ step: saving_extraction
  Save clean extracted_fields to Firestore (extractions collection)
    ↓ step: building_graph
  Graphiti → entity/relationship extraction → Neo4j knowledge graph
    ↓ step: exporting_cypher
  Generate Cypher script → upload to GCS
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
    update_cypher_uri,
    update_processing_step,
    update_status,
)
from shared.repositories.extractions import save_extraction
from workers.connections.gcs import download_bytes
from workers.connections.graphiti_client import get_graphiti
from workers.pipeline.graph.builder import ingest as graph_ingest
from workers.pipeline.graph.exporter import generate_and_upload as cypher_export
from workers.pipeline.ocr.extractor import extract as ocr_extract

_log = logging.getLogger(__name__)


async def run(*, doc_id: str, uid: str, gcs_uri: str, file_name: str) -> None:
    """
    Process one uploaded document end-to-end.

    Parameters come directly from the Pub/Sub message payload published
    after a document is uploaded to GCS.
    """
    _log.info("pipeline_start doc_id=%s uid=%s", doc_id, uid)
    update_status(doc_id, DocumentStatus.PROCESSING)

    try:
        # ── 1. Download from GCS ──────────────────────────────────────────────
        update_processing_step(doc_id, "downloading")
        image_bytes, mime_type = download_bytes(gcs_uri)
        _log.info("pipeline_downloaded doc_id=%s bytes=%d", doc_id, len(image_bytes))

        # ── 2. OCR extraction ─────────────────────────────────────────────────
        update_processing_step(doc_id, "ocr")
        ocr_data = ocr_extract(image_bytes, mime_type)
        doc_type = ocr_data.get("document_type", "unknown")
        _log.info("pipeline_ocr_done doc_id=%s doc_type=%s", doc_id, doc_type)

        # ── 3. Save extraction to Firestore (private, clean) ──────────────────
        update_processing_step(doc_id, "saving_extraction")
        save_extraction(
            Extraction(
                doc_id=doc_id,
                uid=uid,
                document_type=doc_type,
                confidence_score=ocr_data.get("confidence_score"),
                extracted_fields=ocr_data.get("extracted_fields", {}),
                extracted_at=datetime.now(timezone.utc),
            )
        )

        # ── 4. Build knowledge graph ──────────────────────────────────────────
        update_processing_step(doc_id, "building_graph")
        graphiti = await get_graphiti()
        episode_name = await graph_ingest(
            graphiti,
            doc_id=doc_id,
            file_name=file_name,
            doc_type=doc_type,
            ocr_data=ocr_data,
        )

        # ── 5. Export Cypher → GCS ────────────────────────────────────────────
        update_processing_step(doc_id, "exporting_cypher")
        cypher_gcs_uri = cypher_export(episode_name, doc_id, file_name, doc_type)

        # ── 6. Attach cypher link + mark complete ─────────────────────────────
        update_cypher_uri(doc_id, cypher_gcs_uri)
        update_status(doc_id, DocumentStatus.EXTRACTED)
        _log.info("pipeline_done doc_id=%s cypher_gcs=%s", doc_id, cypher_gcs_uri)

    except Exception as exc:
        _log.error("pipeline_failed doc_id=%s error=%s", doc_id, exc, exc_info=True)
        update_status(doc_id, DocumentStatus.FAILED, error=str(exc))
        raise
