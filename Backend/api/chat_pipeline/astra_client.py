"""
Singleton AstraDB vector store client for the chat pipeline (paper retrieval).

This is the SAME AstraDB collection `scrapers/` ingests into (PubMed papers,
Archive preprints, YouTube transcripts, ...) — see
`scrapers/src/backend/Scrapers/BaseScraper/base_scraper.py`.
The embedding model here MUST match what the scraper used to embed documents
(`text-embedding-3-small`, 1536-dim) — mixing embedding spaces silently
returns garbage cosine distances rather than raising an error. This was
diagnosed for real: an earlier version of this file relied on
`OpenAIEmbeddings()`'s implicit default (`text-embedding-ada-002`), which
does NOT match what the scraper actually used, and cosine similarity
between a stored vector and a fresh embedding of its own content came back
~0.02 (statistically random) instead of ~1.0. Never rely on the library
default here — always pass `model=` explicitly, on both the query side
(this file) and the ingestion side (`base_scraper.py`).

Required env vars:
  ASTRA_DB_API_ENDPOINT — e.g. https://<db-id>-<region>.apps.astra.datastax.com
  ASTRA_DB_TOKEN         — AstraCS:... application token
  ASTRA_DB_COLLECTION    — collection name (shared with the scrapers subsystem)
  OPEN_AI_API            — OpenAI key used for query embeddings (same var name
                           the scrapers subsystem uses, so one secret covers both)

Optional:
  ASTRA_DB_NAMESPACE   — default: default_keyspace
  OPENAI_EMBEDDING_MODEL — default: text-embedding-3-small (MUST match ingestion)
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

# MUST match the model the scrapers subsystem embeds documents with (see
# base_scraper.py). Never leave this to OpenAIEmbeddings()'s implicit
# default — see module docstring for why that broke retrieval in practice.
_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


async def get_astra_store() -> AstraDBVectorStore:
    """Return the shared AstraDB vector store, initialising it on first call."""
    global _store
    async with _init_lock:
        if _store is None:
            collection = os.environ["ASTRA_DB_COLLECTION"]
            model = os.environ.get("OPENAI_EMBEDDING_MODEL", _DEFAULT_EMBEDDING_MODEL)
            _store = AstraDBVectorStore(
                embedding=OpenAIEmbeddings(
                    openai_api_key=os.environ["OPEN_AI_API"],
                    model=model,
                ),
                api_endpoint=os.environ["ASTRA_DB_API_ENDPOINT"],
                token=os.environ["ASTRA_DB_TOKEN"],
                namespace=os.environ.get("ASTRA_DB_NAMESPACE", _DEFAULT_NAMESPACE),
                collection_name=collection,
            )
            _log.info(
                "astra_store_created collection=%s embedding_model=%s",
                collection, model,
            )
    return _store
