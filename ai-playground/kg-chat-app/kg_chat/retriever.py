from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from kg_chat.config import AppConfig
from kg_chat.graphiti_search import GraphitiSearchClient, GraphitiSearchResult
from kg_chat.llm import LlmClient
from kg_chat.models import ChatResponse, QueryDebug, QueryPlan, QueryResponse
from kg_chat.neo4j_client import Neo4jGraphClient
from kg_chat.prompts import build_answer_prompt
from kg_chat.query import QueryValidationError, ValidatedQuery, validate_query_plan
from kg_chat.router import RoutedQuery, build_routed_query


logger = logging.getLogger(__name__)


@dataclass
class HistoryTurn:
    question: str
    answer: str


@dataclass(frozen=True)
class RetrievalResult:
    validated: ValidatedQuery
    rows: list[dict[str, Any]]
    retrieval_debug: dict[str, Any]
    graphiti_search_results: list[dict[str, Any]]


class InMemoryHistory:
    def __init__(self, max_turns: int) -> None:
        self.max_turns = max_turns
        self._turns: dict[str, list[HistoryTurn]] = {}

    def format(self, session_id: str) -> str:
        turns = self._turns.get(session_id, [])[-self.max_turns :]
        if not turns:
            return ""
        lines: list[str] = []
        for turn in turns:
            lines.append(f"user: {turn.question}")
            lines.append(f"assistant: {turn.answer}")
        return "\n".join(lines)

    def append(self, session_id: str, *, question: str, answer: str) -> None:
        turns = self._turns.setdefault(session_id, [])
        turns.append(HistoryTurn(question=question, answer=answer))
        del turns[: max(0, len(turns) - self.max_turns)]


class GraphChatService:
    def __init__(
        self,
        *,
        config: AppConfig,
        llm: LlmClient,
        graph_client: Neo4jGraphClient,
        graphiti_search: GraphitiSearchClient | None = None,
    ) -> None:
        self.config = config
        self.llm = llm
        self.graph_client = graph_client
        self.graphiti_search = graphiti_search
        self.history = InMemoryHistory(max_turns=config.max_history_turns)

    def generate_query_only(
        self,
        *,
        question: str,
        session_id: str,
        group_id: str | None = None,
    ) -> QueryResponse:
        schema = self.graph_client.get_schema()
        history_text = self.history.format(session_id)
        routed = self._build_validated_route(question, history_text, group_id=group_id)
        retrieval = self._retrieve(
            routed=routed,
            question=question,
            schema=schema,
            execute=False,
        )
        return QueryResponse(
            cypher=retrieval.validated.cypher,
            parameters=retrieval.validated.parameters,
            reason=routed.query_plan.reason,
            intent=routed.route_plan.intent,
            strategy=routed.strategy,
            route_plan=routed.route_plan.model_dump(),
            planner_debug=routed.planner_debug.to_dict(),
            retrieval_debug=retrieval.retrieval_debug,
            graphiti_search_results=retrieval.graphiti_search_results,
        )

    def chat(
        self,
        *,
        question: str,
        session_id: str,
        group_id: str | None,
        include_debug: bool,
    ) -> ChatResponse:
        schema = self.graph_client.get_schema()
        history_text = self.history.format(session_id)
        routed = self._build_validated_route(question, history_text, group_id=group_id)
        retrieval = self._retrieve(
            routed=routed,
            question=question,
            schema=schema,
            execute=True,
        )

        answer_prompt = build_answer_prompt(
            question=question,
            history_text=history_text,
            cypher=retrieval.validated.cypher,
            rows=retrieval.rows,
        )
        answer = self.llm.generate_text(answer_prompt)
        self.history.append(session_id, question=question, answer=answer)

        debug = None
        if include_debug:
            debug = QueryDebug(
                generated_cypher=retrieval.validated.generated_cypher,
                executed_cypher=retrieval.validated.cypher,
                parameters=retrieval.validated.parameters,
                rows=retrieval.rows,
                schema_refreshed_at=schema.refreshed_at,
                reason=routed.query_plan.reason,
                intent=routed.route_plan.intent,
                strategy=routed.strategy,
                route_plan=routed.route_plan.model_dump(),
                planner_debug=routed.planner_debug.to_dict(),
                retrieval_debug=retrieval.retrieval_debug,
                graphiti_search_results=retrieval.graphiti_search_results,
            )

        return ChatResponse(answer=answer, session_id=session_id, debug=debug)

    def refresh_schema(self) -> dict:
        return self.graph_client.refresh_schema().to_dict()

    def _build_validated_route(
        self,
        question: str,
        history_text: str,
        *,
        group_id: str | None,
    ) -> RoutedQuery:
        schema = self.graph_client.get_schema()
        routed = build_routed_query(
            llm=self.llm,
            question=question,
            schema=schema,
            history_text=history_text,
            default_limit=self.config.default_query_limit,
            group_id=group_id,
        )
        validate_query_plan(
            plan=routed.query_plan,
            schema=schema,
            default_limit=self.config.default_query_limit,
        )
        return routed

    def _retrieve(
        self,
        *,
        routed: RoutedQuery,
        question: str,
        schema,
        execute: bool,
    ) -> RetrievalResult:
        if self._requires_native_graphiti(routed):
            if self.graphiti_search is None:
                raise QueryValidationError(
                    "Native Graphiti search is required for semantic retrieval, "
                    "but it is not available. No Cypher text fallback is enabled."
                )
            try:
                return self._retrieve_with_native_graphiti(
                    routed=routed,
                    question=question,
                    schema=schema,
                    execute=execute,
                )
            except Exception as exc:
                logger.exception("Native Graphiti search failed.")
                raise QueryValidationError(
                    "Native Graphiti search failed. No Cypher text fallback is enabled. "
                    f"{exc.__class__.__name__}: {exc}"
                ) from exc

        return self._retrieve_with_cypher_template(
            routed=routed,
            schema=schema,
            execute=execute,
        )

    def _retrieve_with_cypher_template(
        self,
        *,
        routed: RoutedQuery,
        schema,
        execute: bool,
    ) -> RetrievalResult:
        if routed.strategy != "cypher_template":
            raise QueryValidationError(
                f"Strategy {routed.strategy!r} is not a Cypher template strategy. "
                "No Cypher text fallback is enabled."
            )
        validated = validate_query_plan(
            plan=routed.query_plan,
            schema=schema,
            default_limit=self.config.default_query_limit,
        )
        rows = (
            self.graph_client.run_read_query(
                validated.cypher,
                validated.parameters,
                max_rows=self.config.max_rows_for_answer,
            )
            if execute
            else []
        )
        return RetrievalResult(
            validated=validated,
            rows=rows,
            retrieval_debug={"mode": "cypher_template"},
            graphiti_search_results=[],
        )

    def _requires_native_graphiti(self, routed: RoutedQuery) -> bool:
        return routed.strategy in {
            "graphiti_hybrid_search",
            "graphiti_search_cypher_expansion",
        }

    def _retrieve_with_native_graphiti(
        self,
        *,
        routed: RoutedQuery,
        question: str,
        schema,
        execute: bool,
    ) -> RetrievalResult:
        assert self.graphiti_search is not None

        search_query = _native_graphiti_search_query(routed.route_plan, question)
        group_id = routed.route_plan.group_id
        search_results = self.graphiti_search.search(
            query=search_query,
            group_id=group_id,
            limit=self.config.graphiti_search_limit,
        )
        search_result_dicts = [result.to_dict() for result in search_results]
        edge_uuids = [result.uuid for result in search_results if result.uuid]
        logger.debug(
            "Native Graphiti seed search complete: query=%r group_id=%s count=%s edge_uuids=%s",
            search_query,
            group_id,
            len(search_results),
            edge_uuids,
        )

        query_plan = _build_graphiti_seed_expansion_query(
            edge_uuids=edge_uuids,
            group_id=group_id,
            default_limit=self.config.default_query_limit,
        )
        validated = validate_query_plan(
            plan=query_plan,
            schema=schema,
            default_limit=self.config.default_query_limit,
        )
        rows = []
        if execute and edge_uuids:
            rows = self.graph_client.run_read_query(
                validated.cypher,
                validated.parameters,
                max_rows=self.config.max_rows_for_answer,
            )

        fallback_rows_from_search_results = False
        if execute and not rows:
            fallback_rows_from_search_results = True
            rows = _search_results_as_rows(search_results)

        return RetrievalResult(
            validated=validated,
            rows=rows,
            retrieval_debug={
                "mode": "native_graphiti_search_then_cypher_expansion",
                "search_query": search_query,
                "group_id": group_id,
                "search_limit": self.config.graphiti_search_limit,
                "search_result_count": len(search_results),
                "seed_edge_uuids": edge_uuids,
                "fallback_rows_from_search_results": fallback_rows_from_search_results,
            },
            graphiti_search_results=search_result_dicts,
        )

def _build_graphiti_seed_expansion_query(
    *,
    edge_uuids: list[str],
    group_id: str | None,
    default_limit: int,
) -> QueryPlan:
    return QueryPlan(
        cypher="""
MATCH (source:Entity)-[relationship:RELATES_TO]->(target:Entity)
WHERE relationship.uuid IN $edge_uuids
  AND ($group_id IS NULL OR source.group_id = $group_id OR target.group_id = $group_id OR relationship.group_id = $group_id)
OPTIONAL MATCH (source)-[source_context:RELATES_TO]-(source_neighbor:Entity)
WHERE $group_id IS NULL OR source_neighbor.group_id = $group_id OR source_context.group_id = $group_id
OPTIONAL MATCH (target)-[target_context:RELATES_TO]-(target_neighbor:Entity)
WHERE $group_id IS NULL OR target_neighbor.group_id = $group_id OR target_context.group_id = $group_id
OPTIONAL MATCH (source_episode:Episodic)-[:MENTIONS]->(source)
WHERE $group_id IS NULL OR source_episode.group_id = $group_id
OPTIONAL MATCH (target_episode:Episodic)-[:MENTIONS]->(target)
WHERE $group_id IS NULL OR target_episode.group_id = $group_id
RETURN source.name AS source,
       source.summary AS source_summary,
       source.labels AS source_labels,
       relationship.uuid AS seed_edge_uuid,
       relationship.name AS relationship,
       relationship.fact AS fact,
       relationship.valid_at AS valid_at,
       target.name AS target,
       target.summary AS target_summary,
       target.labels AS target_labels,
       collect(DISTINCT {
         relationship: source_context.name,
         fact: source_context.fact,
         neighbor: source_neighbor.name,
         valid_at: source_context.valid_at
       }) AS source_context,
       collect(DISTINCT {
         relationship: target_context.name,
         fact: target_context.fact,
         neighbor: target_neighbor.name,
         valid_at: target_context.valid_at
       }) AS target_context,
       collect(DISTINCT {
         episode: source_episode.name,
         source: source_episode.source,
         source_description: source_episode.source_description,
         content: source_episode.content,
         valid_at: source_episode.valid_at
       }) AS source_episodes,
       collect(DISTINCT {
         episode: target_episode.name,
         source: target_episode.source,
         source_description: target_episode.source_description,
         content: target_episode.content,
         valid_at: target_episode.valid_at
       }) AS target_episodes
LIMIT $limit
""".strip(),
        parameters={
            "edge_uuids": edge_uuids,
            "group_id": group_id,
            "limit": default_limit,
        },
        reason="Native Graphiti hybrid search returned seed edges; Cypher expands around those facts.",
    )


def _search_results_as_rows(
    search_results: list[GraphitiSearchResult],
) -> list[dict[str, Any]]:
    return [
        {
            "seed_edge_uuid": result.uuid,
            "relationship": result.name,
            "fact": result.fact,
            "group_id": result.group_id,
            "valid_at": _jsonable(result.valid_at),
            "source_node_uuid": result.source_node_uuid,
            "target_node_uuid": result.target_node_uuid,
            "episodes": result.episodes,
            "retrieval_source": "native_graphiti_search",
        }
        for result in search_results
    ]


def _jsonable(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _native_graphiti_search_query(route_plan, question: str) -> str:
    parts = [
        route_plan.semantic_query or "",
        *route_plan.related_terms,
        *route_plan.target_entities,
    ]
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        normalized = str(part).strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return " ".join(deduped) or question.strip()
