from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from kg_chat.config import AppConfig, load_config
from kg_chat.graphiti_search import (
    GraphitiSearchClient,
    GraphitiSearchConfigurationError,
)
from kg_chat.llm import LlmConfigurationError, build_llm_client
from kg_chat.models import ChatRequest, ChatResponse, QueryRequest, QueryResponse
from kg_chat.neo4j_client import Neo4jConfigurationError, Neo4jGraphClient
from kg_chat.query import QueryValidationError
from kg_chat.retriever import GraphChatService


BASE_DIR = Path(__file__).resolve().parent
_startup_config = load_config(BASE_DIR)

logging.basicConfig(
    level=os.environ.get("KG_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logging.getLogger("kg_chat").setLevel(os.environ.get("KG_LOG_LEVEL", "INFO").upper())


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config(BASE_DIR)
    app.state.config = config
    app.state.startup_errors = []
    app.state.graph_client = None
    app.state.graphiti_search = None
    app.state.service = None

    graph_client = _build_graph_client(config, app.state.startup_errors)
    app.state.graph_client = graph_client
    graphiti_search = _build_graphiti_search(config, app.state.startup_errors)
    app.state.graphiti_search = graphiti_search
    llm = _build_llm(config, app.state.startup_errors)

    if graph_client and llm:
        app.state.service = GraphChatService(
            config=config,
            llm=llm,
            graph_client=graph_client,
            graphiti_search=graphiti_search,
        )

    try:
        yield
    finally:
        if graph_client:
            graph_client.close()
        if graphiti_search:
            await graphiti_search.aclose()


app = FastAPI(
    title="AIlixir Knowledge Graph Chat API",
    description=(
        "Chat with an existing Neo4j knowledge graph using startup schema "
        "introspection, structured query planning, strategy routing, "
        "read-only Cypher validation, and grounded answer generation."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_startup_config.cors_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Ops"])
def health() -> dict[str, Any]:
    config: AppConfig = app.state.config
    service: GraphChatService | None = app.state.service
    graph_client: Neo4jGraphClient | None = app.state.graph_client
    graphiti_search: GraphitiSearchClient | None = app.state.graphiti_search
    schema = graph_client.schema if graph_client else None
    return {
        "status": "ok" if service else "degraded",
        "neo4j_configured": config.neo4j_configured,
        "graphiti_search_configured": config.graphiti_search_configured,
        "graphiti_search_available": graphiti_search is not None,
        "llm_provider": config.llm_provider,
        "llm_configured": config.llm_configured,
        "schema_cached": schema is not None,
        "schema_refreshed_at": schema.refreshed_at if schema else None,
        "startup_errors": app.state.startup_errors,
    }


@app.get("/schema", tags=["Knowledge Graph"])
def schema() -> dict[str, Any]:
    graph_client = _require_graph_client()
    return graph_client.get_schema().to_dict()


@app.post("/schema/refresh", tags=["Knowledge Graph"])
def refresh_schema() -> dict[str, Any]:
    graph_client = _require_graph_client()
    return graph_client.refresh_schema().to_dict()


@app.post("/query", response_model=QueryResponse, tags=["Knowledge Graph"])
def generate_query(body: QueryRequest) -> QueryResponse:
    service = _require_service()
    try:
        return service.generate_query_only(
            question=body.question,
            session_id=body.session_id,
            group_id=body.group_id,
        )
    except QueryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
def chat(body: ChatRequest) -> ChatResponse:
    service = _require_service()
    try:
        return service.chat(
            question=body.question,
            session_id=body.session_id,
            group_id=body.group_id,
            include_debug=body.include_debug,
        )
    except QueryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _build_graph_client(
    config: AppConfig,
    startup_errors: list[str],
) -> Neo4jGraphClient | None:
    if not config.neo4j_configured:
        startup_errors.append(
            "Neo4j is not configured. Set NEO4J_URI, NEO4J_USER or "
            "NEO4J_USERNAME, and NEO4J_PASSWORD."
        )
        return None

    try:
        graph_client = Neo4jGraphClient(config)
        graph_client.verify_connectivity()
        graph_client.refresh_schema()
        return graph_client
    except Neo4jConfigurationError as exc:
        startup_errors.append(str(exc))
    except Exception as exc:
        startup_errors.append(f"Could not connect to Neo4j or cache schema: {exc}")
    return None


def _build_llm(config: AppConfig, startup_errors: list[str]):
    if not config.llm_configured:
        startup_errors.append(
            "LLM is not configured. Use LLM_PROVIDER=vertex with Google ADC, "
            "or LLM_PROVIDER=google-genai with GEMINI_API_KEY."
        )
        return None

    try:
        return build_llm_client(config)
    except LlmConfigurationError as exc:
        startup_errors.append(str(exc))
    except Exception as exc:
        startup_errors.append(f"Could not initialise LLM client: {exc}")
    return None


def _build_graphiti_search(
    config: AppConfig,
    startup_errors: list[str],
) -> GraphitiSearchClient | None:
    if not config.graphiti_search_enabled:
        return None

    if not config.graphiti_search_configured:
        startup_errors.append(
            "Native Graphiti search is not configured. Set OPENAI_API_KEY, "
            "or set GRAPHITI_SEARCH_ENABLED=false to use Cypher fallback only."
        )
        return None

    try:
        return GraphitiSearchClient(config)
    except GraphitiSearchConfigurationError as exc:
        startup_errors.append(str(exc))
    except Exception as exc:
        startup_errors.append(f"Could not initialise native Graphiti search: {exc}")
    return None


def _require_graph_client() -> Neo4jGraphClient:
    graph_client: Neo4jGraphClient | None = app.state.graph_client
    if not graph_client:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Neo4j graph client is not available.",
                "startup_errors": app.state.startup_errors,
            },
        )
    return graph_client


def _require_service() -> GraphChatService:
    service: GraphChatService | None = app.state.service
    if not service:
        raise HTTPException(
            status_code=503,
            detail={
                "message": "Graph chat service is not ready.",
                "startup_errors": app.state.startup_errors,
            },
        )
    return service
