"""
graph/vector_store.py
----------------------
Lightweight in-memory vector store that turns documents.json into a real
Retrieval-Augmented Generation (RAG) pipeline:

    documents.json -> chunk -> embed (Vertex AI) -> in-memory index -> cosine search

This replaces the old keyword-overlap scoring in nodes.py with actual
semantic retrieval, while keeping the same public contract so nothing
upstream (nodes.py, builder.py, main.py) has to change.

Design notes (see issue #187 for the longer-term hybrid KG+RAG architecture)
-----------------------------------------------------------------------------
- documents.json remains the "dummy" corpus for now. Pointing this at a real
  research-paper corpus later is a data change only -- chunking, embedding,
  and search logic stay the same.
- Embeddings are cached on disk (embeddings_cache.json), keyed by a hash of
  the chunk text. Restarting the app does not re-embed unchanged chunks, so
  local dev stays fast and Vertex AI embedding calls aren't wasted.
- This module only knows about vector search. When the knowledge graph
  lands (#187), add a sibling module (e.g. kg_store.py) and combine both
  result sets in nodes.py's retrieve step -- this file doesn't need to
  change for that.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from vertexai.language_models import TextEmbeddingModel

_DATA_FILE  = Path(__file__).resolve().parent.parent / "documents.json"
_CACHE_FILE = Path(__file__).resolve().parent.parent / "embeddings_cache.json"

_EMBED_MODEL_NAME = "text-embedding-004"

_CHUNK_SIZE    = 400   # characters per chunk
_CHUNK_OVERLAP = 80    # characters of overlap between consecutive chunks

_embed_model: TextEmbeddingModel | None = None
_index: list[dict] | None = None  # each item: chunk_id, doc_id, title, text, hash, embedding


# ---------------------------------------------------------------------------
# Embedding model
# ---------------------------------------------------------------------------


def _get_embed_model() -> TextEmbeddingModel:
    global _embed_model
    if _embed_model is None:
        _embed_model = TextEmbeddingModel.from_pretrained(_EMBED_MODEL_NAME)
    return _embed_model


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Batches text through the Vertex AI embedding model."""
    embeddings = _get_embed_model().get_embeddings(texts)
    return [e.values for e in embeddings]


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _chunk_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """
    Sliding-window chunker that backs up to the nearest whitespace so chunks
    never cut a word in half, with `overlap` characters shared between
    consecutive chunks so context isn't lost at chunk boundaries.
    """
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            last_space = text.rfind(" ", start, end)
            if last_space > start:
                end = last_space
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


# ---------------------------------------------------------------------------
# Embedding cache (disk)
# ---------------------------------------------------------------------------


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_cache() -> dict[str, list[float]]:
    if _CACHE_FILE.exists():
        try:
            with open(_CACHE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_cache(cache: dict[str, list[float]]) -> None:
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except OSError as exc:
        print(f"[vector_store] failed to write embeddings cache: {exc}")


# ---------------------------------------------------------------------------
# Index construction
# ---------------------------------------------------------------------------


def build_index(force_rebuild: bool = False) -> list[dict]:
    """
    Loads documents.json, chunks each document, embeds every chunk (reusing
    the disk cache for unchanged chunks), and builds the in-memory index.

    Lazily triggered by the first search() call; pass force_rebuild=True to
    re-read documents.json and pick up new/changed documents at runtime.
    """
    global _index
    if _index is not None and not force_rebuild:
        return _index

    with open(_DATA_FILE, encoding="utf-8") as f:
        documents = json.load(f)

    cache = _load_cache()
    new_cache: dict[str, list[float]] = {}
    index: list[dict] = []

    texts_to_embed: list[str] = []
    pending: list[dict] = []

    for doc in documents:
        for i, chunk in enumerate(_chunk_text(doc["content"])):
            chunk_hash = _hash_text(chunk)
            item = {
                "chunk_id": f"{doc['id']}-{i}",
                "doc_id": doc["id"],
                "title": doc["title"],
                "text": chunk,
                "hash": chunk_hash,
            }
            if chunk_hash in cache:
                item["embedding"] = cache[chunk_hash]
                new_cache[chunk_hash] = cache[chunk_hash]
                index.append(item)
            else:
                texts_to_embed.append(chunk)
                pending.append(item)

    if texts_to_embed:
        print(f"[vector_store] embedding {len(texts_to_embed)} new chunk(s) via {_EMBED_MODEL_NAME}")
        embeddings = _embed_texts(texts_to_embed)
        for item, embedding in zip(pending, embeddings):
            item["embedding"] = embedding
            new_cache[item["hash"]] = embedding
            index.append(item)

    _save_cache(new_cache)
    _index = index
    print(f"[vector_store] index ready: {len(index)} chunk(s) from {len(documents)} document(s)")
    return _index


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    a_arr, b_arr = np.array(a), np.array(b)
    denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if denom == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)


def search(query: str, top_k: int = 3) -> list[dict]:
    """
    Embeds the query and returns the top_k most similar chunks
    (chunk_id, doc_id, title, text, score), best match first.
    """
    index = build_index()
    if not index:
        return []

    query_embedding = _embed_texts([query])[0]

    scored = [
        {**item, "score": _cosine_similarity(query_embedding, item["embedding"])}
        for item in index
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]
