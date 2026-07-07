"""
Singleton AstraDB vector store client for the chat pipeline (paper retrieval).

This is the SAME AstraDB collection `scrapers/` ingests into (PubMed papers,
Archive preprints, YouTube transcripts, ...) — see
`scrapers/scraping_embeddings_pipeline/src/backend/Scrapers/BaseScraper/base_scraper.py`.
The embedding model here MUST match what the scraper used to embed documents
(OpenAI, 1536-dim) — mixing embedding spaces silently returns garbage cosine
distances rather than raising an error, so do not swap this for a Vertex
embedder without re-embedding the whole collection.

Required env vars:
  ASTRA_DB_API_ENDPOINT — e.g. https://<db-id>-<region>.apps.astra.datastax.com
  ASTRA_DB_TOKEN         — AstraCS:... application token
  ASTRA_DB_COLLECTION    — collection name (shared with the scrapers subsystem)
  OPEN_AI_API            — OpenAI key used for query embeddings (same var name
                           the scrapers subsystem uses, so one secret covers both)

Optional:
  ASTRA_DB_NAMESPACE — default: default_keyspace
"""

from __future__ import annotations

import asyncio
import logging
import os

from langchain_astradb import AstraDBVectorStore
from langchain_openai import OpenAIEmbeddings

_log = logging.getLogger(__name__)

_store: AstraDBVectorStore | None = None
_init_lock = asyncio.Lock()

_DEFAULT_NAMESPACE = "default_keyspace"


async def get_astra_store() -> AstraDBVectorStore:
    """Return the shared AstraDB vector store, initialising it on first call."""
    global _store
    async with _init_lock:
        if _store is None:
            collection = os.environ["ASTRA_DB_COLLECTION"]
            _store = AstraDBVectorStore(
                embedding=OpenAIEmbeddings(openai_api_key=os.environ["OPEN_AI_API"]),
                api_endpoint=os.environ["ASTRA_DB_API_ENDPOINT"],
                token=os.environ["ASTRA_DB_TOKEN"],
                namespace=os.environ.get("ASTRA_DB_NAMESPACE", _DEFAULT_NAMESPACE),
                collection_name=collection,
            )
            _log.info("astra_store_created collection=%s", collection)
    return _store
