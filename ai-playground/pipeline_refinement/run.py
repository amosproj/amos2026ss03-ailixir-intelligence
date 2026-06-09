"""
Pipeline Refinement — Full End-to-End Document Processor

For each document upload runs:
  1. Load existing patient journey summary from Firestore
  2. Gemini reads PDF → writes clinical narrative (episode_body) + doc metadata
  3. Graphiti ingests episode into Neo4j using the FIXED medical schema
     (Patient, Diagnosis, Medication, LabTest, Procedure, Provider, etc.)
  4. Save extraction + episode name to Firestore (test_extractions/{auto-id})
  5. Gemini updates the concise journey summary
  6. Upsert summary in Firestore (test_summaries/{user_id})

Why the fixed schema matters:
  - Graphiti can merge "Patient-1" from doc 1 with "Patient-1" from doc 5
  - When PSA changes across documents, old facts are expired → temporal graph
  - The knowledge graph builds up correctly over multiple uploads

Usage (from ai-playground/ directory):
    python pipeline_refinement/run.py <path/to/doc.pdf> [user_id]

Process Patient-1 in order to build a rich journey graph:
    python pipeline_refinement/run.py Patient-1/ueberweisungsbrief_e01.pdf  patient_001
    python pipeline_refinement/run.py Patient-1/laborbericht_e02.pdf        patient_001
    python pipeline_refinement/run.py Patient-1/befundbericht_e03.pdf       patient_001
    python pipeline_refinement/run.py Patient-1/pathologiebericht_e04.pdf   patient_001
    python pipeline_refinement/run.py Patient-1/tumorkonferenzprotokoll_e05.pdf patient_001

View the journey graph in Neo4j Browser (http://localhost:7474):
  All facts:     MATCH (n:Entity)-[r]-(m:Entity) WHERE n.group_id = 'patient_001' RETURN n, r, m LIMIT 300
  Current only:  add AND (r.invalid_at IS NULL) to see only non-expired facts
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PLAYGROUND = _HERE.parent
if str(_PLAYGROUND) not in sys.path:
    sys.path.insert(0, str(_PLAYGROUND))

from pipeline_refinement.firestore_store import get_summary, save_extraction, upsert_summary
from pipeline_refinement.graphiti_client import (
    create_graphiti,
    neo4j_current_facts_query,
    neo4j_facts_table_query,
    neo4j_journey_query,
)
from pipeline_refinement.graphiti_ingest import ingest_document_episode
from pipeline_refinement.llm_extractor import analyze_document, update_journey_summary

logging.basicConfig(level=logging.WARNING)

_SEP = "=" * 66


def _load_patient_info() -> dict:
    """
    Load optional patient identity from environment variables.

    These are used to build a fixed header prepended to every Graphiti episode,
    anchoring all documents to one consistent Patient node regardless of how each
    document refers to the patient (abbreviations, titles, name order variations).

    Set before running:
      PATIENT_NAME=<full name>       e.g.  PATIENT_NAME="Hans Schmidt"
      PATIENT_DOB=<YYYY-MM-DD>       e.g.  PATIENT_DOB="1979-03-12"

    Both are optional. If PATIENT_NAME is not set, only the user_id is used as
    the patient anchor (still better than nothing for cross-doc entity merging).
    """
    name = os.getenv("PATIENT_NAME", "").strip()
    dob  = os.getenv("PATIENT_DOB", "").strip()
    return {"name": name, "dob": dob}


async def run(pdf_path: Path, user_id: str) -> None:
    patient_info = _load_patient_info()

    print(f"\n{_SEP}")
    print("  Pipeline Refinement — Full Pipeline")
    print(_SEP)
    print(f"  Document : {pdf_path.name}")
    print(f"  User ID  : {user_id}")
    if patient_info.get("name"):
        print(f"  Patient  : {patient_info['name']}")
    if patient_info.get("dob"):
        print(f"  DOB      : {patient_info['dob']}")
    else:
        print("  Patient  : (set PATIENT_NAME / PATIENT_DOB env vars for stronger entity anchoring)")
    print(f"{_SEP}\n")

    # ── Step 1: Load existing journey summary ─────────────────────────────────
    print("[ 1/6 ]  Loading previous journey summary...")
    summary_doc = get_summary(user_id)
    previous_summary: str = summary_doc.get("summary", "") if summary_doc else ""
    doc_count: int = summary_doc.get("document_count", 0) if summary_doc else 0

    if previous_summary:
        preview = previous_summary[:200] + ("..." if len(previous_summary) > 200 else "")
        print(f"         Found summary ({doc_count} doc(s) so far):")
        print(f"         {preview}")
    else:
        print("         No prior summary — first document for this user.")
    print()

    # ── Step 2: Analyze document with Gemini ──────────────────────────────────
    print("[ 2/6 ]  Sending PDF to Gemini for clinical narrative extraction...")
    pdf_bytes = pdf_path.read_bytes()
    extraction = analyze_document(pdf_bytes, pdf_path.name, previous_summary)

    body = extraction.get("episode_body", "")
    print(f"         Document type   : {extraction.get('document_type', 'unknown')}")
    print(f"         Purpose         : {extraction.get('document_purpose', '')[:110]}")
    print(f"\n         Episode body ({len(body)} chars):")
    for i in range(0, min(len(body), 500), 110):
        print(f"           {body[i:i+110]}")
    if len(body) > 500:
        print(f"           ... (truncated)")
    print()

    # ── Step 3: Graphiti — connect and build indices ───────────────────────────
    print("[ 3/6 ]  Connecting to Graphiti / Neo4j...")
    graphiti = await create_graphiti(build_indices=True)
    print("         Connected. Fixed medical schema ready.")
    print("         (Patient, Diagnosis, Medication, LabTest, Procedure,")
    print("          Provider, PathologyResult, TumorMarker, TreatmentPlan)")
    print()

    # ── Step 4: Ingest episode ────────────────────────────────────────────────
    doc_date_str = extraction.get("document_date") or "not found in document"
    print(f"[ 4/6 ]  Ingesting episode into Neo4j (group_id={user_id}, doc_date={doc_date_str})...")
    episode_name = await ingest_document_episode(
        graphiti,
        user_id=user_id,
        doc_name=pdf_path.name,
        extraction=extraction,
        patient_info=patient_info,
    )
    await graphiti.close()
    print(f"         Episode ingested → '{episode_name}'")
    print()

    # ── Step 5: Save extraction to Firestore ──────────────────────────────────
    print("[ 5/6 ]  Saving to Firestore (test_extractions)...")
    extraction_id = save_extraction(user_id, pdf_path.name, extraction, episode_name)
    print(f"         Saved → test_extractions/{extraction_id}")
    print()

    # ── Step 6: Update journey summary ───────────────────────────────────────
    print("[ 6/6 ]  Updating journey summary (test_summaries)...")
    updated_summary = update_journey_summary(previous_summary, extraction, pdf_path.name)
    upsert_summary(user_id, updated_summary, extraction_id)
    print(f"         Saved → test_summaries/{user_id}")
    print(f"\n         Updated summary:")
    for sentence in updated_summary.replace(". ", ".\n").strip().split("\n"):
        if sentence.strip():
            print(f"           {sentence.strip()}")
    print()

    # ── Done ──────────────────────────────────────────────────────────────────
    print(_SEP)
    print("  DONE")
    print(f"  Neo4j episode  : {episode_name}")
    print(f"  Firestore doc  : test_extractions/{extraction_id}")
    print(f"  Summary        : test_summaries/{user_id}")
    print()
    print("  View journey in Neo4j Browser → http://localhost:7474")
    print()
    print("  [Graph view] Entity graph — all facts:")
    print(f"    {neo4j_journey_query(user_id)}")
    print()
    print("  [Graph view] Current facts only (hides expired/superseded):")
    print(f"    {neo4j_current_facts_query(user_id)}")
    print()
    print("  [Table view] Readable relation list (source → relation → target):")
    print(f"    {neo4j_facts_table_query(user_id)}")
    print()
    print("  TIP: Edge labels show numbers by default.")
    print("       Paint bucket icon → Relationships → Caption → set to 'name'")
    print(_SEP)

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
    asyncio.run(run(_path, _user_id))
