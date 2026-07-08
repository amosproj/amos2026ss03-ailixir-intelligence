# AIlixir Chat Agent (Stateless Edition)

A Retrieval-Augmented Generation (RAG) API built with **Gemini 2.5 Flash (Vertex AI)** and **FastAPI**.

The backend is fully stateless.

The frontend owns:

- Chat history
- Session state
- Conversation persistence

The backend receives:

- Current question
- Chat history

and returns:

- Intent
- Rewritten query
- Grounded answer

---

## Architecture

```
POST /chat
      │
      ▼
[1] Guardrail
      │
      ▼
[2] Intent Classification
      │
 ┌────┴─────┐
 │          │
FOLLOWUP   NEW_QUESTION
 │          │
 ▼          │
Rewrite     │
 └────┬─────┘
      ▼
[3] Retrieval (vector RAG, keyword fallback)
      │
      ▼
[4] Gemini Answer Generation
      │
      ▼
Response
```

---

## Folder Structure

```text
ai-playground/
└── chat-app/
    ├── main.py
    ├── documents.json
    ├── embeddings_cache.json   # generated at runtime, gitignored
    ├── requirements.txt
    ├── .env
    ├── .env.example
    └── graph/
        ├── __init__.py
        ├── nodes.py
        └── vector_store.py
```

`embeddings_cache.json` is created automatically the first time retrieval runs — it caches chunk embeddings by content hash so restarts don't re-embed unchanged documents. It's build output, not source.

---

## Request Format

```json
{
  "question": "What is the dosage?",
  "chat_history": [
    {
      "role": "user",
      "content": "What are the side effects of Metformin?"
    },
    {
      "role": "assistant",
      "content": "Common side effects include nausea and diarrhoea."
    }
  ]
}
```

### Fields

| Field | Required | Description |
|-------|---------|-------------|
| question | Yes | Current user message |
| chat_history | No | Previous conversation turns |

The backend never stores chat history.

---

## API Endpoints

### GET /health

```json
{
  "status": "ok"
}
```

---

### POST /chat

Returns the complete answer synchronously.

### Request

```json
{
  "question": "What about the dosage?",
  "chat_history": [
    {
      "role": "user",
      "content": "Tell me about Metformin side effects."
    },
    {
      "role": "assistant",
      "content": "Metformin commonly causes nausea."
    }
  ]
}
```

### Response

```json
{
  "answer": "The recommended starting dose of Metformin is 500 mg twice daily.",
  "intent": "FOLLOWUP",
  "rewritten_question": "What is the recommended dosage for Metformin?",
  "source": "vector_rag"
}
```

### Response Fields

| Field | Description |
|-------|-------------|
| answer | Grounded answer |
| intent | NEW_QUESTION, FOLLOWUP, or BLOCKED |
| rewritten_question | Query used for retrieval |
| source | Retrieval source: `vector_rag` (default) or `keyword_fallback` (used automatically if the embedding call fails) |

---

## Retrieval (RAG)

Retrieval is embedding-based semantic search, not keyword matching:

1. **Chunk** — each document in `documents.json` is split into ~400-character chunks with 80-character overlap, breaking on whitespace so words are never cut in half.
2. **Embed** — every chunk is embedded with Vertex AI's `text-embedding-004`. Embeddings are cached on disk (`embeddings_cache.json`, keyed by a hash of the chunk text), so restarting the app doesn't re-embed documents that haven't changed.
3. **Search** — the incoming (rewritten) query is embedded the same way, and the top-k chunks are returned by cosine similarity.
4. **Fallback** — if the embedding call fails for any reason (no network, no Vertex AI quota, etc.), retrieval automatically falls back to the original keyword-overlap search over full documents, so one embedding outage never breaks `/chat`.

All of this lives in `graph/vector_store.py`. `documents.json` is still a placeholder corpus — pointing this at a real research-paper dataset later is a data change only, the chunking/embedding/search code doesn't need to change.

---

## Running the Application

### Create virtual environment

```bash
python -m venv venv
```

Linux/Mac:

```bash
source venv/bin/activate
```

Windows:

```bash
venv\Scripts\activate
```

---

### Install dependencies

```bash
pip install -r requirements.txt
```

---

### Configure environment

```bash
cp .env.example .env
```

Example:

```env
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
```

---

### Start server

```bash
uvicorn main:app --reload --port 8000
```

Swagger:

```text
http://localhost:8000/docs
```

---

## Environment Variables

| Variable | Description |
|---------|-------------|
| GOOGLE_CLOUD_PROJECT | GCP Project ID |
| GOOGLE_CLOUD_LOCATION | Vertex AI Region |
| VERTEX_PROJECT | Alias for GOOGLE_CLOUD_PROJECT |
| VERTEX_LOCATION | Alias for GOOGLE_CLOUD_LOCATION |

---

## Extending Retrieval

Retrieval is vector RAG by default (`graph/vector_store.py`), with an automatic keyword fallback — see [Retrieval (RAG)](#retrieval-rag) above.

To add another retrieval source — for example the knowledge graph in [#187](https://github.com/amosproj/amos2026ss03-ailixir-intelligence/issues/187) — extend `retrieve_context()` in `graph/nodes.py` to query the new source alongside `vector_store.search()` and merge the results. The return signature must stay:

```python
(context_text, source_label)
```

Example:

```python
def retrieve_context(query: str, top_k: int = 3):
    vector_hits = vector_store.search(query, top_k=top_k)
    kg_hits = kg_client.query(query)

    return (
        merge_contexts(vector_hits, kg_hits),
        "hybrid"
    )
```