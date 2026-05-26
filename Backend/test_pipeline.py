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

async def run_graphiti(ocr_result: dict, file_name: str) -> str:
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
    return episode_name


# ── step 3: Cypher export ────────────────────────────────────────────────────

def run_cypher(episode_name: str, file_name: str) -> None:
    _header("STEP 3 — Cypher export (paste into Neo4j Browser)")

    from workers.pipeline.graph.exporter import _query_episode_graph, _render_cypher  # noqa: PLC2701

    # The exporter's get_driver() uses a default session; override the database
    # via NEO4J_DATABASE so it works on AuraDB instances with non-default names.
    import os
    from neo4j import GraphDatabase

    uri = os.environ["NEO4J_URI"]
    driver = GraphDatabase.driver(
        uri, auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"])
    )
    database = os.environ.get("NEO4J_DATABASE", "neo4j")

    nodes: list = []
    edges: list = []

    from workers.pipeline.graph.exporter import _clean, _render_cypher  # noqa: PLC2701

    with driver.session(database=database) as session:
        node_rows = session.run(
            """
            MATCH (ep:Episodic {name: $name})-[*0..2]-(n)
            WHERE NOT n:Episodic
            RETURN DISTINCT elementId(n) AS eid, labels(n) AS lbls, properties(n) AS props
            LIMIT 300
            """,
            name=episode_name,
        )
        seen_nodes: set = set()
        for row in node_rows:
            eid = row["eid"]
            if eid in seen_nodes:
                continue
            seen_nodes.add(eid)
            raw = dict(row["props"])
            uuid = raw.get("uuid", eid)
            nodes.append({"uuid": uuid, "eid": eid, "labels": list(row["lbls"]),
                          "name": str(raw.get("name") or uuid), "props": _clean(raw)})

        if seen_nodes:
            eid_to_uuid = {n["eid"]: n["uuid"] for n in nodes}
            seen_edges: set = set()
            rel_rows = session.run(
                """
                MATCH (a)-[r]->(b)
                WHERE NOT a:Episodic AND NOT b:Episodic
                  AND elementId(a) IN $ids AND elementId(b) IN $ids
                RETURN DISTINCT elementId(a) AS src, elementId(b) AS tgt,
                       type(r) AS rtype, properties(r) AS props
                LIMIT 500
                """,
                ids=list(seen_nodes),
            )
            for row in rel_rows:
                key = (row["src"], row["tgt"], row["rtype"])
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edges.append({"source": eid_to_uuid.get(row["src"], row["src"]),
                              "target": eid_to_uuid.get(row["tgt"], row["tgt"]),
                              "type": row["rtype"],
                              "props": _clean(dict(row["props"]))})

    driver.close()

    cypher = _render_cypher(episode_name, file_name, "document", nodes, edges)
    print(f"\nNodes : {len(nodes)}")
    print(f"Edges : {len(edges)}")

    # ── Visualisation query (paste into Neo4j Browser to SEE the graph) ──────
    print("\n── VISUALISE in Neo4j Browser (copy & paste) ───────────────────")
    print(f"MATCH path = (ep:Episodic {{name: '{episode_name}'}})-[*0..2]-(n)")
    print("RETURN path")
    print("── end ─────────────────────────────────────────────────────────")

    # ── Export Cypher (MERGE statements — what the frontend receives) ────────
    print("\n── EXPORT Cypher (frontend / reconstruct graph elsewhere) ──────")
    print(cypher)
    print("── end ─────────────────────────────────────────────────────────")
    print("\n✓ Done")


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
    episode_name = await run_graphiti(ocr_result, file_path.name)
    run_cypher(episode_name, file_path.name)

    _header("ALL STEPS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
