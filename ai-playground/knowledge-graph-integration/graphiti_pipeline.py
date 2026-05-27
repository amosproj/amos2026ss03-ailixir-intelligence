"""
Full Document-to-Knowledge-Graph Pipeline (Graphiti) — Patient Edition
=======================================================================
Changes from original:
  - Patient identity (name, DOB, MRN) injected into every episode header
    so Graphiti always extracts one consistent Patient anchor entity.
  - group_id = patient MRN → all episodes for one patient share a namespace,
    enabling cross-document entity deduplication and temporal merging.
  - reference_time = document date extracted from OCR (falls back to now),
    so the temporal graph reflects the real medical timeline.
  - Patient info collected once at startup (or via env / CLI args).

Flow:
  1. Collect patient identity (MRN, name, DOB)
  2. Read images from ../Images/  (or custom path)
  3. OCR each image via OpenRouter
  4. Prepend patient header to episode text
  5. Feed to Graphiti with group_id=MRN and reference_time=doc_date
  6. Export PNG / Cypher / JSON per document + one combined patient JSON

Usage:
    python graphiti_pipeline.py
    python graphiti_pipeline.py path/to/image.jpg
    python graphiti_pipeline.py path/to/folder/

    # Supply patient info via env to skip prompts:
    PATIENT_MRN=10042 PATIENT_NAME="Hans Schmidt" PATIENT_DOB="1979-03-12" \
        python graphiti_pipeline.py

Requirements:
    OPENAI_API_KEY, OPENROUTER_API_KEY
    NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.parse
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx
from neo4j import GraphDatabase
from dotenv import load_dotenv

# ── Environment ───────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_PLAYGROUND = _HERE.parent

load_dotenv(dotenv_path=_HERE / ".env")
load_dotenv(dotenv_path=_PLAYGROUND / ".env")

sys.path.insert(0, str(_PLAYGROUND / "document-extraction"))

# ── Imports ───────────────────────────────────────────────────────────────────
try:
    from ocr_service import call_openrouter, collect_images
except ImportError as e:
    print(f"❌  Cannot import OCR service: {e}")
    sys.exit(1)

try:
    from graphiti_core import Graphiti
    from graphiti_core.nodes import EpisodeType
    from graphiti_core.llm_client.openai_client import OpenAIClient
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
except ImportError as e:
    print(f"❌  Cannot import graphiti_core: {e}")
    print("    pip install graphiti-core")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "your_secure_password")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
IMAGE_DIR      = _PLAYGROUND / "Images"


# ── Patient identity helpers ──────────────────────────────────────────────────

def _prompt(label: str, env_key: str, required: bool = True) -> str:
    """Read from env first; fall back to interactive prompt."""
    val = os.getenv(env_key, "").strip()
    if val:
        return val
    while True:
        val = input(f"  {label}: ").strip()
        if val or not required:
            return val
        print(f"    ⚠  {label} is required.")


def collect_patient_info() -> dict:
    """
    Gather patient identity once per run.
    Returns a dict with keys: mrn, name, dob (str or empty).
    """
    print("\n── Patient Identity ─────────────────────────────────────────")
    print("  (Set PATIENT_MRN / PATIENT_NAME / PATIENT_DOB env vars to skip)\n")
    mrn  = _prompt("Patient MRN (unique ID)", "PATIENT_MRN", required=True)
    name = _prompt("Patient full name",        "PATIENT_NAME", required=True)
    dob  = _prompt("Date of birth (YYYY-MM-DD, optional)", "PATIENT_DOB", required=False)
    print()
    return {"mrn": mrn, "name": name, "dob": dob}


def _patient_header(patient: dict) -> str:
    """
    Build the fixed anchor sentence prepended to every episode.
    This ensures Graphiti always extracts ONE Patient entity with
    a consistent name, regardless of how the document refers to the person.
    """
    parts = [f"Patient: {patient['name']}", f"MRN: {patient['mrn']}"]
    if patient.get("dob"):
        parts.append(f"DOB: {patient['dob']}")
    return ", ".join(parts) + ".\n"


# ── Document date extraction ──────────────────────────────────────────────────

def _parse_doc_date(ocr_data: dict) -> datetime:
    """
    Try to extract the document's real date from OCR metadata so that
    reference_time reflects the actual medical timeline, not just now().

    Falls back to UTC now if no date is found or parseable.
    """
    raw = (
        ocr_data.get("metadata", {}).get("date_detected")
        or ocr_data.get("extracted_fields", {}).get("date")
        or ocr_data.get("extracted_fields", {}).get("document_date")
        or ocr_data.get("extracted_fields", {}).get("report_date")
        or ocr_data.get("extracted_fields", {}).get("visit_date")
    )
    if not raw:
        return datetime.now(timezone.utc)

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y", "%B %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(str(raw).strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return datetime.now(timezone.utc)


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def run_pipeline(image_source: str | None = None) -> None:
    """Main pipeline: collect patient → OCR → Graphiti episodes → Neo4j."""

    if not OPENAI_API_KEY:
        print("❌  OPENAI_API_KEY is not set.")
        sys.exit(1)

    # ── Collect patient identity ──────────────────────────────────────────────
    patient = collect_patient_info()

    print("\n" + "=" * 60)
    print("  Graphiti Patient Pipeline")
    print("=" * 60)
    print(f"  Patient : {patient['name']}  (MRN: {patient['mrn']})")
    print(f"  Neo4j   : {NEO4J_URI}")
    print(f"  Images  : {image_source or IMAGE_DIR}")
    print("=" * 60 + "\n")

    # ── Init Graphiti ─────────────────────────────────────────────────────────
    llm_client = OpenAIClient(config=LLMConfig(api_key=OPENAI_API_KEY))
    embedder   = OpenAIEmbedder(config=OpenAIEmbedderConfig(api_key=OPENAI_API_KEY))

    graphiti = Graphiti(
        NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
        llm_client=llm_client,
        embedder=embedder,
    )

    graph_out_dir = _HERE / "graph_outputs"
    graph_out_dir.mkdir(exist_ok=True)

    print("Building Neo4j indices (first run only)...")
    await graphiti.build_indices_and_constraints()
    print("Indices ready.\n")

    # ── Collect images ────────────────────────────────────────────────────────
    images = collect_images(image_source)
    if not images:
        print("❌  No images found.")
        await graphiti.close()
        return

    print(f"Found {len(images)} image(s) to process.\n")

    results: list[dict] = []

    for idx, img_path in enumerate(images, start=1):
        print(f"[{idx}/{len(images)}]  {img_path.name}")
        print("-" * 50)

        # ── Step 1: OCR ───────────────────────────────────────────────────────
        print("  Step 1/2  OCR via OpenRouter...")
        try:
            ocr_result = call_openrouter(img_path)
        except Exception as exc:
            print(f"  ✗ OCR exception: {exc}\n")
            results.append({"file": img_path.name, "status": "ocr_error", "error": str(exc)})
            continue

        if not ocr_result["success"]:
            print(f"  ✗ OCR returned invalid JSON\n")
            results.append({"file": img_path.name, "status": "ocr_failed"})
            continue

        ocr_data: dict = ocr_result["extracted_data"]
        doc_type   = ocr_data.get("document_type", "unknown")
        confidence = ocr_data.get("confidence_score", "n/a")
        tokens     = ocr_result.get("tokens_used", {})
        print(f"  ✓ OCR done  doc_type={doc_type}  confidence={confidence}  tokens={tokens}")

        # ── Step 2: Build episode with patient header ─────────────────────────
        print("  Step 2/5  Graphiti entity extraction → Neo4j...")

        # Real document date for temporal accuracy
        doc_date = _parse_doc_date(ocr_data)

        episode_name = (
            f"mrn{patient['mrn']}_{img_path.stem}_"
            f"{doc_date.strftime('%Y%m%d_%H%M%S')}"
        )

        # Patient header anchors every episode to the same Patient entity
        episode_body = (
            _patient_header(patient)
            + _build_episode_text(img_path.name, ocr_data)
        )

        try:
            await graphiti.add_episode(
                name=episode_name,
                episode_body=episode_body,
                source=EpisodeType.text,
                source_description=(
                    f"Medical document — file: {img_path.name}, "
                    f"type: {doc_type}, patient MRN: {patient['mrn']}"
                ),
                # KEY CHANGE 1: all docs for this patient share a namespace
                group_id=patient["mrn"],
                # KEY CHANGE 2: real document date drives the temporal graph
                reference_time=doc_date,
            )
            print(f"  ✓ Episode '{episode_name}' stored")
            print(f"  ✓ group_id={patient['mrn']}  reference_time={doc_date.date()}")

            browser_link = neo4j_browser_link(episode_name)
            patient_link = neo4j_patient_link(patient["mrn"])
            print(f"  🔗 This doc   → {browser_link}")
            print(f"  🔗 Full graph → {patient_link}")

            stem = img_path.stem

            # ── Step 3: PNG ───────────────────────────────────────────────────
            print("  Step 3/5  Rendering knowledge graph PNG...")
            png_path = graph_out_dir / f"{stem}_graph.png"
            try:
                save_graph_png(episode_name, png_path)
                print(f"  ✓ PNG  → {png_path.name}")
            except Exception as exc:
                print(f"  ⚠  PNG failed: {exc}")
                png_path = None

            # ── Step 4: Cypher ────────────────────────────────────────────────
            print("  Step 4/5  Exporting Cypher script...")
            cypher_path = graph_out_dir / f"{stem}_graph.cypher"
            try:
                save_graph_cypher(episode_name, img_path.name, doc_type, cypher_path)
                print(f"  ✓ Cypher → {cypher_path.name}")
            except Exception as exc:
                print(f"  ⚠  Cypher export failed: {exc}")
                cypher_path = None

            # ── Step 5: JSON ──────────────────────────────────────────────────
            print("  Step 5/5  Exporting graph JSON...")
            json_path = graph_out_dir / f"{stem}_graph.json"
            try:
                save_graph_json(episode_name, img_path.name, doc_type, json_path)
                print(f"  ✓ JSON  → {json_path.name}\n")
            except Exception as exc:
                print(f"  ⚠  JSON export failed: {exc}\n")
                json_path = None

            results.append({
                "file": img_path.name,
                "status": "ok",
                "episode": episode_name,
                "doc_type": doc_type,
                "doc_date": doc_date.isoformat(),
                "group_id": patient["mrn"],
                "outputs": {
                    "png":    str(png_path)    if png_path    else None,
                    "cypher": str(cypher_path) if cypher_path else None,
                    "json":   str(json_path)   if json_path   else None,
                },
                "browser_link": browser_link,
            })
        except Exception as exc:
            print(f"  ✗ Graphiti error: {exc}\n")
            results.append({"file": img_path.name, "status": "graphiti_error", "error": str(exc)})

    await graphiti.close()

    # ── Combined patient JSON export ──────────────────────────────────────────
    ok_results = [r for r in results if r["status"] == "ok"]
    if ok_results:
        patient_json_path = graph_out_dir / f"patient_{patient['mrn']}_full_graph.json"
        try:
            save_patient_graph_json(patient, ok_results, patient_json_path)
            print(f"\n  ✓ Combined patient graph → {patient_json_path.name}")
        except Exception as exc:
            print(f"\n  ⚠  Combined patient JSON failed: {exc}")

    # ── Summary ───────────────────────────────────────────────────────────────
    ok_count = len(ok_results)
    print("\n" + "=" * 60)
    print(f"  Done: {ok_count}/{len(images)} documents ingested")
    print(f"  Patient graph (Neo4j) → {neo4j_patient_link(patient['mrn'])}")
    print()
    for r in results:
        if r["status"] != "ok":
            print(f"    {r['file']}  ✗ {r['status']}")
            continue
        outs = r.get("outputs", {})
        print(f"    {r['file']}  ({r.get('doc_date', '')[:10]})")
        for k, v in outs.items():
            if v:
                print(f"      {k.upper():6} → {Path(v).name}")
    print("=" * 60)

    summary_path = _HERE / "pipeline_run.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_at":            datetime.now(timezone.utc).isoformat(),
            "neo4j_uri":         NEO4J_URI,
            "patient":           patient,
            "images_processed":  len(images),
            "success_count":     ok_count,
            "results":           results,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n  Run summary → {summary_path}\n")


# ── Neo4j Browser link generators ────────────────────────────────────────────

def neo4j_browser_link(episode_name: str) -> str:
    cypher = (
        f"MATCH (ep:Episodic {{name:'{episode_name}'}})-[r*1..2]-(n) "
        f"RETURN ep, r, n"
    )
    return f"http://localhost:7474/browser/?cmd=edit&arg={urllib.parse.quote(cypher, safe='')}"


def neo4j_patient_link(mrn: str) -> str:
    """
    Browser link that shows the FULL knowledge graph for one patient
    across ALL their documents (uses group_id).
    """
    cypher = (
        f"MATCH (ep:Episodic {{group_id:'{mrn}'}})-[r*1..2]-(n) "
        f"RETURN ep, r, n"
    )
    return f"http://localhost:7474/browser/?cmd=edit&arg={urllib.parse.quote(cypher, safe='')}"


# ── Knowledge graph PNG ───────────────────────────────────────────────────────

_LABEL_COLOURS: dict[str, str] = {
    "Entity":       "#4A90D9",
    "Person":       "#E67E22",
    "Organization": "#27AE60",
    "Location":     "#8E44AD",
    "Date":         "#E74C3C",
    "Episodic":     "#95A5A6",
}
_DEFAULT_COLOUR = "#BDC3C7"


def save_graph_png(episode_name: str, output_path: Path) -> None:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    G = nx.DiGraph()
    node_labels:  dict[str, str]   = {}
    node_colours: dict[str, str]   = {}
    edge_labels:  dict[tuple, str] = {}

    with driver.session() as session:
        node_result = session.run("""
            MATCH (n) WHERE NOT n:Episodic
            RETURN elementId(n) AS nid, labels(n) AS lbls,
                   coalesce(n.name, n.uuid, elementId(n)) AS display
            LIMIT 200
        """)
        for rec in node_result:
            nid = rec["nid"]
            lbls: list[str] = rec["lbls"] or []
            G.add_node(nid)
            node_labels[nid] = str(rec["display"])[:30]
            colour = next((_LABEL_COLOURS[l] for l in lbls if l in _LABEL_COLOURS), _DEFAULT_COLOUR)
            node_colours[nid] = colour

        rel_result = session.run("""
            MATCH (a)-[r]->(b) WHERE NOT a:Episodic AND NOT b:Episodic
            RETURN elementId(a) AS src, elementId(b) AS tgt, type(r) AS rtype
            LIMIT 300
        """)
        for rec in rel_result:
            src, tgt, rtype = rec["src"], rec["tgt"], rec["rtype"]
            if G.has_node(src) and G.has_node(tgt):
                G.add_edge(src, tgt)
                edge_labels[(src, tgt)] = rtype or ""

    driver.close()

    if G.number_of_nodes() == 0:
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No entities extracted yet",
                ha="center", va="center", fontsize=14, color="gray")
        ax.axis("off")
        plt.savefig(output_path, dpi=120, bbox_inches="tight")
        plt.close()
        return

    fig, ax = plt.subplots(figsize=(18, 12))
    fig.patch.set_facecolor("#1A1A2E")
    ax.set_facecolor("#1A1A2E")
    pos = nx.spring_layout(G, seed=42, k=2.5)
    colours = [node_colours.get(n, _DEFAULT_COLOUR) for n in G.nodes()]
    nx.draw_networkx_nodes(G, pos, node_color=colours, node_size=1800, alpha=0.92, ax=ax)
    nx.draw_networkx_labels(G, pos, labels=node_labels, font_size=7, font_color="white", ax=ax)
    nx.draw_networkx_edges(G, pos, edge_color="#AAAAAA", arrows=True, arrowsize=15,
                           width=1.2, connectionstyle="arc3,rad=0.1", ax=ax)
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels,
                                 font_size=6, font_color="#DDDDDD", ax=ax)
    legend_handles = [mpatches.Patch(color=c, label=lbl) for lbl, c in _LABEL_COLOURS.items()]
    ax.legend(handles=legend_handles, loc="upper left",
              facecolor="#2C2C54", labelcolor="white", fontsize=8)
    ax.set_title(f"Knowledge Graph — {episode_name}", color="white", fontsize=11, pad=12)
    ax.axis("off")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()


# ── Shared Neo4j query helper ─────────────────────────────────────────────────

def _fetch_episode_graph(episode_name: str) -> tuple[list[dict], list[dict]]:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    nodes_out: list[dict] = []
    edges_out: list[dict] = []
    seen_node_ids: set[str] = set()
    seen_edge_keys: set[tuple] = set()

    with driver.session() as session:
        node_rows = session.run("""
            MATCH (ep:Episodic {name: $name})-[*0..2]-(n)
            WHERE NOT n:Episodic
            RETURN DISTINCT elementId(n) AS eid, labels(n) AS lbls, properties(n) AS props
            LIMIT 300
        """, name=episode_name)

        for row in node_rows:
            eid = row["eid"]
            if eid in seen_node_ids:
                continue
            seen_node_ids.add(eid)
            props: dict = dict(row["props"])
            lbls:  list[str] = list(row["lbls"])
            nodes_out.append({
                "id":         props.get("uuid", eid),
                "element_id": eid,
                "labels":     lbls,
                "type":       next((l for l in lbls if l != "Entity"), lbls[0] if lbls else "Entity"),
                "name":       str(props.get("name") or props.get("uuid") or eid),
                "properties": {k: v for k, v in props.items()
                               if k not in {"embedding"} and v is not None},
            })

        if seen_node_ids:
            rel_rows = session.run("""
                MATCH (a)-[r]->(b)
                WHERE NOT a:Episodic AND NOT b:Episodic
                  AND elementId(a) IN $ids AND elementId(b) IN $ids
                RETURN DISTINCT elementId(r) AS reid, elementId(a) AS src,
                       elementId(b) AS tgt, type(r) AS rtype, properties(r) AS props
                LIMIT 500
            """, ids=list(seen_node_ids))

            eid_to_uuid = {n["element_id"]: n["id"] for n in nodes_out}
            for row in rel_rows:
                key = (row["src"], row["tgt"], row["rtype"])
                if key in seen_edge_keys:
                    continue
                seen_edge_keys.add(key)
                rprops = {k: v for k, v in dict(row["props"]).items()
                          if k not in {"embedding"} and v is not None}
                edges_out.append({
                    "id":     row["reid"],
                    "source": eid_to_uuid.get(row["src"], row["src"]),
                    "target": eid_to_uuid.get(row["tgt"], row["tgt"]),
                    "type":   row["rtype"],
                    "label":  row["rtype"].lower().replace("_", " "),
                    "properties": rprops,
                })

    driver.close()
    return nodes_out, edges_out


def _fetch_patient_graph(mrn: str) -> tuple[list[dict], list[dict]]:
    """
    Pull the FULL merged graph for a patient across all episodes
    that share group_id = mrn.
    """
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    nodes_out: list[dict] = []
    edges_out: list[dict] = []
    seen_node_ids: set[str] = set()
    seen_edge_keys: set[tuple] = set()

    with driver.session() as session:
        node_rows = session.run("""
            MATCH (ep:Episodic {group_id: $mrn})-[*0..2]-(n)
            WHERE NOT n:Episodic
            RETURN DISTINCT elementId(n) AS eid, labels(n) AS lbls, properties(n) AS props
            LIMIT 1000
        """, mrn=mrn)

        for row in node_rows:
            eid = row["eid"]
            if eid in seen_node_ids:
                continue
            seen_node_ids.add(eid)
            props: dict = dict(row["props"])
            lbls:  list[str] = list(row["lbls"])
            nodes_out.append({
                "id":         props.get("uuid", eid),
                "element_id": eid,
                "labels":     lbls,
                "type":       next((l for l in lbls if l != "Entity"), lbls[0] if lbls else "Entity"),
                "name":       str(props.get("name") or props.get("uuid") or eid),
                "properties": {k: v for k, v in props.items()
                               if k not in {"embedding"} and v is not None},
            })

        if seen_node_ids:
            rel_rows = session.run("""
                MATCH (a)-[r]->(b)
                WHERE NOT a:Episodic AND NOT b:Episodic
                  AND elementId(a) IN $ids AND elementId(b) IN $ids
                RETURN DISTINCT elementId(r) AS reid, elementId(a) AS src,
                       elementId(b) AS tgt, type(r) AS rtype, properties(r) AS props
                LIMIT 2000
            """, ids=list(seen_node_ids))

            eid_to_uuid = {n["element_id"]: n["id"] for n in nodes_out}
            for row in rel_rows:
                key = (row["src"], row["tgt"], row["rtype"])
                if key in seen_edge_keys:
                    continue
                seen_edge_keys.add(key)
                rprops = {k: v for k, v in dict(row["props"]).items()
                          if k not in {"embedding"} and v is not None}
                edges_out.append({
                    "id":     row["reid"],
                    "source": eid_to_uuid.get(row["src"], row["src"]),
                    "target": eid_to_uuid.get(row["tgt"], row["tgt"]),
                    "type":   row["rtype"],
                    "label":  row["rtype"].lower().replace("_", " "),
                    "properties": rprops,
                })

    driver.close()
    return nodes_out, edges_out


# ── Cypher export ─────────────────────────────────────────────────────────────

def save_graph_cypher(episode_name: str, img_name: str, doc_type: str, output_path: Path) -> None:
    nodes, edges = _fetch_episode_graph(episode_name)
    lines: list[str] = [
        f"// ── Knowledge Graph Export ───────────────────────────────────",
        f"// Source image : {img_name}",
        f"// Document type: {doc_type}",
        f"// Episode      : {episode_name}",
        f"// Generated    : {datetime.now(timezone.utc).isoformat()}",
        "", "// ── Nodes ──────────────────────────────────────────────────────",
    ]
    for n in nodes:
        uuid = n["id"]
        lbls = ":".join(n["labels"]) if n["labels"] else "Entity"
        safe_props = _cypher_props({**n["properties"], "uuid": uuid, "name": n["name"]})
        lines.append(f"MERGE (n_{_safe_var(uuid)}:{lbls} {{uuid: {_cypher_str(uuid)}}})")
        lines.append(f"  SET n_{_safe_var(uuid)} += {safe_props};")
        lines.append("")
    lines += ["", "// ── Relationships ───────────────────────────────────────────────"]
    for e in edges:
        src_var  = _safe_var(e["source"])
        tgt_var  = _safe_var(e["target"])
        rel_type = e["type"].upper().replace(" ", "_")
        rprops   = _cypher_props(e["properties"]) if e["properties"] else "{}"
        lines.append(
            f'MATCH (n_{src_var} {{uuid: {_cypher_str(e["source"])}}}), '
            f'(n_{tgt_var} {{uuid: {_cypher_str(e["target"])}}})'
        )
        lines.append(f"MERGE (n_{src_var})-[:{rel_type} {rprops}]->(n_{tgt_var});")
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _safe_var(uid: str) -> str:
    return "n" + "".join(c if c.isalnum() else "_" for c in uid)[:24]


def _cypher_str(value: object) -> str:
    return "'" + str(value).replace("'", "\\'") + "'"


def _cypher_props(props: dict) -> str:
    if not props:
        return "{}"
    pairs = []
    for k, v in props.items():
        safe_key = k if k.isidentifier() else f"`{k}`"
        if isinstance(v, bool):
            pairs.append(f"{safe_key}: {str(v).lower()}")
        elif isinstance(v, (int, float)):
            pairs.append(f"{safe_key}: {v}")
        elif isinstance(v, list):
            inner = ", ".join(_cypher_str(x) for x in v)
            pairs.append(f"{safe_key}: [{inner}]")
        else:
            pairs.append(f"{safe_key}: {_cypher_str(v)}")
    return "{" + ", ".join(pairs) + "}"


# ── JSON exports ──────────────────────────────────────────────────────────────

_STRIP_PROPS = {
    "embedding", "name_embedding", "summary_embedding",
    "group_id", "uuid", "created_at", "expired_at",
    "valid_at", "invalid_at", "source_episode_names",
    "episodes", "element_id",
}


def _clean_nodes_edges(raw_nodes: list[dict], raw_edges: list[dict]) -> tuple[list, list]:
    clean_nodes = []
    for n in raw_nodes:
        user_props = {
            k: v for k, v in n.get("properties", {}).items()
            if k not in _STRIP_PROPS
            and not k.endswith("_embedding")
            and not isinstance(v, list)
        }
        clean_nodes.append({
            "id":   n["id"],
            "name": n["name"],
            "type": n["type"],
            **( {"summary": n["properties"]["summary"]}
                if "summary" in n.get("properties", {}) else {} ),
            **user_props,
        })
    clean_edges = [
        {"source": e["source"], "target": e["target"],
         "type": e["type"], "label": e["label"]}
        for e in raw_edges
    ]
    return clean_nodes, clean_edges


def save_graph_json(episode_name: str, img_name: str, doc_type: str, output_path: Path) -> None:
    raw_nodes, raw_edges = _fetch_episode_graph(episode_name)
    clean_nodes, clean_edges = _clean_nodes_edges(raw_nodes, raw_edges)
    payload = {
        "meta": {
            "source_image": img_name,
            "episode_name": episode_name,
            "doc_type":     doc_type,
            "exported_at":  datetime.now(timezone.utc).isoformat(),
            "node_count":   len(clean_nodes),
            "edge_count":   len(clean_edges),
            "browser_link": neo4j_browser_link(episode_name),
        },
        "nodes": clean_nodes,
        "edges": clean_edges,
    }
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )


def save_patient_graph_json(
    patient: dict, ok_results: list[dict], output_path: Path
) -> None:
    """
    Export the FULL merged knowledge graph for this patient across
    all documents processed in this run. Compatible with D3/Cytoscape/React Flow.
    """
    mrn = patient["mrn"]
    raw_nodes, raw_edges = _fetch_patient_graph(mrn)
    clean_nodes, clean_edges = _clean_nodes_edges(raw_nodes, raw_edges)

    payload = {
        "meta": {
            "patient_name":     patient["name"],
            "patient_mrn":      mrn,
            "patient_dob":      patient.get("dob", ""),
            "exported_at":      datetime.now(timezone.utc).isoformat(),
            "documents_in_run": [r["file"] for r in ok_results],
            "doc_dates":        [r.get("doc_date", "")[:10] for r in ok_results],
            "node_count":       len(clean_nodes),
            "edge_count":       len(clean_edges),
            "patient_browser_link": neo4j_patient_link(mrn),
        },
        "nodes": clean_nodes,
        "edges": clean_edges,
    }
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )


# ── Episode text builder ──────────────────────────────────────────────────────

def _build_episode_text(filename: str, ocr_data: dict) -> str:
    lines: list[str] = []
    doc_type = ocr_data.get("document_type", "document")
    lines.append(f"This is a {doc_type} named '{filename}'.")

    meta = ocr_data.get("metadata", {})
    if meta.get("date_detected"):
        lines.append(f"Document date: {meta['date_detected']}.")
    if meta.get("language"):
        lines.append(f"Language: {meta['language']}.")

    confidence = ocr_data.get("confidence_score")
    if confidence is not None:
        lines.append(f"OCR confidence: {confidence}.")

    extracted = ocr_data.get("extracted_fields", {})
    if extracted:
        lines.append("\nExtracted information:")
        lines.extend(_flatten_to_sentences(extracted))

    tables = ocr_data.get("tables", [])
    if tables:
        lines.append("\nTabular data:")
        for i, table in enumerate(tables, start=1):
            lines.append(f"Table {i}:")
            if isinstance(table, list):
                for row in table:
                    lines.append("  " + _row_to_str(row))
            elif isinstance(table, dict):
                for k, v in table.items():
                    lines.append(f"  {k}: {v}")

    raw_blocks = ocr_data.get("raw_text_blocks", [])
    if raw_blocks:
        lines.append("\nRaw text from document:")
        lines.extend(str(b) for b in raw_blocks if b)

    return "\n".join(lines)


def _flatten_to_sentences(d: dict, prefix: str = "") -> list[str]:
    out: list[str] = []
    for k, v in d.items():
        label = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.extend(_flatten_to_sentences(v, label))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    out.extend(_flatten_to_sentences(item, f"{label}[{i}]"))
                elif item is not None:
                    out.append(f"  {label}[{i}]: {item}")
        elif v is not None:
            out.append(f"  {label}: {v}")
    return out


def _row_to_str(row: dict | list | str | object) -> str:
    if isinstance(row, dict):
        return " | ".join(f"{k}: {v}" for k, v in row.items())
    if isinstance(row, list):
        return " | ".join(str(x) for x in row)
    return str(row)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _source = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(run_pipeline(_source))