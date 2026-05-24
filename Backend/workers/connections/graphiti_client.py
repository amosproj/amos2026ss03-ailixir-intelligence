"""
Singleton Graphiti client.

Graphiti wraps Neo4j + OpenAI into a temporal knowledge-graph client.
The instance is created once and reused across all pipeline invocations.

Call build_indices() once at app startup (idempotent).
Call close_graphiti() on app shutdown.

Configure via:
  NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
  OPENAI_API_KEY
"""

from __future__ import annotations

import asyncio
import logging
import os

from graphiti_core import Graphiti
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient

_log = logging.getLogger(__name__)

_graphiti: Graphiti | None = None
_indices_built: bool = False
_init_lock = asyncio.Lock()


async def get_graphiti() -> Graphiti:
    """Return the shared Graphiti instance, initialising it on first call."""
    global _graphiti, _indices_built
    async with _init_lock:
        if _graphiti is None:
            api_key = os.environ["OPENAI_API_KEY"]
            _graphiti = Graphiti(
                os.environ["NEO4J_URI"],
                os.environ["NEO4J_USER"],
                os.environ["NEO4J_PASSWORD"],
                llm_client=OpenAIClient(config=LLMConfig(api_key=api_key)),
                embedder=OpenAIEmbedder(config=OpenAIEmbedderConfig(api_key=api_key)),
            )
            _log.info("graphiti_client_created")
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
