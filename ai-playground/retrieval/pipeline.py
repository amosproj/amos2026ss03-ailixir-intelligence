"""
User retrieval pipeline.

Entry point: run_retrieval(query, user_id, ...) → RetrievalOutput

Flow:
  1. Connect to Graphiti (Neo4j + Vertex AI embedder)
  2. Run combined search (edges + nodes) scoped to the user's group_id
  3. Optionally filter edges to current (non-expired) facts only
  4. Format results into a human/LLM-readable context string
  5. Return RetrievalOutput with raw results + formatted context

The context string is designed to be dropped directly into an LLM prompt.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from graphiti_core import Graphiti
from graphiti_core.edges import EntityEdge
from graphiti_core.nodes import EntityNode

from retrieval.graphiti_client import create_graphiti
from retrieval.retriever import RetrievalResult, build_medical_filter, search_combined

_log = logging.getLogger(__name__)


# ── Output dataclass ──────────────────────────────────────────────────────────

@dataclass
class RetrievalOutput:
    """
    Final output of run_retrieval().

    Attributes:
        query:    The original search query.
        user_id:  Firebase UID used to scope the search.
        edges:    Relevant relationship facts (EntityEdge).
        nodes:    Relevant medical entities (EntityNode).
        context:  Formatted string ready to inject into an LLM prompt.
        total_edges: Number of edges returned.
        total_nodes: Number of nodes returned.
    """

    query: str
    user_id: str
    edges: list[EntityEdge] = field(default_factory=list)
    nodes: list[EntityNode] = field(default_factory=list)
    context: str = ""
    total_edges: int = 0
    total_nodes: int = 0


# ── Main pipeline entry point ─────────────────────────────────────────────────

async def run_retrieval(
    query: str,
    user_id: str,
    num_results: int = 10,
    entity_types: list[str] | None = None,
    edge_types: list[str] | None = None,
    current_facts_only: bool = False,
    graphiti: Graphiti | None = None,
) -> RetrievalOutput:
    """
    Run the full retrieval pipeline for a user query.

    Args:
        query:             Natural-language question or search term.
        user_id:           Firebase UID — scopes search to this patient only.
        num_results:       Max number of edges/nodes to retrieve (default 10).
        entity_types:      Optional list of medical entity labels to filter nodes.
                           E.g. ["Medication", "Diagnosis", "LabTest"]
        edge_types:        Optional list of relationship types to filter edges.
                           E.g. ["PRESCRIBED", "HAS_DIAGNOSIS"]
        current_facts_only: If True, filter out superseded (expired) facts.
                            Only returns edges where invalid_at is None.
        graphiti:          Optional pre-built Graphiti instance. If None,
                           a new one is created (and closed after use).

    Returns:
        RetrievalOutput with edges, nodes, and a formatted context string.
    """
    _log.info("retrieval_start query=%r user_id=%s", query, user_id)

    # Manage Graphiti lifecycle if not provided externally
    _owns_graphiti = graphiti is None
    if _owns_graphiti:
        graphiti = await create_graphiti(build_indices=False)

    try:
        search_filter = build_medical_filter(
            entity_types=entity_types,
            edge_types=edge_types,
        )

        result: RetrievalResult = await search_combined(
            graphiti=graphiti,
            query=query,
            user_id=user_id,
            num_results=num_results,
            search_filter=search_filter,
        )

        edges = result.edges
        nodes = result.nodes

        # Filter to current (non-expired) facts if requested
        if current_facts_only:
            edges = [e for e in edges if e.invalid_at is None]
            _log.info("current_facts_only: filtered to %d edges", len(edges))

        context = _format_context(query=query, user_id=user_id, edges=edges, nodes=nodes)

        output = RetrievalOutput(
            query=query,
            user_id=user_id,
            edges=edges,
            nodes=nodes,
            context=context,
            total_edges=len(edges),
            total_nodes=len(nodes),
        )

        _log.info(
            "retrieval_done user_id=%s edges=%d nodes=%d",
            user_id, len(edges), len(nodes),
        )
        return output

    finally:
        if _owns_graphiti:
            await graphiti.close()


# ── Context formatter ─────────────────────────────────────────────────────────

def _format_context(
    query: str,
    user_id: str,
    edges: list[EntityEdge],
    nodes: list[EntityNode],
) -> str:
    """
    Format retrieval results into a structured context string for LLM prompts.

    Sections:
      - Header with query + user
      - Relevant Facts (edges): relationship type, fact text, valid/invalid dates
      - Relevant Entities (nodes): entity type, name, summary
    """
    lines: list[str] = []

    lines.append("=" * 60)
    lines.append("PATIENT KNOWLEDGE GRAPH — RETRIEVAL CONTEXT")
    lines.append("=" * 60)
    lines.append(f"User ID : {user_id}")
    lines.append(f"Query   : {query}")
    lines.append(f"Results : {len(edges)} facts, {len(nodes)} entities")
    lines.append("")

    # ── Facts (edges) ─────────────────────────────────────────────────────────
    if edges:
        lines.append(f"--- RELEVANT FACTS ({len(edges)}) ---")
        for i, edge in enumerate(edges, start=1):
            lines.append(f"\n[{i}] {edge.name}")
            lines.append(f"    Fact   : {edge.fact}")

            valid_str   = _fmt_date(edge.valid_at)
            invalid_str = _fmt_date(edge.invalid_at) if edge.invalid_at else "current"
            lines.append(f"    Period : {valid_str} → {invalid_str}")

        lines.append("")
    else:
        lines.append("--- RELEVANT FACTS ---")
        lines.append("No facts found for this query.")
        lines.append("")

    # ── Entities (nodes) ──────────────────────────────────────────────────────
    if nodes:
        lines.append(f"--- RELEVANT ENTITIES ({len(nodes)}) ---")
        for i, node in enumerate(nodes, start=1):
            labels = ", ".join(node.labels) if node.labels else "Entity"
            lines.append(f"\n[{i}] [{labels}] {node.name}")
            if node.summary:
                lines.append(f"    Summary: {node.summary}")
    else:
        lines.append("--- RELEVANT ENTITIES ---")
        lines.append("No entities found for this query.")

    lines.append("")
    lines.append("=" * 60)

    return "\n".join(lines)


def _fmt_date(dt: datetime | None) -> str:
    if dt is None:
        return "unknown"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%d")
