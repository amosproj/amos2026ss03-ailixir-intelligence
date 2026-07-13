# 03 — API Chat Pipeline (`Backend/api/chat_pipeline/`)

The nine modules implementing the question-answering pipeline consumed by
`api/chat.py` and `api/voice.py`. Full flow/rationale in
[doc 02 architecture](../architecture/02_question_answering_pipeline.md) —
this doc is the per-file reference.

## `gemini_client.py`
**Purpose:** Singleton async Gemini/Vertex AI client for this service.
- `get_gemini_client()` — lazy singleton, `vertexai=True`, ADC auth. Mirrors `workers/connections/gemini_client.py` but kept as a separate copy so the API doesn't import the `workers` package.

## `pacer.py`
**Purpose:** Rate-limits this process's own Vertex Gemini calls.
- `pace_gemini_call()` — async admission gate; `_MIN_INTERVAL_S` (default `0.3s`, ~200 RPM ceiling) between admissions, one `asyncio.Lock` per process. Called explicitly before each of the three direct Vertex calls (contextualize, answer, title) — see [architecture doc](../architecture/02_question_answering_pipeline.md#component-5--rate-limiting-chat_pipelinepacerpy) for why it's a separate instance from the worker's pacer.

## `graphiti_client.py`
**Purpose:** Singleton Graphiti instance for retrieval only (no ingestion).
- `get_graphiti()` — builds `Graphiti` with a plain (unpaced) `GeminiClient`/`GeminiRerankerClient`/`GeminiEmbedder` and `Neo4jDriver`. Does **not** call `build_indices_and_constraints()` — the ingestion worker already built them.
- `close_graphiti()` — called from the API's `lifespan` shutdown.

## `contextualizer.py`
**Purpose:** Step 1 — decides if the query needs rewriting against conversation history.
- `contextualize_query(query, history)` → `ContextualizeResult{query, changed}`. **Never raises** — every failure path returns the original query unchanged.
- `ContextualizeResult` — tiny `__slots__` result container.
- Internal: `_sanitize_history` (role/length/turn-count capping), `_format_history`, `_extract_json`/`_strip_markdown_fences` (tolerant JSON parsing of the LLM response).
- Constants: `_MAX_HISTORY_TURNS` (20), `_MAX_TURN_CHARS` (4000), `_MAX_QUERY_CHARS` (2000), `_MAX_PROMPT_CHARS` (100000), `_TIMEOUT_S` (30s) — all env-overridable.

## `retriever.py`
**Purpose:** Step 2a — hybrid search over the patient's Neo4j knowledge graph.
- `retrieve(query, user_id, num_results=4, graphiti=None)` → `RetrievalResult{query, user_id, edges, nodes}`. Scopes every search with `group_ids=[user_id]` — this is the patient-isolation boundary. Raises `asyncio.TimeoutError` past `_SEARCH_TIMEOUT_S` (default 15s), which the caller maps to a `503`.
- `RetrievalResult` — dataclass with `.total_edges`/`.total_nodes` properties.
- `_build_search_config(num_results)` — cosine + BM25 search methods, RRF reranker, on both edges and nodes.

## `paper_retriever.py`
**Purpose:** Step 2b — the supplementary research-paper retrieval arm (vector search + rerank). Runs concurrently with `retriever.py`, never with it.
- `retrieve_papers(query)` → `PaperRetrievalResult{query, chunks}`. **Never raises** — every failure (vector search, rerank, timeout, no hits) collapses to an empty result.
- `PaperChunk` — one reranked chunk (`content`, `source`, `source_type`, `source_id`, `published_date`, `score`).
- `PaperRetrievalResult` — dataclass with `.total_chunks`.
- Internal: `_vector_search(query)` (AstraDB, filtered by hardcoded `domain=medical`/`sub_domain=oncology`), `_rank_sync(query, documents)` (blocking Ranking API call, run via `asyncio.to_thread`), `_rerank(query, documents)`.

## `reranker_client.py`
**Purpose:** Singleton Vertex AI Ranking API client used by `paper_retriever.py`.
- `get_reranker_client()` — the **sync** `RankServiceClient` (not the async gapic client — an upstream bug in the async client raises "Task got Future attached to a different loop"; sync + `asyncio.to_thread` sidesteps it). Guarded by a plain `threading.Lock` since it's built from inside a worker thread, not the event loop.
- `ranking_config_path()` — builds the `projects/{p}/locations/{l}/rankingConfigs/{c}` resource name.

## `astra_client.py`
**Purpose:** Singleton AstraDB vector store client for paper retrieval — the **query side** of the same collection `Backend/scrapers/` writes to.
- `get_astra_store()` — lazy singleton `AstraDBVectorStore` wrapping `OpenAIEmbeddings`.
- **Notes:** The embedding model (`text-embedding-3-small`, hardcoded default, never left to the library's implicit default) **must** match what the scraper used to embed — see [doc 04 architecture](../architecture/04_literature_ingestion_pipeline.md#the-embedding-model-coupling-a-documented-footgun-already-hit-once) for the real incident this constraint documents.

## `answerer.py`
**Purpose:** Step 3 — turns retrieved graph facts (+ optional paper excerpts) into a natural-language answer.
- `generate_answer(query, result, paper_result=None)` → answer string. Raises `TimeoutError` past `_TIMEOUT_S` (60s) and `ValueError` on an empty Gemini response (SAFETY/MAX_TOKENS/RECITATION) — both are caught by name in `api/chat.py` and mapped to distinct error codes.
- `_build_llm_context(result)` — splits edges into **current** (`invalid_at is None`) vs. **historical**, formats entities; this current/historical split is the direct payoff of Graphiti's bi-temporal model (see [doc 01 architecture](../architecture/01_extraction_and_knowledge_graph_pipeline.md)).
- `_build_paper_context(paper_result)` — returns `""` when there are no chunks, so the prompt template degrades cleanly to graph-only.
- `_extract_finish_reason(response)` — pulls the Gemini finish reason for a more actionable exception message than "empty response."
- `_fmt_date(dt)` — `YYYY-MM-DD` or `"unknown date"`.

## `titler.py`
**Purpose:** Best-effort chat-title generation after the first message of a new chat — not part of the answer path.
- `generate_and_store_title(uid, chat_id, query)` — the public entry point; **never raises**, launched via `asyncio.create_task` from `api/chat.py`.
- `_generate_title(query)` — one paced (`pace_gemini_call`), time-bounded (10s) Vertex call with `thinking_config=ThinkingConfig(thinking_budget=0)` (a 3-6 word title needs no reasoning budget, and thinking would add seconds of latency).
- `_sanitize_title(raw, fallback)` — strips fences/control chars/quotes/trailing punctuation, collapses whitespace, caps at 60 chars, falls back to the query's own opening text if the model returns nothing usable.
- `_write_title_txn(uid, chat_id, title)` — blocking Realtime Database transaction (run via `asyncio.to_thread`); only overwrites the literal placeholder `"New Chat"` and never a user's own rename (`titleSource == "user"`) — this is what makes the trigger side idempotent and rename-safe.
- `_SkipTitleWrite` — sentinel exception used to abort the RTDB transaction cleanly without writing.
