from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class GraphSchema:
    labels: list[str] = field(default_factory=list)
    relationship_types: list[str] = field(default_factory=list)
    node_properties: dict[str, list[str]] = field(default_factory=dict)
    relationship_properties: dict[str, list[str]] = field(default_factory=dict)
    observed_patterns: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    refreshed_at: str | None = None

    def to_prompt(self) -> str:
        lines: list[str] = []
        lines.append(f"Refreshed at: {self.refreshed_at or 'unknown'}")

        lines.append("")
        lines.append("Node labels:")
        if self.labels:
            for label in self.labels:
                lines.append(f"- {label}")
        else:
            lines.append("- (none discovered)")

        lines.append("")
        lines.append("Relationship types:")
        if self.relationship_types:
            for rel_type in self.relationship_types:
                lines.append(f"- {rel_type}")
        else:
            lines.append("- (none discovered)")

        lines.append("")
        lines.append("Node properties:")
        if self.node_properties:
            for owner, properties in sorted(self.node_properties.items()):
                joined = ", ".join(properties) if properties else "(none)"
                lines.append(f"- {owner}: {joined}")
        else:
            lines.append("- (none discovered)")

        lines.append("")
        lines.append("Relationship properties:")
        if self.relationship_properties:
            for owner, properties in sorted(self.relationship_properties.items()):
                joined = ", ".join(properties) if properties else "(none)"
                lines.append(f"- {owner}: {joined}")
        else:
            lines.append("- (none discovered)")

        lines.append("")
        lines.append("Observed relationship patterns:")
        if self.observed_patterns:
            for pattern in self.observed_patterns:
                source = ":".join(pattern.get("source_labels") or ["?"])
                target = ":".join(pattern.get("target_labels") or ["?"])
                rel_type = pattern.get("relationship_type", "?")
                count = pattern.get("count", "?")
                lines.append(f"- (:{source})-[:{rel_type}]->(:{target}) count={count}")
        else:
            lines.append("- (none discovered)")

        if self.warnings:
            lines.append("")
            lines.append("Introspection warnings:")
            for warning in self.warnings:
                lines.append(f"- {warning}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "labels": self.labels,
            "relationship_types": self.relationship_types,
            "node_properties": self.node_properties,
            "relationship_properties": self.relationship_properties,
            "observed_patterns": self.observed_patterns,
            "warnings": self.warnings,
            "refreshed_at": self.refreshed_at,
        }


class Neo4jSchemaIntrospector:
    def __init__(
        self,
        driver: Any,
        *,
        database: str | None,
        pattern_limit: int,
    ) -> None:
        self.driver = driver
        self.database = database
        self.pattern_limit = pattern_limit

    def refresh(self) -> GraphSchema:
        schema = GraphSchema(
            refreshed_at=datetime.now(timezone.utc).isoformat(timespec="seconds")
        )
        session_kwargs = {"database": self.database} if self.database else {}

        with self.driver.session(**session_kwargs) as session:
            schema.labels = sorted(
                self._read_column(
                    session,
                    "CALL db.labels() YIELD label RETURN label ORDER BY label",
                    "label",
                    schema,
                    "Could not read node labels",
                )
            )
            schema.relationship_types = sorted(
                self._read_column(
                    session,
                    """
                    CALL db.relationshipTypes()
                    YIELD relationshipType
                    RETURN relationshipType
                    ORDER BY relationshipType
                    """,
                    "relationshipType",
                    schema,
                    "Could not read relationship types",
                )
            )
            schema.node_properties = self._read_property_map(
                session,
                """
                CALL db.schema.nodeTypeProperties()
                YIELD nodeType, propertyName, propertyTypes, mandatory
                RETURN nodeType AS owner,
                       propertyName AS property,
                       propertyTypes AS property_types,
                       mandatory AS mandatory
                ORDER BY owner, property
                """,
                schema,
                "Could not read node properties",
            )
            schema.relationship_properties = self._read_property_map(
                session,
                """
                CALL db.schema.relTypeProperties()
                YIELD relType, propertyName, propertyTypes, mandatory
                RETURN relType AS owner,
                       propertyName AS property,
                       propertyTypes AS property_types,
                       mandatory AS mandatory
                ORDER BY owner, property
                """,
                schema,
                "Could not read relationship properties",
            )
            schema.observed_patterns = self._read_patterns(session, schema)

        return schema

    def _read_column(
        self,
        session: Any,
        query: str,
        column: str,
        schema: GraphSchema,
        warning_prefix: str,
    ) -> list[str]:
        try:
            return [
                str(record[column])
                for record in session.run(query)
                if record.get(column) is not None
            ]
        except Exception as exc:
            schema.warnings.append(f"{warning_prefix}: {exc}")
            return []

    def _read_property_map(
        self,
        session: Any,
        query: str,
        schema: GraphSchema,
        warning_prefix: str,
    ) -> dict[str, list[str]]:
        try:
            property_map: dict[str, list[str]] = {}
            for record in session.run(query):
                owner = str(record.get("owner") or "(unknown)")
                property_name = str(record.get("property") or "")
                if not property_name:
                    continue
                property_types = record.get("property_types") or []
                mandatory = " required" if record.get("mandatory") else ""
                type_text = "|".join(str(item) for item in property_types)
                entry = f"{property_name}: {type_text}{mandatory}".strip()
                property_map.setdefault(owner, []).append(entry)
            return property_map
        except Exception as exc:
            schema.warnings.append(f"{warning_prefix}: {exc}")
            return {}

    def _read_patterns(self, session: Any, schema: GraphSchema) -> list[dict[str, Any]]:
        try:
            records = session.run(
                """
                MATCH (source)-[relationship]->(target)
                RETURN labels(source) AS source_labels,
                       type(relationship) AS relationship_type,
                       labels(target) AS target_labels,
                       count(*) AS count
                ORDER BY count DESC
                LIMIT $limit
                """,
                limit=self.pattern_limit,
            )
            return [record.data() for record in records]
        except Exception as exc:
            schema.warnings.append(f"Could not sample relationship patterns: {exc}")
            return []

