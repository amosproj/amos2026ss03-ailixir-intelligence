from __future__ import annotations

from typing import Any

from kg_chat.config import AppConfig
from kg_chat.schema_cache import GraphSchema, Neo4jSchemaIntrospector


class Neo4jConfigurationError(RuntimeError):
    pass


class Neo4jGraphClient:
    def __init__(self, config: AppConfig) -> None:
        if not config.neo4j_configured:
            raise Neo4jConfigurationError(
                "NEO4J_URI, NEO4J_USER or NEO4J_USERNAME, and NEO4J_PASSWORD are required."
            )

        try:
            from neo4j import GraphDatabase
        except Exception as exc:
            raise Neo4jConfigurationError(
                "neo4j dependency is missing. Install neo4j."
            ) from exc

        self.config = config
        self.driver = GraphDatabase.driver(
            config.neo4j_uri,
            auth=(config.neo4j_user, config.neo4j_password),
        )
        self._schema: GraphSchema | None = None

    def verify_connectivity(self) -> None:
        self.driver.verify_connectivity()

    def close(self) -> None:
        self.driver.close()

    @property
    def schema(self) -> GraphSchema | None:
        return self._schema

    def refresh_schema(self) -> GraphSchema:
        introspector = Neo4jSchemaIntrospector(
            self.driver,
            database=self.config.neo4j_database,
            pattern_limit=self.config.schema_pattern_limit,
        )
        self._schema = introspector.refresh()
        return self._schema

    def get_schema(self) -> GraphSchema:
        if self._schema is None:
            return self.refresh_schema()
        return self._schema

    def run_read_query(
        self,
        cypher: str,
        parameters: dict[str, Any],
        *,
        max_rows: int,
    ) -> list[dict[str, Any]]:
        session_kwargs = {"database": self.config.neo4j_database} if self.config.neo4j_database else {}
        with self.driver.session(**session_kwargs) as session:
            records = session.run(cypher, parameters)
            rows = [self._record_to_dict(record) for record in records]
        return rows[:max_rows]

    def _record_to_dict(self, record: Any) -> dict[str, Any]:
        return {key: self._to_jsonable(record[key]) for key in record.keys()}

    def _to_jsonable(self, value: Any) -> Any:
        try:
            from neo4j.graph import Node, Path, Relationship
        except Exception:
            Node = Relationship = Path = ()  # type: ignore

        if isinstance(value, Node):
            return {
                "element_id": value.element_id,
                "labels": sorted(value.labels),
                "properties": {
                    str(key): self._to_jsonable(item)
                    for key, item in dict(value).items()
                },
            }
        if isinstance(value, Relationship):
            return {
                "element_id": value.element_id,
                "type": value.type,
                "start_node": value.start_node.element_id,
                "end_node": value.end_node.element_id,
                "properties": {
                    str(key): self._to_jsonable(item)
                    for key, item in dict(value).items()
                },
            }
        if isinstance(value, Path):
            return {
                "nodes": [self._to_jsonable(node) for node in value.nodes],
                "relationships": [
                    self._to_jsonable(relationship)
                    for relationship in value.relationships
                ],
            }
        if isinstance(value, dict):
            return {str(key): self._to_jsonable(item) for key, item in value.items()}
        if isinstance(value, list | tuple | set):
            return [self._to_jsonable(item) for item in value]
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

