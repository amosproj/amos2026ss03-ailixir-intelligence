"""
Singleton Graphiti client for the chat pipeline (retrieval-only).

Adapted from workers/connections/graphiti_client.py with two differences:
  1. build_indices=False — indices were already built by the ingestion worker.
     Calling build_indices_and_constraints() on every API cold-start wastes
     ~2s and can cause index contention with a running worker.
  2. Uses plain GeminiClient / GeminiRerankerClient instead of the paced
     wrappers — chat queries are user-initiated one at a time, not the burst-y
     parallel ingestion that needs rate-limiting.

RRF reranking is used instead of cross-encoder to keep per-request latency
low (avoids the extra Gemini call inside Graphiti's reranker). The answering
step's LLM handles relevance selection across the top-4 facts anyway.

Required env vars:
  VERTEX_PROJECT         — GCP project ID
  NEO4J_URI              — neo4j+s:// or bolt:// URI
  NEO4J_USER             — database user
  NEO4J_PASSWORD         — database password

Optional:
  VERTEX_LOCATION        — default: us-central1
  VERTEX_LLM_MODEL       — default: gemini-2.5-flash
  VERTEX_EMBEDDING_MODEL — default: text-embedding-005
  NEO4J_DATABASE         — default: neo4j

Auth: Application Default Credentials (ADC).
"""

from __future__ import annotations

import asyncio
import logging
import os

from google import genai
from graphiti_core import Graphiti
from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.gemini_client import GeminiClient

_log = logging.getLogger(__name__)

_graphiti: Graphiti | None = None
_init_lock = asyncio.Lock()

_DEFAULT_LLM_MODEL       = "gemini-2.5-flash"
_DEFAULT_EMBEDDING_MODEL = "text-embedding-005"
_DEFAULT_LOCATION        = "us-central1"
_EMBEDDING_DIM           = 768


async def get_graphiti() -> Graphiti:
    """Return the shared Graphiti instance, initialising it on first call."""
    global _graphiti
    async with _init_lock:
        if _graphiti is None:
            project         = os.environ["VERTEX_PROJECT"]
            location        = os.environ.get("VERTEX_LOCATION",        _DEFAULT_LOCATION)
            llm_model       = os.environ.get("VERTEX_LLM_MODEL",       _DEFAULT_LLM_MODEL)
            embedding_model = os.environ.get("VERTEX_EMBEDDING_MODEL", _DEFAULT_EMBEDDING_MODEL)
            neo4j_database  = os.environ.get("NEO4J_DATABASE",         "neo4j")

            vertex_client = genai.Client(vertexai=True, project=project, location=location)

            llm_config = LLMConfig(
                api_key="vertex-ai-adc",
                model=llm_model,
                small_model=llm_model,
            )

            _graphiti = Graphiti(
                graph_driver=Neo4jDriver(
                    os.environ["NEO4J_URI"],
                    os.environ["NEO4J_USER"],
                    os.environ["NEO4J_PASSWORD"],
                    database=neo4j_database,
                ),
                llm_client=GeminiClient(config=llm_config, client=vertex_client),
                embedder=GeminiEmbedder(
                    config=GeminiEmbedderConfig(
                        embedding_model=embedding_model,
                        embedding_dim=_EMBEDDING_DIM,
                    ),
                    client=vertex_client,
                ),
                cross_encoder=GeminiRerankerClient(config=llm_config, client=vertex_client),
            )
            _log.info(
                "graphiti_client_created project=%s llm=%s embedding=%s",
                project, llm_model, embedding_model,
            )
    return _graphiti


async def close_graphiti() -> None:
    """Close the Neo4j connection. Call from FastAPI's lifespan shutdown."""
    global _graphiti
    if _graphiti is not None:
        await _graphiti.close()
        _graphiti = None
        _log.info("graphiti_client_closed")
