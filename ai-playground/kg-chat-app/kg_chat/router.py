from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Any

from kg_chat.llm import LlmClient
from kg_chat.models import QueryPlan, RoutePlan
from kg_chat.query import extract_json_object
from kg_chat.schema_cache import GraphSchema


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlannerDebug:
    source: str
    raw_response: str | None = None
    parsed_payload: dict[str, Any] | None = None
    error: str | None = None
    selected_strategy: str = ""
    selected_solution: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "raw_response": self.raw_response,
            "parsed_payload": self.parsed_payload,
            "error": self.error,
            "selected_strategy": self.selected_strategy,
            "selected_solution": self.selected_solution or self.selected_strategy,
        }


@dataclass(frozen=True)
class RoutePlanningResult:
    route_plan: RoutePlan
    debug: PlannerDebug


@dataclass(frozen=True)
class RoutedQuery:
    query_plan: QueryPlan
    route_plan: RoutePlan
    strategy: str
    planner_debug: PlannerDebug


CYPHER_TEMPLATE_INTENTS = {
    "timeline_query",
    "events_after_anchor_event",
    "diagnosis_evidence",
    "source_lookup",
    "path_explanation",
    "filter_count_query",
}

SEMANTIC_EXPAND_INTENTS = {
    "patient_specific_search",
    "patient_summary",
    "comparison_query",
}

GRAPHITI_HYBRID_SEARCH = "graphiti_hybrid_search"
GRAPHITI_SEARCH_CYPHER_EXPANSION = "graphiti_search_cypher_expansion"
CYPHER_TEMPLATE = "cypher_template"
LOW_CONFIDENCE_THRESHOLD = 0.25

def build_routed_query(
    *,
    llm: LlmClient,
    question: str,
    schema: GraphSchema,
    history_text: str,
    default_limit: int,
    group_id: str | None = None,
) -> RoutedQuery:
    planning_result = build_route_plan_with_debug(
        llm=llm,
        question=question,
        schema=schema,
        history_text=history_text,
        group_id=group_id,
    )
    route_plan = planning_result.route_plan
    strategy = choose_strategy(route_plan)
    planner_debug = replace(
        planning_result.debug,
        selected_strategy=strategy,
        selected_solution=strategy,
    )
    logger.info(
        "KG route selected: intent=%s strategy=%s group_id=%s source=%s",
        route_plan.intent,
        strategy,
        _effective_group_id(route_plan),
        planner_debug.source,
    )
    query_plan = build_query_for_strategy(
        strategy=strategy,
        route_plan=route_plan,
        question=question,
        schema=schema,
        default_limit=default_limit,
    )
    logger.debug(
        "KG query plan built: strategy=%s reason=%s parameters=%s",
        strategy,
        query_plan.reason,
        query_plan.parameters,
    )
    return RoutedQuery(
        query_plan=query_plan,
        route_plan=route_plan,
        strategy=strategy,
        planner_debug=planner_debug,
    )


def build_route_plan(
    *,
    llm: LlmClient,
    question: str,
    schema: GraphSchema,
    history_text: str,
    group_id: str | None = None,
) -> RoutePlan:
    return build_route_plan_with_debug(
        llm=llm,
        question=question,
        schema=schema,
        history_text=history_text,
        group_id=group_id,
    ).route_plan


def build_route_plan_with_debug(
    *,
    llm: LlmClient,
    question: str,
    schema: GraphSchema,
    history_text: str,
    group_id: str | None = None,
) -> RoutePlanningResult:
    prompt = f"""
You are a query planner for a medical knowledge graph.

Classify the user's question into one of these intents:
- semantic_search
- patient_specific_search
- timeline_query
- events_after_anchor_event
- diagnosis_evidence
- source_lookup
- path_explanation
- filter_count_query
- comparison_query
- patient_summary
- ambiguous

Extract:
- group_id if mentioned or supplied by the API, otherwise null
- semantic_query: a concise phrase for semantic retrieval, preserving medical meaning
- target_entities: explicit entity names mentioned by the user, not generic topics
- related_terms: LLM-generated similarity hints and synonyms for retrieval
- anchor_event if the question is before, after, or during a specific event
- time_relation: before, after, during, latest, earliest, or null
- confidence from 0 to 1

Use the graph schema only as context for available labels, relationships, and
properties. Do not generate Cypher here.

GRAPH SCHEMA:
{schema.to_prompt()}

CONVERSATION HISTORY:
{history_text or "(none)"}

API-SUPPLIED GROUP ID:
{group_id or "(none)"}

Return JSON only in this shape:
{{
  "intent": "semantic_search",
  "group_id": null,
  "semantic_query": "concise semantic search phrase",
  "target_entities": [],
  "related_terms": [],
  "anchor_event": null,
  "time_relation": null,
  "confidence": 0.0
}}

User question:
{question}
""".strip()

    raw = llm.generate_text(prompt, temperature=0.0)
    logger.debug("KG planner raw LLM response: %s", raw)
    try:
        payload = extract_json_object(raw)
        route_plan = RoutePlan.model_validate(payload)
        if route_plan.intent == "ambiguous" and route_plan.confidence == 0:
            heuristic_plan = _prepare_route_plan(
                _heuristic_route_plan(question),
                question,
                group_id,
            )
            logger.warning(
                "KG planner returned ambiguous zero-confidence plan; using heuristic plan: %s",
                heuristic_plan.model_dump(),
            )
            return RoutePlanningResult(
                route_plan=heuristic_plan,
                debug=PlannerDebug(
                    source="heuristic_after_ambiguous_llm",
                    raw_response=raw,
                    parsed_payload=payload,
                    error="Planner returned ambiguous intent with confidence=0.",
                ),
            )

        route_plan = _prepare_route_plan(route_plan, question, group_id)
        logger.info("KG planner parsed route plan: %s", route_plan.model_dump())
        return RoutePlanningResult(
            route_plan=route_plan,
            debug=PlannerDebug(
                source="llm_json",
                raw_response=raw,
                parsed_payload=payload,
            ),
        )
    except Exception as exc:
        heuristic_plan = _prepare_route_plan(
            _heuristic_route_plan(question),
            question,
            group_id,
        )
        logger.exception(
            "KG planner JSON parsing/validation failed; using heuristic plan: %s",
            heuristic_plan.model_dump(),
        )
        return RoutePlanningResult(
            route_plan=heuristic_plan,
            debug=PlannerDebug(
                source="heuristic_after_planner_error",
                raw_response=raw,
                error=str(exc),
            ),
        )


def choose_strategy(route_plan: RoutePlan) -> str:
    if (
        route_plan.intent == "ambiguous"
        or route_plan.confidence < LOW_CONFIDENCE_THRESHOLD
    ):
        return GRAPHITI_HYBRID_SEARCH

    if route_plan.intent in CYPHER_TEMPLATE_INTENTS:
        return CYPHER_TEMPLATE

    if route_plan.intent in SEMANTIC_EXPAND_INTENTS:
        return GRAPHITI_SEARCH_CYPHER_EXPANSION

    if _effective_group_id(route_plan) and route_plan.intent == "semantic_search":
        return GRAPHITI_SEARCH_CYPHER_EXPANSION

    return GRAPHITI_HYBRID_SEARCH


def build_query_for_strategy(
    *,
    strategy: str,
    route_plan: RoutePlan,
    question: str,
    schema: GraphSchema,
    default_limit: int,
) -> QueryPlan:
    if _is_graphiti_schema(schema):
        if strategy == CYPHER_TEMPLATE:
            return _build_graphiti_template_query(
                schema=schema,
                route_plan=route_plan,
                question=question,
                default_limit=default_limit,
            )
        if strategy in {GRAPHITI_SEARCH_CYPHER_EXPANSION, GRAPHITI_HYBRID_SEARCH}:
            return _build_native_graphiti_query_marker(route_plan)

    return _build_empty_template_query(
        reason="No supported Graphiti schema/template route is available; Cypher text fallback is disabled.",
        default_limit=default_limit,
    )


def _build_native_graphiti_query_marker(route_plan: RoutePlan) -> QueryPlan:
    return QueryPlan(
        cypher="""
MATCH (placeholder)
RETURN 'native_graphiti_search' AS retrieval_mode
LIMIT 0
""".strip(),
        parameters={
            "group_id": _effective_group_id(route_plan),
        },
        reason="Native Graphiti search is required; Cypher text fallback is disabled.",
    )


def _build_empty_template_query(*, reason: str, default_limit: int) -> QueryPlan:
    return QueryPlan(
        cypher="""
MATCH (placeholder)
WHERE false
RETURN placeholder
LIMIT $limit
""".strip(),
        parameters={"limit": default_limit},
        reason=reason,
    )


def _build_graphiti_template_query(
    *,
    schema: GraphSchema,
    route_plan: RoutePlan,
    question: str,
    default_limit: int,
) -> QueryPlan:
    if route_plan.intent == "source_lookup":
        return _build_source_lookup_query(schema, route_plan, question, default_limit)

    if route_plan.intent == "timeline_query":
        return _build_timeline_query(schema, route_plan, question, default_limit)

    if route_plan.intent == "events_after_anchor_event":
        return _build_anchor_event_query(schema, route_plan, question, default_limit)

    if route_plan.intent == "filter_count_query":
        return _build_count_query(route_plan, question)

    if route_plan.intent == "path_explanation":
        return _build_path_query(route_plan, question, default_limit)

    if route_plan.intent == "diagnosis_evidence":
        return _build_diagnosis_evidence_query(
            schema,
            route_plan,
            question,
            default_limit,
        )

    return _build_empty_template_query(
        reason=f"No deterministic Cypher template is available for intent={route_plan.intent}.",
        default_limit=default_limit,
    )


def _build_source_lookup_query(
    schema: GraphSchema,
    route_plan: RoutePlan,
    question: str,
    default_limit: int,
) -> QueryPlan:
    if not (_has_label(schema, "Episodic") and _has_relationship(schema, "MENTIONS")):
        return _build_empty_template_query(
            reason="Source lookup requested, but Episodic/MENTIONS are unavailable.",
            default_limit=default_limit,
        )

    search_text = _search_text(route_plan, question)

    return QueryPlan(
        cypher=f"""
MATCH (episode:Episodic)-[:MENTIONS]->(entity:Entity)
WHERE ($group_id IS NULL OR episode.group_id = $group_id OR entity.group_id = $group_id)
  AND ($query = '' OR toLower(
    coalesce(toString(entity.name), '') + ' ' +
    coalesce(toString(entity.summary), '') + ' ' +
    {_labels_text("entity")} + ' ' +
    coalesce(toString(episode.name), '') + ' ' +
    coalesce(toString(episode.content), '') + ' ' +
    coalesce(toString(episode.source), '') + ' ' +
    coalesce(toString(episode.source_description), '')
  ) CONTAINS toLower($query))
RETURN entity.name AS entity,
       entity.labels AS entity_labels,
       episode.name AS source_episode,
       episode.source AS source,
       episode.source_description AS source_description,
       episode.content AS content,
       episode.valid_at AS valid_at
ORDER BY valid_at
LIMIT $limit
""".strip(),
        parameters={
            "query": search_text,
            "group_id": _effective_group_id(route_plan),
            "limit": default_limit,
        },
        reason="Routed to Cypher template for source/provenance lookup.",
    )


def _build_timeline_query(
    schema: GraphSchema,
    route_plan: RoutePlan,
    question: str,
    default_limit: int,
) -> QueryPlan:
    event_range = _extract_calendar_range(
        route_plan.anchor_event,
        route_plan.semantic_query,
        question,
    )
    if event_range:
        return _build_date_range_timeline_query(
            schema=schema,
            route_plan=route_plan,
            event_start=event_range[0],
            event_end=event_range[1],
            default_limit=default_limit,
        )

    target_terms = _timeline_target_terms(route_plan)
    if _has_label(schema, "Episodic") and _has_relationship(schema, "MENTIONS"):
        return QueryPlan(
            cypher="""
MATCH (episode:Episodic)-[:MENTIONS]->(entity:Entity)
WHERE ($group_id IS NULL OR episode.group_id = $group_id OR entity.group_id = $group_id)
  AND (size($target_terms) = 0 OR any(term IN $target_terms WHERE toLower(
    coalesce(toString(entity.name), '') + ' ' +
    coalesce(toString(entity.summary), '') + ' ' +
    coalesce(toString(episode.name), '') + ' ' +
    coalesce(toString(episode.content), '') + ' ' +
    coalesce(toString(episode.source_description), '')
  ) CONTAINS toLower(term)))
RETURN episode.name AS event,
       episode.content AS content,
       episode.source AS source,
       episode.source_description AS source_description,
       episode.valid_at AS valid_at,
       collect(DISTINCT entity.name) AS mentioned_entities
ORDER BY valid_at
LIMIT $limit
""".strip(),
            parameters={
                "target_terms": target_terms,
                "group_id": _effective_group_id(route_plan),
                "limit": default_limit,
            },
            reason="Routed to Cypher template for patient timeline retrieval.",
        )

    return QueryPlan(
        cypher="""
MATCH (source:Entity)-[relationship:RELATES_TO]->(target:Entity)
WHERE ($group_id IS NULL OR source.group_id = $group_id OR target.group_id = $group_id OR relationship.group_id = $group_id)
  AND (size($target_terms) = 0 OR any(term IN $target_terms WHERE toLower(
    coalesce(toString(source.name), '') + ' ' +
    coalesce(toString(source.summary), '') + ' ' +
    coalesce(toString(target.name), '') + ' ' +
    coalesce(toString(target.summary), '') + ' ' +
    coalesce(toString(relationship.name), '') + ' ' +
    coalesce(toString(relationship.fact), '')
  ) CONTAINS toLower(term)))
RETURN source.name AS source,
       relationship.name AS relationship,
       relationship.fact AS fact,
       target.name AS target,
       relationship.valid_at AS valid_at
ORDER BY valid_at
LIMIT $limit
""".strip(),
        parameters={
            "target_terms": target_terms,
            "group_id": _effective_group_id(route_plan),
            "limit": default_limit,
        },
        reason="Routed to Cypher template for timeline retrieval over dated facts.",
    )


def _build_date_range_timeline_query(
    *,
    schema: GraphSchema,
    route_plan: RoutePlan,
    event_start: str,
    event_end: str,
    default_limit: int,
) -> QueryPlan:
    if _has_label(schema, "Episodic") and _has_relationship(schema, "MENTIONS"):
        return QueryPlan(
            cypher="""
MATCH (episode:Episodic)-[:MENTIONS]->(entity:Entity)
WHERE ($group_id IS NULL OR episode.group_id = $group_id OR entity.group_id = $group_id)
  AND episode.valid_at IS NOT NULL
  AND date(episode.valid_at) >= date($event_start)
  AND date(episode.valid_at) < date($event_end)
RETURN episode.name AS event,
       episode.content AS content,
       episode.source AS source,
       episode.source_description AS source_description,
       episode.valid_at AS valid_at,
       collect(DISTINCT entity.name) AS mentioned_entities
ORDER BY valid_at
LIMIT $limit
""".strip(),
            parameters={
                "event_start": event_start,
                "event_end": event_end,
                "group_id": _effective_group_id(route_plan),
                "limit": default_limit,
            },
            reason="Routed to Cypher template for timeline retrieval over a date range.",
        )

    return QueryPlan(
        cypher="""
MATCH (source:Entity)-[relationship:RELATES_TO]->(target:Entity)
WHERE ($group_id IS NULL OR source.group_id = $group_id OR target.group_id = $group_id OR relationship.group_id = $group_id)
  AND relationship.valid_at IS NOT NULL
  AND date(relationship.valid_at) >= date($event_start)
  AND date(relationship.valid_at) < date($event_end)
RETURN source.name AS source,
       relationship.name AS relationship,
       relationship.fact AS fact,
       target.name AS target,
       relationship.valid_at AS valid_at
ORDER BY valid_at
LIMIT $limit
""".strip(),
        parameters={
            "event_start": event_start,
            "event_end": event_end,
            "group_id": _effective_group_id(route_plan),
            "limit": default_limit,
        },
        reason="Routed to Cypher template for dated facts over a date range.",
    )


def _build_anchor_event_query(
    schema: GraphSchema,
    route_plan: RoutePlan,
    question: str,
    default_limit: int,
) -> QueryPlan:
    anchor = _anchor_text(route_plan, question)
    target = _target_text(route_plan, fallback="")
    time_relation = route_plan.time_relation or "after"

    if _has_label(schema, "Episodic") and _has_relationship(schema, "MENTIONS"):
        return QueryPlan(
            cypher=f"""
MATCH (anchor_episode:Episodic)
WHERE ($group_id IS NULL OR anchor_episode.group_id = $group_id)
  AND anchor_episode.valid_at IS NOT NULL
  AND toLower(
    coalesce(toString(anchor_episode.name), '') + ' ' +
    coalesce(toString(anchor_episode.content), '') + ' ' +
    coalesce(toString(anchor_episode.source_description), '')
  ) CONTAINS toLower($anchor)
WITH anchor_episode
ORDER BY anchor_episode.valid_at
LIMIT 1
MATCH (event_episode:Episodic)-[:MENTIONS]->(entity:Entity)
WHERE ($group_id IS NULL OR event_episode.group_id = $group_id OR entity.group_id = $group_id)
  AND event_episode.valid_at IS NOT NULL
  AND (
    ($time_relation = 'after' AND event_episode.valid_at > anchor_episode.valid_at) OR
    ($time_relation = 'before' AND event_episode.valid_at < anchor_episode.valid_at) OR
    ($time_relation = 'during' AND event_episode.valid_at = anchor_episode.valid_at)
  )
  AND ($target = '' OR toLower(
    coalesce(toString(entity.name), '') + ' ' +
    coalesce(toString(entity.summary), '') + ' ' +
    {_labels_text("entity")} + ' ' +
    coalesce(toString(event_episode.name), '') + ' ' +
    coalesce(toString(event_episode.content), '')
  ) CONTAINS toLower($target))
RETURN anchor_episode.name AS anchor_event,
       anchor_episode.valid_at AS anchor_date,
       event_episode.name AS event,
       event_episode.content AS content,
       event_episode.source AS source,
       event_episode.source_description AS source_description,
       event_episode.valid_at AS event_date,
       collect(DISTINCT entity.name) AS mentioned_entities
ORDER BY event_date
LIMIT $limit
""".strip(),
            parameters={
                "anchor": anchor,
                "target": target,
                "time_relation": time_relation,
                "group_id": _effective_group_id(route_plan),
                "limit": default_limit,
            },
            reason="Routed to Cypher template for events before/after an anchor event.",
        )

    return QueryPlan(
        cypher="""
MATCH (anchor_source:Entity)-[anchor_relationship:RELATES_TO]-(anchor_target:Entity)
WHERE ($group_id IS NULL OR anchor_source.group_id = $group_id OR anchor_target.group_id = $group_id OR anchor_relationship.group_id = $group_id)
  AND anchor_relationship.valid_at IS NOT NULL
  AND toLower(
    coalesce(toString(anchor_source.name), '') + ' ' +
    coalesce(toString(anchor_source.summary), '') + ' ' +
    coalesce(toString(anchor_target.name), '') + ' ' +
    coalesce(toString(anchor_target.summary), '') + ' ' +
    coalesce(toString(anchor_relationship.name), '') + ' ' +
    coalesce(toString(anchor_relationship.fact), '')
  ) CONTAINS toLower($anchor)
WITH anchor_relationship
ORDER BY anchor_relationship.valid_at
LIMIT 1
MATCH (source:Entity)-[relationship:RELATES_TO]->(target:Entity)
WHERE ($group_id IS NULL OR source.group_id = $group_id OR target.group_id = $group_id OR relationship.group_id = $group_id)
  AND relationship.valid_at IS NOT NULL
  AND (
    ($time_relation = 'after' AND relationship.valid_at > anchor_relationship.valid_at) OR
    ($time_relation = 'before' AND relationship.valid_at < anchor_relationship.valid_at) OR
    ($time_relation = 'during' AND relationship.valid_at = anchor_relationship.valid_at)
  )
  AND ($target = '' OR toLower(
    coalesce(toString(source.name), '') + ' ' +
    coalesce(toString(source.summary), '') + ' ' +
    coalesce(toString(target.name), '') + ' ' +
    coalesce(toString(target.summary), '') + ' ' +
    coalesce(toString(relationship.name), '') + ' ' +
    coalesce(toString(relationship.fact), '')
  ) CONTAINS toLower($target))
RETURN source.name AS source,
       relationship.name AS relationship,
       relationship.fact AS fact,
       target.name AS target,
       relationship.valid_at AS event_date
ORDER BY event_date
LIMIT $limit
""".strip(),
        parameters={
            "anchor": anchor,
            "target": target,
            "time_relation": time_relation,
            "group_id": _effective_group_id(route_plan),
            "limit": default_limit,
        },
        reason="Routed to Cypher template for dated facts before/after an anchor fact.",
    )


def _build_count_query(
    route_plan: RoutePlan,
    question: str,
) -> QueryPlan:
    search_text = _search_text(route_plan, question)
    return QueryPlan(
        cypher="""
MATCH (source:Entity)-[relationship:RELATES_TO]->(target:Entity)
WHERE ($group_id IS NULL OR source.group_id = $group_id OR target.group_id = $group_id OR relationship.group_id = $group_id)
  AND ($query = '' OR toLower(
    coalesce(toString(source.name), '') + ' ' +
    coalesce(toString(source.summary), '') + ' ' +
    coalesce(toString(target.name), '') + ' ' +
    coalesce(toString(target.summary), '') + ' ' +
    coalesce(toString(relationship.name), '') + ' ' +
    coalesce(toString(relationship.fact), '')
  ) CONTAINS toLower($query))
RETURN count(DISTINCT relationship) AS count
""".strip(),
        parameters={
            "query": search_text,
            "group_id": _effective_group_id(route_plan),
        },
        reason="Routed to Cypher template for a filtered count query.",
    )


def _build_path_query(
    route_plan: RoutePlan,
    question: str,
    default_limit: int,
) -> QueryPlan:
    left, right = _path_terms(route_plan, question)
    return QueryPlan(
        cypher=f"""
MATCH path = (left:Entity)-[:RELATES_TO*1..2]-(right:Entity)
WHERE ($group_id IS NULL OR left.group_id = $group_id OR right.group_id = $group_id OR any(relationship IN relationships(path) WHERE relationship.group_id = $group_id))
  AND toLower(
    coalesce(toString(left.name), '') + ' ' +
    coalesce(toString(left.summary), '') + ' ' +
    {_labels_text("left")}
  ) CONTAINS toLower($left_query)
  AND toLower(
    coalesce(toString(right.name), '') + ' ' +
    coalesce(toString(right.summary), '') + ' ' +
    {_labels_text("right")}
  ) CONTAINS toLower($right_query)
RETURN [node IN nodes(path) | {{
         name: node.name,
         labels: node.labels,
         summary: node.summary,
         group_id: node.group_id
       }}] AS path_nodes,
       [relationship IN relationships(path) | {{
         name: relationship.name,
         fact: relationship.fact,
         valid_at: relationship.valid_at,
         group_id: relationship.group_id
       }}] AS path_relationships
LIMIT $limit
""".strip(),
        parameters={
            "left_query": left,
            "right_query": right,
            "group_id": _effective_group_id(route_plan),
            "limit": default_limit,
        },
        reason="Routed to Cypher template for relationship/path explanation.",
    )


def _build_diagnosis_evidence_query(
    schema: GraphSchema,
    route_plan: RoutePlan,
    question: str,
    default_limit: int,
) -> QueryPlan:
    search_text = _search_text(route_plan, question)
    if _has_label(schema, "Episodic") and _has_relationship(schema, "MENTIONS"):
        return QueryPlan(
            cypher=f"""
MATCH (source:Entity)-[relationship:RELATES_TO]->(target:Entity)
WHERE ($group_id IS NULL OR source.group_id = $group_id OR target.group_id = $group_id OR relationship.group_id = $group_id)
  AND ($query = '' OR toLower(
    coalesce(toString(source.name), '') + ' ' +
    coalesce(toString(source.summary), '') + ' ' +
    {_labels_text("source")} + ' ' +
    coalesce(toString(target.name), '') + ' ' +
    coalesce(toString(target.summary), '') + ' ' +
    {_labels_text("target")} + ' ' +
    coalesce(toString(relationship.name), '') + ' ' +
    coalesce(toString(relationship.fact), '')
  ) CONTAINS toLower($query))
OPTIONAL MATCH (episode:Episodic)-[:MENTIONS]->(source)
WHERE $group_id IS NULL OR episode.group_id = $group_id
RETURN source.name AS source,
       relationship.name AS relationship,
       relationship.fact AS evidence,
       target.name AS diagnosis_or_target,
       relationship.valid_at AS valid_at,
       collect(DISTINCT {{
         episode: episode.name,
         source: episode.source,
         source_description: episode.source_description,
         content: episode.content,
         valid_at: episode.valid_at
       }}) AS source_episodes
ORDER BY valid_at
LIMIT $limit
""".strip(),
            parameters={
                "query": search_text,
                "group_id": _effective_group_id(route_plan),
                "limit": default_limit,
            },
            reason="Routed to Cypher template for diagnosis evidence with source grounding.",
        )

    return _build_empty_template_query(
        reason="Diagnosis evidence requested, but Episodic/MENTIONS are unavailable.",
        default_limit=default_limit,
    )


def _heuristic_route_plan(question: str) -> RoutePlan:
    lowered = question.lower()
    group_id = _extract_group_id(question)
    anchor_event = _extract_anchor_event(question)
    time_relation = _extract_time_relation(lowered)
    target_entities = _extract_target_terms(question, anchor_event)
    related_terms: list[str] = []

    if any(term in lowered for term in ("timeline", "chronology", "chronological")):
        intent = "timeline_query"
    elif _looks_like_medication_question(lowered):
        intent = "patient_specific_search"
    elif _looks_like_identity_question(lowered):
        intent = "patient_specific_search"
    elif time_relation in {"after", "before", "during"} and anchor_event:
        intent = "events_after_anchor_event"
    elif any(term in lowered for term in ("which document", "source", "mentioned", "report", "note")):
        intent = "source_lookup"
    elif re.search(r"\b(how many|count|number of)\b", lowered):
        intent = "filter_count_query"
    elif any(term in lowered for term in ("path", "connected", "connection", "relationship between", "link between")):
        intent = "path_explanation"
    elif any(term in lowered for term in ("why", "evidence", "diagnosis", "diagnosed")):
        intent = "diagnosis_evidence"
    elif any(term in lowered for term in ("summary", "summarize", "overview")):
        intent = "patient_summary"
    elif any(term in lowered for term in ("compare", "versus", " vs ", "difference between")):
        intent = "comparison_query"
    elif group_id:
        intent = "patient_specific_search"
    else:
        intent = "semantic_search"

    semantic_query = " ".join(target_entities).strip() or question.strip()
    return RoutePlan(
        intent=intent,
        group_id=group_id,
        semantic_query=semantic_query,
        target_entities=target_entities,
        related_terms=related_terms,
        anchor_event=anchor_event,
        time_relation=time_relation,
        confidence=0.55,
    )


def _prepare_route_plan(
    route_plan: RoutePlan,
    question: str,
    group_id: str | None,
) -> RoutePlan:
    route_plan = _with_group_id(route_plan, group_id)
    route_plan = _move_query_hints_out_of_target_entities(route_plan, question)
    return _mark_first_person_questions_as_patient_specific(route_plan, question)


def _move_query_hints_out_of_target_entities(
    route_plan: RoutePlan,
    question: str,
) -> RoutePlan:
    explicit_entities: list[str] = []
    related_terms = list(route_plan.related_terms)
    for entity in route_plan.target_entities:
        if _looks_like_explicit_entity_name(entity, question):
            explicit_entities.append(entity)
        else:
            related_terms.append(entity)

    semantic_query = route_plan.semantic_query
    if not semantic_query:
        semantic_query = " ".join([*explicit_entities, *related_terms]).strip() or question.strip()

    return route_plan.model_copy(
        update={
            "target_entities": _dedupe_terms(explicit_entities),
            "related_terms": _dedupe_terms(related_terms),
            "semantic_query": semantic_query,
        }
    )


def _mark_first_person_questions_as_patient_specific(
    route_plan: RoutePlan,
    question: str,
) -> RoutePlan:
    lowered = question.lower()
    if not _looks_like_first_person_question(lowered):
        return route_plan
    if not (_looks_like_medication_question(lowered) or _looks_like_identity_question(lowered)):
        return route_plan

    related_terms = _dedupe_terms(route_plan.related_terms)
    semantic_query = route_plan.semantic_query or question.strip()
    return route_plan.model_copy(
        update={
            "intent": "patient_specific_search",
            "semantic_query": semantic_query,
            "related_terms": related_terms,
            "confidence": max(route_plan.confidence, 0.7),
        }
    )


def _with_group_id(route_plan: RoutePlan, group_id: str | None) -> RoutePlan:
    explicit_group_id = _normalize_id(group_id)
    if not explicit_group_id:
        return route_plan

    return route_plan.model_copy(update={"group_id": explicit_group_id})


def _effective_group_id(route_plan: RoutePlan) -> str | None:
    return route_plan.group_id


def _search_text(
    route_plan: RoutePlan,
    question: str,
    *,
    empty_if_no_terms: bool = False,
) -> str:
    parts = [
        route_plan.semantic_query or "",
        *_string_values(route_plan.target_entities),
        *_string_values(route_plan.related_terms),
        route_plan.anchor_event or "",
    ]
    text = _join_unique_terms(parts)
    if text:
        return text
    return "" if empty_if_no_terms else question.strip()


def _target_text(route_plan: RoutePlan, *, fallback: str) -> str:
    parts = [
        *_string_values(route_plan.target_entities),
    ]
    text = " ".join(part for part in parts if part).strip()
    return text or fallback


def _timeline_target_terms(route_plan: RoutePlan) -> list[str]:
    terms: list[str] = []
    for entity in route_plan.target_entities:
        stripped = entity.strip()
        if not stripped:
            continue
        terms.append(stripped)
        terms.extend(
            part
            for part in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", stripped)
            if part.lower() != stripped.lower()
        )
    return _dedupe_preserve_case(terms)[:12]


def _anchor_text(route_plan: RoutePlan, question: str) -> str:
    return (route_plan.anchor_event or _extract_anchor_event(question) or question).strip()


def _path_terms(route_plan: RoutePlan, question: str) -> tuple[str, str]:
    terms = _string_values(route_plan.target_entities)
    if len(terms) >= 2:
        return terms[0], terms[1]

    between_match = re.search(
        r"\bbetween\s+(.+?)\s+(?:and|&)\s+(.+?)(?:[?.]|$)",
        question,
        flags=re.IGNORECASE,
    )
    if between_match:
        return between_match.group(1).strip(), between_match.group(2).strip()

    if len(terms) == 1:
        return terms[0], terms[0]

    return question.strip(), question.strip()


def _extract_group_id(question: str) -> str | None:
    explicit = re.search(
        r"\b(?:group[_\s-]*id|groub[_\s-]*id)\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9_.:-]{0,199})\b",
        question,
        flags=re.IGNORECASE,
    )
    if explicit:
        return _normalize_id(explicit.group(1))
    return None


def _looks_like_medication_question(lowered_question: str) -> bool:
    return bool(
        re.search(
            r"\b(medication|medications|medicine|medicines|drug|drugs|prescription|prescriptions|dose|dosage|take|therapy|treatment)\b",
            lowered_question,
        )
    )


def _looks_like_identity_question(lowered_question: str) -> bool:
    return bool(
        re.search(
            r"\b(what(?:'s| is)? my name|who am i|patient name|my identity|identifier)\b",
            lowered_question,
        )
    )


def _looks_like_first_person_question(lowered_question: str) -> bool:
    return bool(re.search(r"\b(i|me|my|mine|myself)\b", lowered_question))


def _looks_like_explicit_entity_name(term: str, question: str) -> bool:
    stripped = term.strip()
    if not stripped or len(stripped) <= 2:
        return False
    if stripped.startswith(("'", '"')) and stripped.endswith(("'", '"')):
        return True
    if re.search(r"\d", stripped):
        return True
    if "-" in stripped or "/" in stripped or "_" in stripped:
        return True
    if stripped.isupper() and len(stripped) > 2:
        return True
    if any(character.isupper() for character in stripped[1:]):
        return True
    if re.search(rf"\b{re.escape(stripped)}\b", question) and any(
        character.isupper() for character in stripped
    ):
        return True
    return False


def _dedupe_terms(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _dedupe_preserve_case(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = str(value).strip()
        normalized = stripped.lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(stripped)
    return deduped


def _join_unique_terms(values: list[str]) -> str:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        stripped = str(value).strip()
        if not stripped:
            continue
        key = stripped.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(stripped)
    return " ".join(deduped)


def _normalize_id(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _extract_time_relation(lowered_question: str) -> str | None:
    if re.search(r"\b(after|following|since)\b", lowered_question):
        return "after"
    if re.search(r"\b(before|prior to|preceding)\b", lowered_question):
        return "before"
    if re.search(r"\bduring\b", lowered_question):
        return "during"
    if re.search(r"\b(latest|most recent|newest)\b", lowered_question):
        return "latest"
    if re.search(r"\b(earliest|first|oldest)\b", lowered_question):
        return "earliest"
    return None


def _extract_calendar_range(*values: str | None) -> tuple[str, str] | None:
    for value in values:
        if not value:
            continue
        for extractor in (
            _extract_iso_calendar_range,
            _extract_named_day_calendar_range,
            _extract_named_month_calendar_range,
            _extract_year_calendar_range,
        ):
            date_range = extractor(value)
            if date_range:
                return date_range
    return None


def _extract_iso_calendar_range(value: str) -> tuple[str, str] | None:
    match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", value)
    if not match:
        return None
    year, month, day = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return _day_range(year, month, day)


def _extract_named_day_calendar_range(value: str) -> tuple[str, str] | None:
    match = re.search(
        r"\b("
        r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?"
        r")\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(\d{4})\b",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    month = _month_number(match.group(1))
    day = int(match.group(2))
    year = int(match.group(3))
    return _day_range(year, month, day)


def _extract_named_month_calendar_range(value: str) -> tuple[str, str] | None:
    match = re.search(
        r"\b("
        r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?"
        r")[,]?\s+(\d{4})\b",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    month = _month_number(match.group(1))
    year = int(match.group(2))
    return _month_range(year, month)


def _extract_year_calendar_range(value: str) -> tuple[str, str] | None:
    match = re.search(r"\b(19\d{2}|20\d{2}|21\d{2})\b", value)
    if not match:
        return None
    year = int(match.group(1))
    return _year_range(year)


def _month_number(value: str) -> int:
    month_names = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }
    return month_names[value.lower()]


def _day_range(year: int, month: int, day: int) -> tuple[str, str] | None:
    try:
        start = date(year, month, day)
        end = start + timedelta(days=1)
    except ValueError:
        return None
    return start.isoformat(), end.isoformat()


def _month_range(year: int, month: int) -> tuple[str, str] | None:
    try:
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1)
        else:
            end = date(year, month + 1, 1)
    except ValueError:
        return None
    return start.isoformat(), end.isoformat()


def _year_range(year: int) -> tuple[str, str] | None:
    try:
        return date(year, 1, 1).isoformat(), date(year + 1, 1, 1).isoformat()
    except ValueError:
        return None


def _extract_anchor_event(question: str) -> str | None:
    match = re.search(
        r"\b(?:after|following|since|before|prior to|during)\s+(?:the\s+)?([^?.,]+)",
        question,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    anchor = match.group(1).strip()
    anchor = re.split(r"\b(?:what|which|was|were|did|does|do)\b", anchor, maxsplit=1, flags=re.IGNORECASE)[0]
    return anchor.strip() or None


def _extract_target_terms(question: str, anchor_event: str | None) -> list[str]:
    quoted = re.findall(r'"([^"]+)"|' + r"'([^']+)'", question)
    terms = [left or right for left, right in quoted if (left or right)]

    about_match = re.search(
        r"\b(?:about|related to|regarding|for)\s+([^?.,]+)",
        question,
        flags=re.IGNORECASE,
    )
    if about_match:
        terms.append(about_match.group(1).strip())

    if anchor_event:
        terms = [term for term in terms if term.lower() != anchor_event.lower()]

    deduped: list[str] = []
    for term in terms:
        if term and term not in deduped:
            deduped.append(term)
    return deduped


def _string_values(values: list[Any]) -> list[str]:
    return [str(value).strip() for value in values if str(value).strip()]


def _is_graphiti_schema(schema: GraphSchema) -> bool:
    return _has_label(schema, "Entity") and _has_relationship(schema, "RELATES_TO")


def _has_label(schema: GraphSchema, label: str) -> bool:
    return label in schema.labels


def _has_relationship(schema: GraphSchema, relationship_type: str) -> bool:
    return relationship_type in schema.relationship_types


def _labels_text(variable: str) -> str:
    return (
        f"reduce(label_text = '', label IN coalesce({variable}.labels, []) | "
        "label_text + ' ' + toString(label))"
    )


