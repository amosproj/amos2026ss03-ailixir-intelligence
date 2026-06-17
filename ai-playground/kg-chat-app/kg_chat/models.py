from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default="default-session", min_length=1, max_length=200)
    group_id: str | None = Field(default=None, max_length=200)
    include_debug: bool = Field(default=False)


class QueryPlan(BaseModel):
    cypher: str = Field(..., min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="")


class RoutePlan(BaseModel):
    intent: str = Field(default="ambiguous")
    group_id: str | None = None
    semantic_query: str | None = None
    target_entities: list[str] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)
    anchor_event: str | None = None
    time_relation: str | None = None
    confidence: float = Field(default=0.0)

    @model_validator(mode="before")
    @classmethod
    def normalize_planner_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        if "target_entities" not in payload and "target_entity" in payload:
            target_entity = payload.get("target_entity")
            if isinstance(target_entity, list):
                payload["target_entities"] = target_entity
            elif target_entity:
                payload["target_entities"] = [target_entity]

        if "confidence" not in payload and payload.get("intent"):
            payload["confidence"] = 0.5

        return payload

    @field_validator("intent")
    @classmethod
    def normalize_intent(cls, value: str) -> str:
        allowed = {
            "semantic_search",
            "patient_specific_search",
            "timeline_query",
            "events_after_anchor_event",
            "diagnosis_evidence",
            "source_lookup",
            "path_explanation",
            "filter_count_query",
            "comparison_query",
            "patient_summary",
            "ambiguous",
        }
        normalized = (value or "ambiguous").strip().lower()
        return normalized if normalized in allowed else "ambiguous"

    @field_validator("target_entities", "related_terms", mode="before")
    @classmethod
    def normalize_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    @field_validator("group_id")
    @classmethod
    def normalize_optional_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("semantic_query")
    @classmethod
    def normalize_semantic_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("time_relation")
    @classmethod
    def normalize_time_relation(cls, value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip().lower()
        allowed = {"before", "after", "during", "latest", "earliest"}
        return normalized if normalized in allowed else None

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, value: float) -> float:
        return max(0.0, min(1.0, float(value or 0.0)))


class QueryDebug(BaseModel):
    generated_cypher: str
    executed_cypher: str
    parameters: dict[str, Any]
    rows: list[dict[str, Any]]
    schema_refreshed_at: str | None = None
    reason: str = ""
    intent: str = ""
    strategy: str = ""
    route_plan: dict[str, Any] | None = None
    planner_debug: dict[str, Any] | None = None
    retrieval_debug: dict[str, Any] | None = None
    graphiti_search_results: list[dict[str, Any]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    debug: QueryDebug | None = None


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default="default-session", min_length=1, max_length=200)
    group_id: str | None = Field(default=None, max_length=200)


class QueryResponse(BaseModel):
    cypher: str
    parameters: dict[str, Any]
    reason: str = ""
    intent: str = ""
    strategy: str = ""
    route_plan: dict[str, Any] | None = None
    planner_debug: dict[str, Any] | None = None
    retrieval_debug: dict[str, Any] | None = None
    graphiti_search_results: list[dict[str, Any]] = Field(default_factory=list)
