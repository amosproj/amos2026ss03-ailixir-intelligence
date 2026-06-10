from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default="default-session", min_length=1, max_length=200)
    include_debug: bool = Field(default=False)


class QueryPlan(BaseModel):
    cypher: str = Field(..., min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="")


class QueryDebug(BaseModel):
    generated_cypher: str
    executed_cypher: str
    parameters: dict[str, Any]
    rows: list[dict[str, Any]]
    schema_refreshed_at: str | None = None
    reason: str = ""


class ChatResponse(BaseModel):
    answer: str
    session_id: str
    debug: QueryDebug | None = None


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default="default-session", min_length=1, max_length=200)


class QueryResponse(BaseModel):
    cypher: str
    parameters: dict[str, Any]
    reason: str = ""

