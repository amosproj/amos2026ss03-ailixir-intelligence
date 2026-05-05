from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from neo4j import GraphDatabase


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str
    user: str
    password: str
    database: str | None = None


def ingest_graph_payload(
    payload: dict[str, Any],
    *,
    source_id: str,
    doc_type: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    neo4j_database: str | None = None,
) -> None:
    """
    Ingest a Gemini-produced payload shaped like:
      { "schema_json": {...}, "graph": { "nodes": [...], "relationships": [...] } }

    This keeps the whole playground at ONE LLM call (Gemini) and uses only Neo4j writes after.
    """
    cfg = Neo4jConfig(uri=neo4j_uri, user=neo4j_user, password=neo4j_password, database=neo4j_database)
    graph = payload.get("graph") if isinstance(payload, dict) else None
    if not isinstance(graph, dict):
        return

    nodes = graph.get("nodes", [])
    rels = graph.get("relationships", [])
    schema_json = payload.get("schema_json")

    with GraphDatabase.driver(cfg.uri, auth=(cfg.user, cfg.password)) as driver:
        session_kwargs = {"database": cfg.database} if cfg.database else {}
        with driver.session(**session_kwargs) as session:
            session.execute_write(
                _write_graph_payload,
                source_id=source_id,
                doc_type=doc_type,
                schema_json=schema_json,
                nodes=nodes,
                rels=rels,
            )


def _write_graph_payload(tx, *, source_id: str, doc_type: str, schema_json: Any, nodes: Any, rels: Any) -> None:
    tx.run(
        """
        MERGE (d:Document {source_id: $source_id})
        SET d.doc_type = $doc_type,
            d.name = $doc_name,
            d.schema_json = $schema_json,
            d.updated_at = datetime()
        """,
        source_id=source_id,
        doc_type=doc_type,
        doc_name=f"{doc_type}:{source_id}",
        schema_json=json.dumps(schema_json, ensure_ascii=False) if schema_json is not None else None,
    )

    # Nodes (generic :Entity with labels list stored as property)
    for n in nodes if isinstance(nodes, list) else []:
        if not isinstance(n, dict):
            continue
        node_id = n.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            continue
        # Support both shapes:
        # A) prompt-intended: {"id": "...", "labels": [...], "properties": {...}}
        # B) common LLM output: {"id": "...", "type": "...", "name": "...", ...}
        labels = n.get("labels", [])
        props = n.get("properties", {})
        if not isinstance(labels, list):
            labels = []
        if not isinstance(props, dict):
            props = {}

        # If node is in shape (B), treat all keys except id/labels/properties as properties.
        if not props:
            props = {
                k: v
                for k, v in n.items()
                if k not in {"id", "labels", "properties"} and v is not None
            }

        # Allow "type" to behave like a label for retrieval/visual grouping.
        node_type = n.get("type")
        if isinstance(node_type, str) and node_type.strip():
            labels = [*labels, node_type.strip()]

        # Avoid writing nulls (they delete properties in Neo4j) and ensure a stable display name.
        cleaned_props = {str(k): v for k, v in props.items() if v is not None}
        inferred_name = cleaned_props.get("name") if isinstance(cleaned_props.get("name"), str) else None

        tx.run(
            """
            MERGE (e:Entity {id: $id})
            SET e.labels = $labels,
                e += $props,
                e.name = coalesce($inferred_name, e.name, $fallback_name),
                e.updated_at = datetime()
            WITH e
            MATCH (d:Document {source_id: $source_id})
            MERGE (d)-[:MENTIONS]->(e)
            """,
            id=node_id,
            labels=[str(x) for x in labels],
            props=cleaned_props,
            inferred_name=inferred_name,
            fallback_name=node_id,
            source_id=source_id,
        )

    # Relationships (generic :REL with type stored as property)
    for r in rels if isinstance(rels, list) else []:
        if not isinstance(r, dict):
            continue
        src = r.get("source")
        tgt = r.get("target")
        rel_type = r.get("type")
        props = r.get("properties", {})
        if not (isinstance(src, str) and isinstance(tgt, str) and isinstance(rel_type, str)):
            continue
        if not isinstance(props, dict):
            props = {}

        cleaned_props = {str(k): v for k, v in props.items() if v is not None}

        # Use a generic relationship to avoid dynamic Cypher relationship types.
        # Store the intended type on the relationship itself.
        tx.run(
            """
            MATCH (a:Entity {id: $src})
            MATCH (b:Entity {id: $tgt})
            // IMPORTANT:
            // Include source_id in the relationship identity to avoid collapsing edges
            // coming from different documents/runs (critical for retrieval + visualization).
            MERGE (a)-[rel:REL {type: $type, source_id: $source_id}]->(b)
            SET rel += $props,
                rel.updated_at = datetime()
            """,
            src=src,
            tgt=tgt,
            type=rel_type,
            source_id=source_id,
            props=cleaned_props,
        )

