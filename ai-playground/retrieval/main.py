"""
CLI entry point for the Graphiti retrieval + QA pipeline.

Default mode: full QA (retrieval → Gemini answer).
Use --retrieve-only to skip the LLM and inspect raw facts.

Usage (run from ai-playground/ directory):

    # Full pipeline — retrieve facts then get Gemini answer (default)
    python -m retrieval.main "What medications is the patient on?" --user-id patient_001

    # Retrieve only — inspect raw facts without LLM answering
    python -m retrieval.main "PSA levels" --user-id patient_001 --retrieve-only

    # Current facts only (exclude superseded/expired data)
    python -m retrieval.main "diagnoses" --user-id patient_001 --current-only

    # Filter by entity or relationship type
    python -m retrieval.main "lab results" --user-id patient_001 \\
        --entity-types LabTest TumorMarker

    # JSON output (good for piping into other tools)
    python -m retrieval.main "treatment" --user-id patient_001 --format json

    # Change max retrieved facts (default: 4)
    python -m retrieval.main "history" --user-id patient_001 --num-results 6

Output formats (--format, only relevant with --retrieve-only):
    context  — Full formatted context string
    facts    — Only edges/facts (compact)
    entities — Only entity nodes
    json     — Raw JSON of edges + nodes
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from retrieval.pipeline import QAOutput, RetrievalOutput, run_qa, run_retrieval

# Silence noisy library loggers so pipeline output is clean
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s  %(name)s  %(message)s",
)
logging.getLogger("retrieval").setLevel(logging.INFO)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m retrieval.main",
        description=(
            "Query a patient's Graphiti knowledge graph and get a Gemini-powered answer."
        ),
    )
    parser.add_argument(
        "query",
        help="Natural-language query (e.g. 'What medications is this patient on?')",
    )
    parser.add_argument(
        "--user-id",
        required=True,
        metavar="UID",
        help="Patient user ID (Firebase UID or test ID like 'patient_001').",
    )
    parser.add_argument(
        "--num-results",
        type=int,
        default=4,
        metavar="N",
        help="Max facts/entities to retrieve (default: 4). Graph facts are dense.",
    )
    parser.add_argument(
        "--entity-types",
        nargs="+",
        metavar="TYPE",
        help=(
            "Restrict node search to specific medical entity types. "
            "E.g.: --entity-types Medication Diagnosis LabTest Patient"
        ),
    )
    parser.add_argument(
        "--edge-types",
        nargs="+",
        metavar="TYPE",
        help=(
            "Restrict edge search to specific relationship types. "
            "E.g.: --edge-types PRESCRIBED HAS_DIAGNOSIS HAD_LAB_TEST"
        ),
    )
    parser.add_argument(
        "--current-only",
        action="store_true",
        default=False,
        help="Return only current (non-expired) facts. Hides superseded data.",
    )
    parser.add_argument(
        "--retrieve-only",
        action="store_true",
        default=False,
        help="Skip Gemini answering. Just show retrieved facts and entities.",
    )
    parser.add_argument(
        "--format",
        choices=["context", "facts", "entities", "json"],
        default="context",
        help="Output format for --retrieve-only mode (default: context).",
    )
    return parser.parse_args()


# ── Print helpers ─────────────────────────────────────────────────────────────

def _print_answer(result: QAOutput) -> None:
    sep = "=" * 60
    print(f"\n{sep}")
    print("ANSWER")
    print(sep)
    print(result.answer)
    print(f"\n{sep}")
    print(
        f"Based on {result.retrieval.total_edges} fact(s) and "
        f"{result.retrieval.total_nodes} entity/entities retrieved from "
        f"the knowledge graph."
    )
    print(sep)


def _print_retrieval_context(output: RetrievalOutput) -> None:
    print(output.context)


def _print_facts(output: RetrievalOutput) -> None:
    print(f"\nFACTS ({output.total_edges}) — query: {output.query!r}")
    print(f"User: {output.user_id}\n")
    if not output.edges:
        print("No facts found.")
        return
    for i, edge in enumerate(output.edges, start=1):
        status = "current" if edge.invalid_at is None else f"expired {edge.invalid_at.date()}"
        date   = edge.valid_at.date() if edge.valid_at else "unknown"
        print(f"[{i}] {edge.name}  ({date} → {status})")
        print(f"    {edge.fact}")
        print()


def _print_entities(output: RetrievalOutput) -> None:
    print(f"\nENTITIES ({output.total_nodes}) — query: {output.query!r}")
    print(f"User: {output.user_id}\n")
    if not output.nodes:
        print("No entities found.")
        return
    for i, node in enumerate(output.nodes, start=1):
        labels = ", ".join(node.labels) if node.labels else "Entity"
        print(f"[{i}] [{labels}] {node.name}")
        if node.summary:
            print(f"    {node.summary}")
        print()


def _print_json(output: RetrievalOutput) -> None:
    data = {
        "query":       output.query,
        "user_id":     output.user_id,
        "total_edges": output.total_edges,
        "total_nodes": output.total_nodes,
        "edges": [
            {
                "name":       edge.name,
                "fact":       edge.fact,
                "valid_at":   edge.valid_at.isoformat() if edge.valid_at else None,
                "invalid_at": edge.invalid_at.isoformat() if edge.invalid_at else None,
                "uuid":       str(edge.uuid),
            }
            for edge in output.edges
        ],
        "nodes": [
            {
                "name":    node.name,
                "labels":  list(node.labels) if node.labels else [],
                "summary": node.summary,
                "uuid":    str(node.uuid),
            }
            for node in output.nodes
        ],
    }
    print(json.dumps(data, indent=2, ensure_ascii=False))


# ── Main async runner ─────────────────────────────────────────────────────────

async def _run(args: argparse.Namespace) -> None:
    print(f"\nUser   : {args.user_id}")
    print(f"Query  : {args.query!r}")
    if args.entity_types:
        print(f"Filter (entities): {args.entity_types}")
    if args.edge_types:
        print(f"Filter (edges)   : {args.edge_types}")
    if args.current_only:
        print("Mode   : current facts only (expired facts excluded)")
    print()

    if args.retrieve_only:
        # ── Retrieval-only mode ───────────────────────────────────────────────
        print("Retrieving from knowledge graph...")
        output = await run_retrieval(
            query=args.query,
            user_id=args.user_id,
            num_results=args.num_results,
            entity_types=args.entity_types,
            edge_types=args.edge_types,
            current_facts_only=args.current_only,
        )
        fmt = args.format
        if fmt == "context":
            _print_retrieval_context(output)
        elif fmt == "facts":
            _print_facts(output)
        elif fmt == "entities":
            _print_entities(output)
        elif fmt == "json":
            _print_json(output)
    else:
        # ── Full QA mode (default) ────────────────────────────────────────────
        print("Step 1/2: Retrieving facts from knowledge graph...")
        print("Step 2/2: Generating answer with Gemini...\n")
        result = await run_qa(
            query=args.query,
            user_id=args.user_id,
            num_results=args.num_results,
            entity_types=args.entity_types,
            edge_types=args.edge_types,
            current_facts_only=args.current_only,
        )
        _print_answer(result)


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(_run(args))
    except EnvironmentError as e:
        print(f"\nConfiguration error:\n  {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
