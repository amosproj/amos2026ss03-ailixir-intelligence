"""
Pipeline Refinement — Document Analyzer CLI

Processes a medical PDF through:
  1. Loads the existing patient journey summary from Firestore (if any)
  2. Sends PDF + summary to Gemini → produces:
       episode_body  — rich narrative paragraph (what Graphiti will read)
       entity_types  — Pydantic-compatible type definitions
       edge_types    — relationship class definitions
       edge_type_map — valid source/target/relation constraints
  3. Saves everything as a NEW document in Firestore: test_extractions/{auto-id}
  4. Sends episode_body to Gemini → updated concise journey summary
  5. Upserts summary in Firestore: test_summaries/{user_id}

Usage (from ai-playground/ directory):
    python pipeline_refinement/run.py <path/to/doc.pdf> [user_id]

Examples — process Patient-1 in order to build up journey context:
    python pipeline_refinement/run.py Patient-1/ueberweisungsbrief_e01.pdf  patient_001
    python pipeline_refinement/run.py Patient-1/laborbericht_e02.pdf        patient_001
    python pipeline_refinement/run.py Patient-1/befundbericht_e03.pdf       patient_001
    python pipeline_refinement/run.py Patient-1/pathologiebericht_e04.pdf   patient_001
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ── Path setup so `pipeline_refinement` is importable as a package ────────────
_HERE = Path(__file__).resolve().parent     # …/pipeline_refinement/
_PLAYGROUND = _HERE.parent                  # …/ai-playground/
if str(_PLAYGROUND) not in sys.path:
    sys.path.insert(0, str(_PLAYGROUND))

from pipeline_refinement.firestore_store import get_summary, save_extraction, upsert_summary
from pipeline_refinement.llm_extractor import analyze_document, build_graphiti_types, update_journey_summary


def run(pdf_path: Path, user_id: str) -> None:
    sep = "=" * 64
    print(f"\n{sep}")
    print("  Pipeline Refinement — Document Analyzer")
    print(sep)
    print(f"  Document : {pdf_path.name}")
    print(f"  User ID  : {user_id}")
    print(f"{sep}\n")

    # ── Step 1: Load existing journey summary ─────────────────────────────────
    print("[ 1/4 ]  Loading previous journey summary...")
    summary_doc = get_summary(user_id)
    previous_summary: str = summary_doc.get("summary", "") if summary_doc else ""
    doc_count: int = summary_doc.get("document_count", 0) if summary_doc else 0

    if previous_summary:
        preview = previous_summary[:200] + ("..." if len(previous_summary) > 200 else "")
        print(f"         Found summary ({doc_count} doc(s) processed so far):")
        print(f"         {preview}")
    else:
        print("         No prior summary — this is the first document for this user.")
    print()

    # ── Step 2: Analyze document with Gemini ──────────────────────────────────
    print("[ 2/4 ]  Sending PDF to Gemini...")
    pdf_bytes = pdf_path.read_bytes()
    extraction = analyze_document(pdf_bytes, pdf_path.name, previous_summary)

    entity_names = [e["name"] for e in extraction.get("entity_types", [])]
    edge_names   = [e["name"] for e in extraction.get("edge_types", [])]

    print(f"         Document type    : {extraction.get('document_type', 'unknown')}")
    print(f"         Purpose          : {extraction.get('document_purpose', '')[:110]}")
    print(f"         Entity types     : {entity_names}")
    print(f"         Edge types       : {edge_names}")
    print(f"         Edge type rules  : {len(extraction.get('edge_type_map', []))}")
    print()
    print("         Episode body (narrative for Graphiti):")
    body = extraction.get("episode_body", "")
    # Print in wrapped chunks of ~100 chars
    for i in range(0, min(len(body), 600), 100):
        print(f"           {body[i:i+100]}")
    if len(body) > 600:
        print(f"           ... ({len(body)} chars total)")
    print()

    # ── Build Pydantic types (shown here for verification, used later by Graphiti) ──
    entity_types, edge_types, edge_type_map = build_graphiti_types(extraction)
    print(f"         Pydantic models built: {list(entity_types.keys())}")
    print(f"         Edge models built    : {list(edge_types.keys())}")
    print()

    # ── Step 3: Save extraction to Firestore ──────────────────────────────────
    print("[ 3/4 ]  Saving to Firestore (test_extractions)...")
    extraction_id = save_extraction(user_id, pdf_path.name, extraction)
    print(f"         Saved → test_extractions/{extraction_id}")
    print()

    # ── Step 4: Update journey summary ───────────────────────────────────────
    print("[ 4/4 ]  Updating journey summary (test_summaries)...")
    updated_summary = update_journey_summary(previous_summary, extraction, pdf_path.name)
    upsert_summary(user_id, updated_summary, extraction_id)
    print(f"         Saved → test_summaries/{user_id}")
    print(f"\n         Updated summary:")
    for sentence in updated_summary.replace(". ", ".\n").strip().split("\n"):
        if sentence.strip():
            print(f"           {sentence.strip()}")
    print()

    # ── Result summary ────────────────────────────────────────────────────────
    print(sep)
    print("  DONE")
    print(f"  Extraction  → test_extractions/{extraction_id}")
    print(f"  Summary     → test_summaries/{user_id}")
    print(sep)

    print("\nFull extraction JSON:\n")
    print(json.dumps(extraction, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    _path = Path(sys.argv[1])
    if not _path.is_absolute():
        _path = Path.cwd() / _path
    _path = _path.resolve()

    if not _path.is_file():
        print(f"Error: file not found: {_path}")
        sys.exit(1)
    if _path.suffix.lower() != ".pdf":
        print(f"Error: expected a .pdf file, got '{_path.suffix}'")
        sys.exit(1)

    _user_id = sys.argv[2] if len(sys.argv) > 2 else "test_patient_001"
    run(_path, _user_id)
