"""
Cypher script generator and GCS uploader.

Queries Neo4j for the subgraph belonging to a Graphiti episode, renders a
self-contained .cypher script, and uploads it to GCS.

The returned GCS URI is stored on the Firestore document record so the
frontend can fetch and use the Cypher file.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from workers.connections.gcs import upload_text
from workers.connections.neo4j import get_session

_log = logging.getLogger(__name__)

# Graphiti-internal properties — never written to the Cypher export
_STRIP = frozenset({
    "embedding", "name_embedding", "summary_embedding",
    "group_id", "created_at", "expired_at",
    "valid_at", "invalid_at", "source_episode_names", "episodes",
})


def generate_and_upload(
    episode_name: str,
    doc_id: str,
    file_name: str,
    doc_type: str,
) -> str:
    """
    Build the Cypher script for this episode and upload it to GCS.
    Returns the GCS URI.
    """
    nodes, edges = _query_episode_graph(episode_name)
    cypher = _render_cypher(episode_name, file_name, doc_type, nodes, edges)
    gcs_uri = upload_text(cypher, doc_id, "graph.cypher")
    _log.info(
        "cypher_exported doc_id=%s nodes=%d edges=%d gcs=%s",
        doc_id, len(nodes), len(edges), gcs_uri,
    )
    return gcs_uri


# ── Neo4j query ───────────────────────────────────────────────────────────────

def _query_episode_graph(episode_name: str) -> tuple[list[dict], list[dict]]:
    """Walk 2 hops from the Episodic node to collect the document subgraph."""
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_nodes: set[str] = set()
    seen_edges: set[tuple] = set()

    with get_session() as session:
        node_rows = session.run(
            """
            MATCH (ep:Episodic {name: $name})-[*0..2]-(n)
            WHERE NOT n:Episodic
            RETURN DISTINCT
                elementId(n)  AS eid,
                labels(n)     AS lbls,
                properties(n) AS props
            LIMIT 300
            """,
            name=episode_name,
        )

        for row in node_rows:
            eid: str = row["eid"]
            if eid in seen_nodes:
                continue
            seen_nodes.add(eid)
            raw_props: dict = dict(row["props"])
            clean_props = _clean(raw_props)
            uuid = raw_props.get("uuid", eid)
            nodes.append({
                "uuid":   uuid,
                "eid":    eid,
                "labels": list(row["lbls"]),
                "name":   str(raw_props.get("name") or uuid),
                "props":  clean_props,
            })

        if seen_nodes:
            eid_to_uuid = {n["eid"]: n["uuid"] for n in nodes}
            rel_rows = session.run(
                """
                MATCH (a)-[r]->(b)
                WHERE NOT a:Episodic AND NOT b:Episodic
                  AND elementId(a) IN $ids AND elementId(b) IN $ids
                RETURN DISTINCT
                    elementId(a) AS src,
                    elementId(b) AS tgt,
                    type(r)      AS rtype,
                    properties(r) AS props
                LIMIT 500
                """,
                ids=list(seen_nodes),
            )
            for row in rel_rows:
                key = (row["src"], row["tgt"], row["rtype"])
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edges.append({
                    "source": eid_to_uuid.get(row["src"], row["src"]),
                    "target": eid_to_uuid.get(row["tgt"], row["tgt"]),
                    "type":   row["rtype"],
                    "props":  _clean(dict(row["props"])),
                })

    return nodes, edges


# ── Cypher rendering ──────────────────────────────────────────────────────────

def _render_cypher(
    episode_name: str,
    file_name: str,
    doc_type: str,
    nodes: list[dict],
    edges: list[dict],
) -> str:
    lines = [
        f"// Knowledge Graph — {file_name}",
        f"// Document type : {doc_type}",
        f"// Episode       : {episode_name}",
        f"// Generated     : {datetime.now(timezone.utc).isoformat()}",
        "//",
        "// Paste into Neo4j Browser to visualise the graph for this document.",
        "",
        f"MATCH path = (ep:Episodic {{name: {_q(episode_name)}}})-[*0..2]-(n)",
        "WHERE NOT n:Episodic",
        "RETURN path",
    ]

    return "\n".join(lines) + "\n"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean(props: dict) -> dict:
    return {
        k: v for k, v in props.items()
        if k not in _STRIP and not k.endswith("_embedding") and v is not None
    }


def _var(uid: str) -> str:
    return "n_" + "".join(c if c.isalnum() else "_" for c in uid)[:20]


def _q(v: object) -> str:
    return "'" + str(v).replace("'", "\\'") + "'"


def _props(d: dict) -> str:
    if not d:
        return "{}"
    pairs = []
    for k, v in d.items():
        key = k if k.isidentifier() else f"`{k}`"
        if isinstance(v, bool):
            pairs.append(f"{key}: {str(v).lower()}")
        elif isinstance(v, (int, float)):
            pairs.append(f"{key}: {v}")
        elif isinstance(v, list):
            pairs.append(f"{key}: [{', '.join(_q(x) for x in v)}]")
        else:
            pairs.append(f"{key}: {_q(v)}")
    return "{" + ", ".join(pairs) + "}"
