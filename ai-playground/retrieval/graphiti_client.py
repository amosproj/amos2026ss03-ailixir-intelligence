"""
Graphiti client factory for the retrieval pipeline.

Self-contained module — mirrors pipeline_refinement/graphiti_client.py but
sets build_indices=False by default (indices already exist from ingestion).

Loads env from ai-playground/.env (one directory above this file).

Env vars required:
  VERTEX_PROJECT         — GCP project ID
  NEO4J_URI              — bolt://localhost:7687  (local Docker)
  NEO4J_USER             — neo4j
  NEO4J_PASSWORD         — your password

Optional:
  VERTEX_LOCATION        — default: us-central1
  VERTEX_LLM_MODEL       — default: gemini-2.5-flash
  VERTEX_EMBEDDING_MODEL — default: text-embedding-005
  NEO4J_DATABASE         — default: neo4j

Auth: Application Default Credentials (ADC).
  Local:  gcloud auth application-default login
  GCP:    service account on Cloud Run is picked up automatically
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from graphiti_core import Graphiti
from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.gemini_client import GeminiClient

_HERE = Path(__file__).resolve().parent           # retrieval/
load_dotenv(dotenv_path=_HERE.parent / ".env")    # ai-playground/.env

_DEFAULT_LLM_MODEL       = "gemini-2.5-flash"
_DEFAULT_EMBEDDING_MODEL = "text-embedding-005"
_DEFAULT_LOCATION        = "us-central1"
_EMBEDDING_DIM           = 768


async def create_graphiti(build_indices: bool = False) -> Graphiti:
    """
    Return a ready-to-use Graphiti instance connected to local Neo4j.

    build_indices=False: indices were already created by the ingestion pipeline,
    so we skip the idempotent re-build to keep retrieval startup fast.
    Set to True only if you are starting from a fresh Neo4j database.
    """
    project         = os.environ.get("VERTEX_PROJECT", "")
    location        = os.environ.get("VERTEX_LOCATION",        _DEFAULT_LOCATION)
    llm_model       = os.environ.get("VERTEX_LLM_MODEL",       _DEFAULT_LLM_MODEL)
    embedding_model = os.environ.get("VERTEX_EMBEDDING_MODEL", _DEFAULT_EMBEDDING_MODEL)
    neo4j_database  = os.environ.get("NEO4J_DATABASE",         "neo4j")

    if not project:
        raise EnvironmentError(
            "VERTEX_PROJECT is not set. Add it to ai-playground/.env\n"
            "  VERTEX_PROJECT=your-gcp-project-id"
        )
    for var in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"):
        if not os.environ.get(var):
            raise EnvironmentError(
                f"{var} is not set. Add it to ai-playground/.env\n"
                f"  Example: NEO4J_URI=bolt://localhost:7687"
            )

    vertex_client = genai.Client(vertexai=True, project=project, location=location)

    llm_config = LLMConfig(
        api_key="vertex-ai-adc",   # placeholder; actual auth is via ADC
        model=llm_model,
        small_model=llm_model,
    )

    graphiti = Graphiti(
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

    if build_indices:
        await graphiti.build_indices_and_constraints()

    return graphiti
