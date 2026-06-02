"""
Graphiti client factory for the pipeline_refinement playground.

Uses Vertex AI (Gemini) for LLM + embeddings, Neo4j for graph storage.
Mirrors the pattern in Backend/workers/connections/graphiti_client.py.

Auth: Application Default Credentials — run `gcloud auth application-default login` once.

Env vars (set in ai-playground/.env):
  NEO4J_URI              — bolt://localhost:7687
  NEO4J_USER             — neo4j
  NEO4J_PASSWORD         — your password
  NEO4J_DATABASE         — database name (default: neo4j)
  VERTEX_PROJECT         — GCP project ID
  VERTEX_LOCATION        — region (default: us-central1)
  VERTEX_LLM_MODEL       — Gemini model (default: gemini-2.5-flash)
  VERTEX_EMBEDDING_MODEL — embedding model (default: text-embedding-005)
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

_HERE = Path(__file__).resolve().parent
load_dotenv(dotenv_path=_HERE.parent / ".env")

_DEFAULT_LLM_MODEL       = "gemini-2.5-flash"
_DEFAULT_EMBEDDING_MODEL = "text-embedding-005"
_DEFAULT_LOCATION        = "us-central1"
_EMBEDDING_DIM           = 768


async def create_graphiti(build_indices: bool = True) -> Graphiti:
    """
    Create and return a ready-to-use Graphiti instance.

    On first call (build_indices=True) it will run build_indices_and_constraints()
    which is idempotent — safe to call every time.
    """
    project  = os.environ.get("VERTEX_PROJECT", "")
    location = os.environ.get("VERTEX_LOCATION", _DEFAULT_LOCATION)
    llm_model       = os.environ.get("VERTEX_LLM_MODEL",       _DEFAULT_LLM_MODEL)
    embedding_model = os.environ.get("VERTEX_EMBEDDING_MODEL", _DEFAULT_EMBEDDING_MODEL)
    neo4j_database  = os.environ.get("NEO4J_DATABASE", "neo4j")

    if not project:
        raise EnvironmentError(
            "VERTEX_PROJECT is not set. Add it to ai-playground/.env"
        )
    for var in ("NEO4J_URI", "NEO4J_USER", "NEO4J_PASSWORD"):
        if not os.environ.get(var):
            raise EnvironmentError(
                f"{var} is not set. Add it to ai-playground/.env\n"
                "Example: NEO4J_URI=bolt://localhost:7687"
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


def neo4j_journey_query(user_id: str) -> str:
    """
    View the full patient journey graph (entity nodes only — no episodic infrastructure).

    NOTE: Edge labels show numbers by default in Neo4j Browser.
    To see relationship names (HAS_DIAGNOSIS, TREATED_BY etc.) instead:
      1. Run the query
      2. Click the paint bucket icon (bottom-left of graph panel)
      3. Under Relationships → change Caption to "name"

    Open http://localhost:7474 and paste this query.
    """
    return (
        f"MATCH (n:Entity)-[r]-(m:Entity) "
        f"WHERE n.group_id = '{user_id}' "
        f"RETURN n, r, m "
        f"LIMIT 300"
    )


def neo4j_current_facts_query(user_id: str) -> str:
    """
    Current (non-expired) facts only.
    Shows the up-to-date state — superseded facts from earlier documents are hidden.
    This is the temporal view: only what is still valid today.
    """
    return (
        f"MATCH (n:Entity)-[r]-(m:Entity) "
        f"WHERE n.group_id = '{user_id}' "
        f"AND (r.invalid_at IS NULL) "
        f"RETURN n, r, m "
        f"LIMIT 300"
    )


def neo4j_facts_table_query(user_id: str) -> str:
    """
    Return all facts as a readable table: source → relation name → target → fact text.
    Paste in Neo4j Browser and switch to Table view to see semantic relationships.
    """
    return (
        f"MATCH (n:Entity)-[r]-(m:Entity) "
        f"WHERE n.group_id = '{user_id}' "
        f"AND (r.invalid_at IS NULL) "
        f"RETURN n.name AS source, r.name AS relation, m.name AS target, r.fact AS fact "
        f"ORDER BY relation "
        f"LIMIT 300"
    )
