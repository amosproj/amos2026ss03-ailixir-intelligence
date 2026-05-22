"""
Full Document-to-Knowledge-Graph Pipeline (Graphiti)
======================================================
Flow:
  1. Read images from ../Images/
  2. OCR each image via OpenRouter (document-extraction service)
  3. Feed structured JSON → Graphiti → entity/relationship extraction via OpenAI
  4. Store temporal knowledge graph in Neo4j

Usage:
    python graphiti_pipeline.py                     # all images in ../Images/
    python graphiti_pipeline.py path/to/image.jpg   # single image
    python graphiti_pipeline.py path/to/folder/     # custom folder

Requirements:
    OPENAI_API_KEY       — used by Graphiti for LLM + embeddings
    OPENROUTER_API_KEY   — used by OCR service for vision extraction
    NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD — Neo4j connection
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend (no display needed)
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx
from neo4j import GraphDatabase
from dotenv import load_dotenv

# ── Environment ──────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_PLAYGROUND = _HERE.parent

# Load .env: local first, then ai-playground root
load_dotenv(dotenv_path=_HERE / ".env")
load_dotenv(dotenv_path=_PLAYGROUND / ".env")

# Add document-extraction folder to path (folder name has a hyphen, so direct import)
sys.path.insert(0, str(_PLAYGROUND / "document-extraction"))

# ── Imports ───────────────────────────────────────────────────────────────────
try:
    from ocr_service import call_openrouter, collect_images  # noqa: E402
except ImportError as e:
    print(f"❌  Cannot import OCR service: {e}")
    print(f"    Expected: {_PLAYGROUND / 'document-extraction' / 'ocr_service.py'}")
    sys.exit(1)

try:
    from graphiti_core import Graphiti
    from graphiti_core.nodes import EpisodeType
    from graphiti_core.llm_client.openai_client import OpenAIClient
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
except ImportError as e:
    print(f"❌  Cannot import graphiti_core: {e}")
    print("    Install with:  pip install graphiti-core")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "your_secure_password")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
IMAGE_DIR = _PLAYGROUND / "Images"


# ── Pipeline ──────────────────────────────────────────────────────────────────

async def run_pipeline(image_source: str | None = None) -> None:
    """Main pipeline: OCR → Graphiti episodes → Neo4j knowledge graph."""

    if not OPENAI_API_KEY:
        print("❌  OPENAI_API_KEY is not set.")
        print("    Export it:  $env:OPENAI_API_KEY='sk-...'   (PowerShell)")
        print("    or add to:  ai-playground/full_pipeline/.env")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  Graphiti Document Pipeline")
    print("=" * 60)
    print(f"  Neo4j  : {NEO4J_URI}")
    print(f"  Images : {image_source or IMAGE_DIR}")
    print("=" * 60 + "\n")

    # ── Init Graphiti ─────────────────────────────────────────────────────────
    llm_client = OpenAIClient(
        config=LLMConfig(api_key=OPENAI_API_KEY)
    )
    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(api_key=OPENAI_API_KEY)
    )

    graphiti = Graphiti(
        NEO4J_URI,
        NEO4J_USER,
        NEO4J_PASSWORD,
        llm_client=llm_client,
        embedder=embedder,
    )

    # Output folder for PNG files
    graph_out_dir = _HERE / "graph_outputs"
    graph_out_dir.mkdir(exist_ok=True)

    # Build vector + fulltext indices once (idempotent)
    print("Building Neo4j indices (first run only)...")
    await graphiti.build_indices_and_constraints()
    print("Indices ready.\n")

    # ── Collect images ────────────────────────────────────────────────────────
    images = collect_images(image_source)
    if not images:
        print("❌  No images found. Check IMAGE_DIR or pass a path as argument.")
        await graphiti.close()
        return

    print(f"Found {len(images)} image(s) to process.\n")

    results: list[dict] = []

    for idx, img_path in enumerate(images, start=1):
        print(f"[{idx}/{len(images)}]  {img_path.name}")
        print("-" * 50)

        # ── Step 1: OCR extraction ────────────────────────────────────────
        print("  Step 1/2  OCR via OpenRouter...")
        try:
            ocr_result = call_openrouter(img_path)
        except Exception as exc:
            print(f"  ✗ OCR exception: {exc}\n")
            results.append({"file": img_path.name, "status": "ocr_error", "error": str(exc)})
            continue

        if not ocr_result["success"]:
            raw_err = ocr_result.get("extracted_data", {})
            print(f"  ✗ OCR returned invalid JSON: {raw_err}\n")
            results.append({"file": img_path.name, "status": "ocr_failed"})
            continue

        ocr_data: dict = ocr_result["extracted_data"]
        doc_type = ocr_data.get("document_type", "unknown")
        confidence = ocr_data.get("confidence_score", "n/a")
        tokens = ocr_result.get("tokens_used", {})
        print(f"  ✓ OCR done  doc_type={doc_type}  confidence={confidence}  tokens={tokens}")

        # ── Step 2: Add to Graphiti ───────────────────────────────────────
        print("  Step 2/3  Graphiti entity extraction → Neo4j...")

        episode_name = f"{img_path.stem}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        episode_body = _build_episode_text(img_path.name, ocr_data)

        try:
            await graphiti.add_episode(
                name=episode_name,
                episode_body=episode_body,
                source=EpisodeType.text,
                source_description=(
                    f"Document OCR extraction — file: {img_path.name}, type: {doc_type}"
                ),
                reference_time=datetime.now(timezone.utc),
            )
            print(f"  ✓ Episode '{episode_name}' stored in Neo4j")

            # Browser link for this document's subgraph
            browser_link = neo4j_browser_link(episode_name)
            print(f"  🔗 Neo4j Browser → {browser_link}")

            # ── Step 3: Export knowledge graph as PNG ─────────────────────
            print("  Step 3/3  Rendering knowledge graph PNG...")
            png_path = graph_out_dir / f"{img_path.stem}_graph.png"
            try:
                save_graph_png(episode_name, png_path)
                print(f"  ✓ Graph PNG → {png_path}\n")
            except Exception as exc:
                print(f"  ⚠  PNG generation failed: {exc}\n")
                png_path = None

            results.append({
                "file": img_path.name,
                "status": "ok",
                "episode": episode_name,
                "doc_type": doc_type,
                "graph_png": str(png_path) if png_path else None,
                "browser_link": browser_link,
            })
        except Exception as exc:
            print(f"  ✗ Graphiti error: {exc}\n")
            results.append({"file": img_path.name, "status": "graphiti_error", "error": str(exc)})

    await graphiti.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    ok_count = sum(1 for r in results if r["status"] == "ok")
    print("=" * 60)
    print(f"  Done: {ok_count}/{len(images)} images ingested successfully")
    print(f"  Neo4j browser (full graph) : http://localhost:7474")
    print()
    print("  Per-document links (open in browser, then click Run):")
    for r in results:
        if r.get("browser_link"):
            print(f"    {r['file']}")
            print(f"      {r['browser_link']}")
    print("=" * 60)

    summary_path = _HERE / "pipeline_run.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "run_at": datetime.now(timezone.utc).isoformat(),
                "neo4j_uri": NEO4J_URI,
                "images_processed": len(images),
                "success_count": ok_count,
                "results": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\n  Run summary → {summary_path}\n")


# ── Neo4j Browser link generator ─────────────────────────────────────────────

def neo4j_browser_link(episode_name: str) -> str:
    """
    Return a localhost Neo4j Browser URL with a Cypher query pre-filled
    for the given episode. Clicking the link opens the graph instantly.
    """
    cypher = (
        f"MATCH (ep:Episodic {{name:'{episode_name}'}})-[r*1..2]-(n) "
        f"RETURN ep, r, n"
    )
    encoded = urllib.parse.quote(cypher, safe="")
    return f"http://localhost:7474/browser/?cmd=edit&arg={encoded}"


# ── Knowledge graph PNG export ───────────────────────────────────────────────

# Node colour per label type (Graphiti uses these label names)
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
    """
    Query Neo4j for all entity nodes and relationships, build a networkx DiGraph,
    and save a labelled PNG. The episode that was just added is highlighted.
    """
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    G = nx.DiGraph()
    node_labels: dict[str, str] = {}   # node_id → display label
    node_colours: dict[str, str] = {}  # node_id → colour
    edge_labels: dict[tuple, str] = {} # (src, tgt) → rel type

    with driver.session() as session:
        # Pull entity nodes (skip raw Episodic metadata nodes for clarity)
        node_result = session.run("""
            MATCH (n)
            WHERE NOT n:Episodic
            RETURN
                elementId(n)  AS nid,
                labels(n)     AS lbls,
                coalesce(n.name, n.uuid, elementId(n)) AS display
            LIMIT 200
        """)
        for rec in node_result:
            nid = rec["nid"]
            lbls: list[str] = rec["lbls"] or []
            display: str = str(rec["display"])
            G.add_node(nid)
            node_labels[nid] = display[:30]  # truncate long names
            colour = _DEFAULT_COLOUR
            for lbl in lbls:
                if lbl in _LABEL_COLOURS:
                    colour = _LABEL_COLOURS[lbl]
                    break
            node_colours[nid] = colour

        # Pull relationships
        rel_result = session.run("""
            MATCH (a)-[r]->(b)
            WHERE NOT a:Episodic AND NOT b:Episodic
            RETURN
                elementId(a) AS src,
                elementId(b) AS tgt,
                type(r)      AS rtype
            LIMIT 300
        """)
        for rec in rel_result:
            src, tgt, rtype = rec["src"], rec["tgt"], rec["rtype"]
            if G.has_node(src) and G.has_node(tgt):
                G.add_edge(src, tgt)
                edge_labels[(src, tgt)] = rtype or ""

    driver.close()

    if G.number_of_nodes() == 0:
        # Nothing to draw yet — create a placeholder
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.text(0.5, 0.5, "No entities extracted yet", ha="center", va="center",
                fontsize=14, color="gray")
        ax.axis("off")
        plt.savefig(output_path, dpi=120, bbox_inches="tight")
        plt.close()
        return

    fig, ax = plt.subplots(figsize=(18, 12))
    fig.patch.set_facecolor("#1A1A2E")
    ax.set_facecolor("#1A1A2E")

    pos = nx.spring_layout(G, seed=42, k=2.5)

    colours = [node_colours.get(n, _DEFAULT_COLOUR) for n in G.nodes()]
    nx.draw_networkx_nodes(G, pos, node_color=colours, node_size=1800,
                           alpha=0.92, ax=ax)
    nx.draw_networkx_labels(G, pos, labels=node_labels, font_size=7,
                            font_color="white", ax=ax)
    nx.draw_networkx_edges(G, pos, edge_color="#AAAAAA", arrows=True,
                           arrowsize=15, width=1.2,
                           connectionstyle="arc3,rad=0.1", ax=ax)
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels,
                                 font_size=6, font_color="#DDDDDD", ax=ax)

    # Legend
    legend_handles = [
        mpatches.Patch(color=c, label=lbl)
        for lbl, c in _LABEL_COLOURS.items()
    ]
    ax.legend(handles=legend_handles, loc="upper left",
              facecolor="#2C2C54", labelcolor="white", fontsize=8)

    ax.set_title(f"Knowledge Graph — {episode_name}", color="white", fontsize=11, pad=12)
    ax.axis("off")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()


# ── Episode text builder ──────────────────────────────────────────────────────

def _build_episode_text(filename: str, ocr_data: dict) -> str:
    """
    Convert OCR JSON → natural language text so Graphiti's LLM can extract
    entities and relationships accurately.
    """
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
    """Recursively produce 'key: value' lines from a nested dict."""
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
