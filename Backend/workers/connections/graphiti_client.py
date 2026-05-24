"""
Singleton Graphiti client.

Graphiti wraps Neo4j + Vertex AI (Gemini) into a temporal knowledge-graph client.
The instance is created once and reused across all pipeline invocations.

Call build_indices() once at app startup (idempotent).
Call close_graphiti() on app shutdown.

Configure via:
  NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
  VERTEX_PROJECT         — GCP project ID
  VERTEX_LOCATION        — region, e.g. "us-central1"   (default: us-central1)
  VERTEX_LLM_MODEL       — Gemini model for extraction   (default: gemini-2.0-flash-001)
  VERTEX_EMBEDDING_MODEL — embedding model               (default: text-embedding-005)

Authentication uses Application Default Credentials (ADC):
  - Local:  run `gcloud auth application-default login` once
  - GCP:    the service account attached to the Cloud Run instance is used automatically
  The service account needs the `roles/aiplatform.user` IAM role.
"""

from __future__ import annotations

import asyncio
import logging
import os

from google import genai
from graphiti_core import Graphiti
from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.gemini_client import GeminiClient

_log = logging.getLogger(__name__)

_graphiti: Graphiti | None = None
_indices_built: bool = False
_init_lock = asyncio.Lock()

_DEFAULT_LLM_MODEL = "gemini-2.0-flash-001"
_DEFAULT_EMBEDDING_MODEL = "text-embedding-005"
_DEFAULT_LOCATION = "us-central1"


async def get_graphiti() -> Graphiti:
    """Return the shared Graphiti instance, initialising it on first call."""
    global _graphiti, _indices_built
    async with _init_lock:
        if _graphiti is None:
            project = os.environ["VERTEX_PROJECT"]
            location = os.environ.get("VERTEX_LOCATION", _DEFAULT_LOCATION)
            llm_model = os.environ.get("VERTEX_LLM_MODEL", _DEFAULT_LLM_MODEL)
            embedding_model = os.environ.get("VERTEX_EMBEDDING_MODEL", _DEFAULT_EMBEDDING_MODEL)

            # Uses ADC — no API key needed. Locally: gcloud auth application-default login.
            # On GCP: the Cloud Run service account is picked up automatically.
            vertex_client = genai.Client(
                vertexai=True,
                project=project,
                location=location,
            )

            _graphiti = Graphiti(
                os.environ["NEO4J_URI"],
                os.environ["NEO4J_USER"],
                os.environ["NEO4J_PASSWORD"],
                llm_client=GeminiClient(
                    config=LLMConfig(
                        api_key="vertex-ai-adc",  # placeholder; auth via ADC, not API key
                        model=llm_model,
                        small_model=llm_model,
                    ),
                    client=vertex_client,
                ),
                embedder=GeminiEmbedder(
                    config=GeminiEmbedderConfig(embedding_model=embedding_model),
                    client=vertex_client,
                ),
                cross_encoder=GeminiRerankerClient(
                    config=LLMConfig(
                        api_key="vertex-ai-adc",
                        model=llm_model,
                        small_model=llm_model,
                    ),
                    client=vertex_client,
                ),
            )
            _log.info(
                "graphiti_client_created project=%s location=%s llm=%s embedding=%s",
                project,
                location,
                llm_model,
                embedding_model,
            )
        if not _indices_built:
            await _graphiti.build_indices_and_constraints()
            _indices_built = True
            _log.info("graphiti_indices_ready")
    return _graphiti


async def close_graphiti() -> None:
    global _graphiti, _indices_built
    if _graphiti is not None:
        await _graphiti.close()
        _graphiti = None
        _indices_built = False
        _log.info("graphiti_client_closed")
