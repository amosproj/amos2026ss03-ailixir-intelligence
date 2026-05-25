"""
test_pipeline.py — Local smoke test for OCR + Graphiti components.

Reads a local PDF/image, runs it through Document AI OCR, then feeds the
result into Graphiti for knowledge-graph extraction. No GCS, Firestore,
or Pub/Sub involved.

Run from the Backend/ directory:
    python test_pipeline.py [path/to/file.pdf]

Defaults to AIlixir_Test_MRT_Befund.pdf if no argument is given.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent


# ── helpers ───────────────────────────────────────────────────────────────────

def _header(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def _check_env() -> None:
    required = [
        "GCP_PROJECT_ID",
        "DOCUMENT_AI_PROCESSOR_ID",
        "VERTEX_PROJECT",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
    ]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print("ERROR: missing required environment variables:")
        for v in missing:
            print(f"  {v}")
        sys.exit(1)


# ── step 1: OCR ───────────────────────────────────────────────────────────────

def run_ocr(file_path: Path) -> dict:
    _header("STEP 1 — Document AI OCR")
    print(f"File : {file_path.name}")
    print(f"Size : {file_path.stat().st_size:,} bytes")

    file_bytes = file_path.read_bytes()
    mime_type = "application/pdf" if file_path.suffix.lower() == ".pdf" else "image/jpeg"

    from workers.pipeline.ocr.document_ai import extract_document
    result = extract_document(file_bytes, mime_type)

    print(f"\ndocument_type    : {result['document_type']}")
    print(f"confidence_score : {result['confidence_score']}")
    print(f"page_count       : {result['metadata'].get('page_count', 'n/a')}")
    print(f"extracted_fields : {len(result['extracted_fields'])} entries")
    print(f"tables           : {len(result['tables'])}")
    print(f"raw_text_blocks  : {len(result['raw_text_blocks'])} page(s)")

    if result["extracted_fields"]:
        print("\n── extracted_fields ──")
        print(json.dumps(result["extracted_fields"], indent=2, ensure_ascii=False))

    if result["raw_text_blocks"]:
        preview = "\n".join(result["raw_text_blocks"])[:800]
        print(f"\n── raw text preview ──\n{preview}")
        if sum(len(b) for b in result["raw_text_blocks"]) > 800:
            print("  ... [truncated]")

    print("\n✓ OCR passed")
    return result


# ── step 2: Graphiti ──────────────────────────────────────────────────────────

async def run_graphiti(ocr_result: dict, file_name: str) -> None:
    _header("STEP 2 — Graphiti knowledge-graph extraction")

    from workers.connections.graphiti_client import close_graphiti, get_graphiti
    from workers.pipeline.graph.builder import ingest

    print("Connecting to Neo4j + initialising Graphiti indices …")
    graphiti = await get_graphiti()
    print("✓ connected")

    doc_id = "test_doc_local_001"
    print(f"\nIngesting episode  doc_id={doc_id}  file={file_name} …")

    episode_name = await ingest(
        graphiti,
        doc_id=doc_id,
        file_name=file_name,
        doc_type=ocr_result.get("document_type", "document"),
        ocr_data=ocr_result,
    )

    print(f"✓ episode ingested: {episode_name}")
    await close_graphiti()


# ── main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    # Resolve file path
    if len(sys.argv) > 1:
        file_path = Path(sys.argv[1])
        if not file_path.is_absolute():
            file_path = BACKEND_DIR / file_path
    else:
        file_path = BACKEND_DIR / "AIlixir_Test_MRT_Befund.pdf"

    if not file_path.exists():
        print(f"ERROR: file not found: {file_path}")
        sys.exit(1)

    _check_env()

    # Run steps
    ocr_result = run_ocr(file_path)
    await run_graphiti(ocr_result, file_path.name)

    _header("ALL STEPS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
