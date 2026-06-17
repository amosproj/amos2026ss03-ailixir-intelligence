from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

from kg_chat.config import AppConfig


logger = logging.getLogger(__name__)


class GraphitiSearchConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class GraphitiSearchResult:
    uuid: str | None
    group_id: str | None
    source_node_uuid: str | None
    target_node_uuid: str | None
    name: str | None
    fact: str | None
    episodes: list[str]
    valid_at: Any = None
    invalid_at: Any = None
    expired_at: Any = None
    reference_time: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "uuid": self.uuid,
            "group_id": self.group_id,
            "source_node_uuid": self.source_node_uuid,
            "target_node_uuid": self.target_node_uuid,
            "name": self.name,
            "fact": self.fact,
            "episodes": self.episodes,
            "valid_at": _jsonable(self.valid_at),
            "invalid_at": _jsonable(self.invalid_at),
            "expired_at": _jsonable(self.expired_at),
            "reference_time": _jsonable(self.reference_time),
        }


class GraphitiSearchClient:
    def __init__(self, config: AppConfig) -> None:
        if not config.graphiti_search_configured:
            raise GraphitiSearchConfigurationError(
                "Graphiti search needs GRAPHITI_SEARCH_ENABLED=true, Neo4j credentials, "
                "and OPENAI_API_KEY."
            )

        try:
            os.environ.setdefault("GRAPHITI_TELEMETRY_ENABLED", "false")

            from graphiti_core import Graphiti
            from graphiti_core.embedder.openai import (
                OpenAIEmbedder,
                OpenAIEmbedderConfig,
            )
            from graphiti_core.llm_client.config import LLMConfig
            from graphiti_core.llm_client.openai_client import OpenAIClient
        except Exception as exc:
            raise GraphitiSearchConfigurationError(
                "Graphiti search dependencies are missing. Install graphiti-core and openai."
            ) from exc

        self._graphiti_cls = Graphiti
        self._openai_client_cls = OpenAIClient
        self._llm_config_cls = LLMConfig
        self._openai_embedder_cls = OpenAIEmbedder
        self._openai_embedder_config_cls = OpenAIEmbedderConfig
        self._neo4j_uri = config.neo4j_uri
        self._neo4j_user = config.neo4j_user
        self._neo4j_password = config.neo4j_password
        self._openai_api_key = config.openai_api_key

    def search(
        self,
        *,
        query: str,
        group_id: str | None,
        limit: int,
    ) -> list[GraphitiSearchResult]:
        group_ids = [group_id] if group_id else None
        logger.debug(
            "Running native Graphiti search: query=%r group_ids=%s limit=%s",
            query,
            group_ids,
            limit,
        )
        edges = _run_async(self._search_once(query=query, group_ids=group_ids, limit=limit))
        results = [_edge_to_result(edge) for edge in edges]
        logger.info(
            "Native Graphiti search returned %s result(s) for group_id=%s.",
            len(results),
            group_id,
        )
        logger.debug(
            "Native Graphiti search edge UUIDs: %s",
            [result.uuid for result in results if result.uuid],
        )
        return results

    async def aclose(self) -> None:
        return None

    async def _search_once(
        self,
        *,
        query: str,
        group_ids: list[str] | None,
        limit: int,
    ) -> Any:
        llm_client = self._openai_client_cls(
            config=self._llm_config_cls(api_key=self._openai_api_key)
        )
        embedder = self._openai_embedder_cls(
            config=self._openai_embedder_config_cls(api_key=self._openai_api_key)
        )
        graphiti = self._graphiti_cls(
            self._neo4j_uri,
            self._neo4j_user,
            self._neo4j_password,
            llm_client=llm_client,
            embedder=embedder,
        )
        try:
            return await graphiti.search(
                query=query,
                group_ids=group_ids,
                num_results=limit,
            )
        finally:
            await graphiti.close()


def _edge_to_result(edge: Any) -> GraphitiSearchResult:
    payload = edge.model_dump() if hasattr(edge, "model_dump") else dict(edge)
    return GraphitiSearchResult(
        uuid=payload.get("uuid"),
        group_id=payload.get("group_id"),
        source_node_uuid=payload.get("source_node_uuid"),
        target_node_uuid=payload.get("target_node_uuid"),
        name=payload.get("name"),
        fact=payload.get("fact"),
        episodes=list(payload.get("episodes") or []),
        valid_at=payload.get("valid_at"),
        invalid_at=payload.get("invalid_at"),
        expired_at=payload.get("expired_at"),
        reference_time=payload.get("reference_time"),
    )


def _run_async(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    raise RuntimeError("Graphiti search cannot run from an active event loop thread.")


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value
