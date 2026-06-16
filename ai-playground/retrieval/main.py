"""
CLI entry point for the Graphiti retrieval pipeline.

Usage (run from ai-playground/ directory):

    python -m retrieval.main "What medications is the patient on?" --user-id USER_ID

    python -m retrieval.main "PSA levels" --user-id USER_ID --num-results 5

    python -m retrieval.main "diagnoses" --user-id USER_ID \\
        --entity-types Diagnosis Patient \\
        --current-only

    python -m retrieval.main "lab results" --user-id USER_ID \\
        --edge-types HAD_LAB_TEST \\
        --format facts

Output formats:
    context  — Full formatted context string (default, good for LLM prompts)
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

from retrieval.pipeline import RetrievalOutput, run_retrieval

# Silence noisy library loggers so pipeline output is clean
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s  %(name)s  %(message)s",
)
logging.getLogger("retrieval").setLevel(logging.INFO)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m retrieval.main",
        description="Query a patient's Graphiti knowledge graph.",
    )
    parser.add_argument(
        "query",
        help="Natural-language query (e.g. 'What medications is this patient on?')",
    )
    parser.add_argument(
        "--user-id",
        required=True,
        metavar="UID",
        help="Firebase UID of the patient whose graph to query.",
    )
    parser.add_argument(
        "--num-results",
        type=int,
        default=10,
        metavar="N",
        help="Maximum number of facts/entities to retrieve (default: 10).",
    )
    parser.add_argument(
        "--entity-types",
        nargs="+",
        metavar="TYPE",
        help=(
            "Restrict node search to specific medical entity types. "
            "E.g.: --entity-types Medication Diagnosis LabTest"
        ),
    )
    parser.add_argument(
        "--edge-types",
        nargs="+",
        metavar="TYPE",
        help=(
            "Restrict edge search to specific relationship types. "
            "E.g.: --edge-types PRESCRIBED HAS_DIAGNOSIS"
        ),
    )
    parser.add_argument(
        "--current-only",
        action="store_true",
        default=False,
        help="Return only current (non-expired) facts. Hides superseded data.",
    )
    parser.add_argument(
        "--format",
        choices=["context", "facts", "entities", "json"],
        default="context",
        help="Output format (default: context).",
    )
    return parser.parse_args()


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
        "query": output.query,
        "user_id": output.user_id,
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


async def _run(args: argparse.Namespace) -> None:
    print(f"\nQuerying knowledge graph for user: {args.user_id}")
    print(f"Query: {args.query!r}")
    if args.entity_types:
        print(f"Entity filter: {args.entity_types}")
    if args.edge_types:
        print(f"Edge filter: {args.edge_types}")
    if args.current_only:
        print("Mode: current facts only (expired facts excluded)")
    print()

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
        print(output.context)
    elif fmt == "facts":
        _print_facts(output)
    elif fmt == "entities":
        _print_entities(output)
    elif fmt == "json":
        _print_json(output)


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
