"""
Singleton Vertex AI Ranking API client for the chat pipeline (paper retrieval).

The Ranking API is Vertex AI Search's stateless cross-encoder reranker
(`discoveryengine.googleapis.com`, method `rankingConfigs.rank`) — it takes a
query plus a small candidate list and returns precise relevance scores,
unlike the cosine-distance ordering from vector search alone. There is
nothing to index ahead of time; every call is self-contained.

Docs: https://docs.cloud.google.com/generative-ai-app-builder/docs/ranking

Required env vars:
  VERTEX_PROJECT — GCP project ID (same var the chat pipeline already uses)

Optional:
  VERTEX_RANKING_LOCATION   — default: global (rankingConfigs only exist at "global")
  VERTEX_RANKING_CONFIG_ID  — default: default_ranking_config (every project gets one for free)

Auth: Application Default Credentials (ADC). The Cloud Run service account
needs `roles/discoveryengine.viewer`, which grants `rankingConfigs.rank`.
"""

from __future__ import annotations

import asyncio
import os

from google.cloud import discoveryengine_v1 as discoveryengine

_client: discoveryengine.RankServiceAsyncClient | None = None
_init_lock = asyncio.Lock()

_DEFAULT_LOCATION = "global"
_DEFAULT_RANKING_CONFIG_ID = "default_ranking_config"


async def get_reranker_client() -> discoveryengine.RankServiceAsyncClient:
    """Return the shared Ranking API client, initialising it on first call."""
    global _client
    async with _init_lock:
        if _client is None:
            _client = discoveryengine.RankServiceAsyncClient()
    return _client


def ranking_config_path() -> str:
    """Build the `projects/{p}/locations/{l}/rankingConfigs/{c}` resource name."""
    project = os.environ["VERTEX_PROJECT"]
    location = os.environ.get("VERTEX_RANKING_LOCATION", _DEFAULT_LOCATION)
    config_id = os.environ.get("VERTEX_RANKING_CONFIG_ID", _DEFAULT_RANKING_CONFIG_ID)
    return discoveryengine.RankServiceClient.ranking_config_path(
        project=project,
        location=location,
        ranking_config=config_id,
    )
