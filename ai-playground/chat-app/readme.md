# AIlixir Chat Agent

A RAG (Retrieval-Augmented Generation) chat agent built with **LangGraph**, **Gemini 2.5 Flash (Vertex AI)**, and **FastAPI**. Users ask natural-language questions about uploaded pharmaceutical documents. Conversation history is persisted per session in **PostgreSQL**.

---

## Folder Structure

```
ai-playground/
└── chat-app/
    ├── main.py              # FastAPI app — /health, /chat, /chat/stream endpoints
    ├── init_db.py           # Local-dev helper to verify DB connection & pre-create tables
    ├── documents.json       # Source documents for retrieval
    ├── requirements.txt     # Python dependencies
    ├── .env                 # Your local config (never commit this)
    ├── .env.example         # Safe template to commit
    └── graph/
        ├── __init__.py
        ├── builder.py       # LangGraph graph definition & Postgres checkpointer
        ├── nodes.py         # All graph nodes + shared helpers used by main.py
        └── state.py         # AgentState TypedDict — the single shared state schema
```

---

## Architecture

```
User Request (POST /chat or POST /chat/stream)
        │
        ▼
  [ Guardrail Node ]
        │  checks for prompt-injection patterns
        │  + off-topic intent via LLM classifier
        │
   BLOCKED ──────────────────────────────────────▶ END (refusal message)
        │
      ALLOWED
        │
        ▼
  [ Intent Node ]
        │  LLM-based + heuristic classifier
        │
   ┌────┴────┐
   │         │
FOLLOWUP  NEW_QUESTION
   │         │
   ▼         │
[ Rewrite    │
  Node ]     │   resolves pronouns & vague references
   │         │   into a self-contained query
   └────┬────┘
        ▼
  [ Retrieve Node ]   ◀── keyword search over documents.json
        │                  (swap point for Knowledge Graph — issue #75)
        │
   streaming=True ──────────────────────────────▶ END
        │            main.py streams Gemini directly
   streaming=False
        │
        ▼
  [ Answer Node ]     ◀── Gemini 2.5 Flash via Vertex AI (non-streaming)
        │
        ▼
  Response saved to Postgres (LangGraph PostgresSaver)
```

### Streaming vs. Non-Streaming

The graph has two paths after the retrieve node, controlled by `state.streaming`:

- **`POST /chat`** (non-streaming): the graph runs all five nodes including `answer_node`. The full answer is returned in a single JSON response.
- **`POST /chat/stream`** (streaming): the graph runs up to and including `retrieve_node`, then exits. `main.py` then calls Gemini with `stream=True` and pipes tokens directly to the client as Server-Sent Events. This eliminates any wasted non-streaming LLM call inside the graph.

Both paths use the same `build_answer_prompt()` function from `nodes.py` — there is no prompt duplication.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.10+ |
| PostgreSQL | 14+ |
| Google Cloud project | Vertex AI API enabled |

---

## Setup

### 1. Clone and create a virtual environment

```bash
cd ai-playground/chat-app
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Install and configure PostgreSQL

If PostgreSQL is not installed yet:

- **Windows**: Download from https://www.postgresql.org/download/windows/ and set a password for the `postgres` user during installation.
- **macOS**: `brew install postgresql@14 && brew services start postgresql@14`
- **Linux (Ubuntu/Debian)**: `sudo apt install postgresql && sudo systemctl start postgresql`

Once installed, open a terminal and create the database:

```bash
# Windows (run psql from Start menu or add it to PATH)
psql -U postgres

# macOS / Linux
sudo -u postgres psql
```

Inside the psql shell:

```sql
CREATE DATABASE ailixir;
\q
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
VERTEX_PROJECT_ID=your-vertex-project-id
DB_URI=postgresql://postgres:YOUR_PASSWORD@localhost:5432/ailixir
```

Both `GOOGLE_CLOUD_PROJECT` and `VERTEX_PROJECT_ID` are supported. The code reads whichever is present, so you can use either the standard Google Cloud SDK convention or the Vertex-specific name.

> **DB_URI format:** `postgresql://<user>:<password>@<host>:<port>/<database>`  
> Default user is `postgres`, default port is `5432`.

### 5. Database tables

The required tables (`checkpoints`, `writes`) are created **automatically** on first startup by LangGraph's `checkpointer.setup()` inside `builder.py`. No manual SQL is needed.

If you want to verify the connection and pre-create the tables before starting the server (useful in local dev), run:

```bash
python init_db.py
```

### 6. Run the API

```bash
uvicorn main:app --reload --port 8000
```

The API is now live at `http://localhost:8000`.  
Swagger UI (interactive docs): `http://localhost:8000/docs`

---

## API Endpoints

### `GET /health`

Liveness check. Returns `{"status": "ok"}`.

---

### `POST /chat`

Synchronous — full answer returned at once. All five graph nodes run.

**Request body:**
```json
{
  "question": "What are the side effects of Metformin?",
  "session_id": "user-42"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `question` | string | ✅ | Your question (1–2000 chars) |
| `session_id` | string | ❌ | Conversation thread ID. Reuse across turns to maintain context. Defaults to `"default-session"` |

**Response:**
```json
{
  "answer": "Common side effects of Metformin include nausea, diarrhoea...",
  "session_id": "user-42",
  "intent": "NEW_QUESTION",
  "rewritten_question": "What are the side effects of Metformin?",
  "source": "documents.json"
}
```

| Field | Description |
|---|---|
| `answer` | Agent's answer grounded in documents |
| `session_id` | Echo of the session used |
| `intent` | `NEW_QUESTION`, `FOLLOWUP`, or `BLOCKED` |
| `rewritten_question` | Disambiguated query used for retrieval |
| `source` | Retrieval source — currently always `documents.json` |

---

### `POST /chat/stream`

Streaming via Server-Sent Events. The graph runs up to `retrieve_node`, then Gemini streams tokens directly to the client.

Same request body as `/chat`.

**SSE event sequence:**

```
data: {"type":"meta","intent":"NEW_QUESTION","rewritten_question":"...","source":"documents.json"}

data: {"type":"token","text":"Common "}

data: {"type":"token","text":"side effects "}

...

data: {"type":"done"}
```

On a blocked question:
```
data: {"type":"blocked","text":"I can only answer questions about pharmaceutical documents..."}

data: {"type":"done"}
```

On an error:
```
data: {"type":"error","text":"<error message>"}
```

The `meta` event arrives **before** the first token, so the frontend can display intent indicators and source badges immediately without waiting for the full answer.

**React Native example:**

```javascript
const res = await fetch('https://your-api-domain.com/chat/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ question: userInput, session_id: userId }),
});

const reader = res.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  const raw = decoder.decode(value);
  for (const line of raw.split('\n')) {
    if (!line.startsWith('data: ')) continue;
    const msg = JSON.parse(line.slice(6));
    if (msg.type === 'meta')    setMeta(msg);
    if (msg.type === 'token')   appendText(msg.text);
    if (msg.type === 'done')    markComplete();
    if (msg.type === 'blocked') showRefusal(msg.text);
    if (msg.type === 'error')   showError(msg.text);
  }
}
```

---

## Graph Nodes

All node logic lives in `graph/nodes.py`. Constants and helpers used by `main.py` are imported from there — no logic is duplicated.

| Node | Purpose |
|---|---|
| `guardrail_node` | Blocks prompt-injection patterns and off-topic questions. Sets `intent="BLOCKED"` and short-circuits to END if triggered. |
| `intent_node` | Classifies the question as `NEW_QUESTION` or `FOLLOWUP` using a heuristic check first, then an LLM call if needed. |
| `rewrite_node` | Rewrites follow-up questions into fully self-contained queries by resolving pronouns and vague references. Only runs for `FOLLOWUP`. |
| `retrieve_node` | Performs keyword search over `documents.json` and populates `state.context` and `state.source`. |
| `answer_node` | Calls Gemini to generate the final answer. Skipped when `state.streaming=True`. |

---

## Guardrails

Questions pass through `guardrail_node` before any LLM call:

**Prompt-injection detection** blocks patterns such as `"ignore previous instructions"`, `"pretend you are"`, `"jailbreak"`, `"act as"`, `"bypass"`, `"developer mode"`, and similar.

**Off-topic detection** uses an LLM classifier to reject questions with no pharmaceutical or document relevance.

Blocked requests return `REFUSAL_MESSAGE` and never invoke the LLM.

---

## Conversation Memory

Memory is managed automatically by LangGraph's `PostgresSaver`. Each unique `session_id` maps to an independent thread stored in PostgreSQL. The full message history is loaded explicitly before each graph invocation so every node — including `guardrail_node` and `intent_node` — sees the complete prior conversation from the first node onwards.

Message history is stored using the rewritten question (not the raw follow-up) so that future intent classification and query rewriting always work from fully resolved context.

---

## Retrieval

Retrieval currently uses keyword scoring over `documents.json`. Each document's content is scored by the number of query words it contains; the top-3 documents are concatenated and passed as context to Gemini.

### Extending to a Knowledge Graph (issue #75)

The only function that changes is `retrieve_context()` in `graph/nodes.py`:

```python
def retrieve_context(query: str, top_k: int = 3) -> tuple[str, str]:
    # Replace with your KG client call
    results = kg_client.query(query)
    return format_kg_results(results), "knowledge_graph"
```

The return signature `(context_text, source_label)` must stay the same. No other file needs to change. New state fields for KG metadata (subgraph, entities) can be added to `graph/state.py` — all downstream nodes and the API response will have access to them automatically.

---

## Environment Variable Reference

| Variable | Description | Default |
|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | GCP project ID (standard SDK name) | — |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI region | `us-central1` |
| `VERTEX_PROJECT_ID` | GCP project ID (Vertex-specific alias) | — |
| `DB_URI` | Full PostgreSQL connection string | `postgresql://postgres:password@localhost:5432/ailixir` |

`GOOGLE_CLOUD_PROJECT` and `VERTEX_PROJECT_ID` are interchangeable — the code reads whichever is set.