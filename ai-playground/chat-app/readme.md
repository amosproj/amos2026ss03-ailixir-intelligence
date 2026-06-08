# AIlixir Chat Agent

A RAG (Retrieval-Augmented Generation) chat agent built with **LangGraph**, **Gemini (Vertex AI)**, and **FastAPI**. Users can ask natural-language questions about uploaded pharmaceutical documents. Conversation history is persisted per session in **PostgreSQL**.

---

## Folder Structure

```
chat-app/
├── main.py                  # FastAPI application & endpoints
├── documents.json           # Source documents for retrieval
├── requirements.txt         # Python dependencies
├── .env.example             # Safe template to commit
└── graph/
    ├── __init__.py
    ├── builder.py           # LangGraph graph definition & Postgres checkpointer
    ├── nodes.py             # All graph nodes: guardrail, intent, rewrite, retrieve, answer
    └── state.py             # AgentState TypedDict
```

---

## Architecture

```
User Request (POST /chat)
        │
        ▼
  [ Guardrail Node ]  ──── BLOCKED ──▶  END (refusal message)
        │
      ALLOWED
        │
        ▼
  [ Intent Detection ]
        │
   ┌────┴────┐
   │         │
FOLLOWUP  NEW_QUESTION
   │         │
   ▼         │
[ Query      │
  Rewriter ] │
   │         │
   └────┬────┘
        ▼
  [ Retrieval Node ]   ◀── documents.json (keyword search)
        │                   (swap for Knowledge Graph later)
        ▼
  [ Answer Node ]      ◀── Gemini 2.5 Flash via Vertex AI
        │
        ▼
     Response
  (saved to Postgres)
```

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.10+ |
| PostgreSQL | 14+ |
| Google Cloud project | with Vertex AI API enabled |

---

## Setup

### 1. Clone and create a virtual environment

```bash
cd chat-app
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

- **Windows**: Download and install from https://www.postgresql.org/download/windows/  
  During installation, set a password for the `postgres` user — remember it.
- **macOS**: `brew install postgresql@14 && brew services start postgresql@14`
- **Linux (Ubuntu/Debian)**: `sudo apt install postgresql && sudo systemctl start postgresql`

Once installed, open a terminal and connect to PostgreSQL:

```bash
# Windows (use psql from the Start menu or add it to PATH)
psql -U postgres

# macOS / Linux
sudo -u postgres psql
```

Inside the psql shell, create the database:

```sql
CREATE DATABASE ailixir;
\q
```

### 4. Configure environment variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```env
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
DB_URI=postgresql://postgres:YOUR_PASSWORD@localhost:5432/ailixir
```

Replace `YOUR_PASSWORD` with the password you set during PostgreSQL installation.

> The `DB_URI` format is: `postgresql://<user>:<password>@<host>:<port>/<database>`  
> Default PostgreSQL user is `postgres`, default port is `5432`.

Then update `graph/builder.py` to read from the environment instead of hardcoding:

```python
import os
DB_URI = os.getenv("DB_URI", "postgresql://postgres:password@localhost:5432/ailixir")
```

### 5. Database tables

The required tables (`checkpoints`, `writes`) are created **automatically** on first startup — no manual SQL needed. LangGraph's `checkpointer.setup()` handles this.

### 6. Run the API

```bash
uvicorn main:app --reload --port 8000
```

The API is now live at `http://localhost:8000`.  
Interactive docs (Swagger UI): `http://localhost:8000/docs`

---

## API Endpoints

### `GET /health`
Liveness check. Returns `{"status": "ok"}`.

---

### `POST /chat`
Send a question to the agent.

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
| `session_id` | string | ❌ | Conversation thread ID. Reuse across turns to keep memory. Defaults to `"default-session"` |

**Response:**
```json
{
  "answer": "Common side effects of Metformin include nausea, diarrhoea...",
  "session_id": "user-42",
  "intent": "NEW_QUESTION",
  "rewritten_question": "What are the side effects of Metformin?"
}
```

| Field | Description |
|---|---|
| `answer` | Agent's answer grounded in documents |
| `session_id` | Echo of the session used |
| `intent` | `NEW_QUESTION`, `FOLLOWUP`, or `BLOCKED` |
| `rewritten_question` | Disambiguated question used for retrieval (follow-ups only) |

---

## Guardrails

All questions pass through a guardrail node **before** reaching the LLM:

- **Prompt injection** — blocks patterns like `"ignore previous instructions"`, `"pretend you are"`, `"jailbreak"`, etc.
- **Off-topic queries** — blocks questions with no pharmaceutical/document relevance using keyword heuristics.

Blocked requests return a safe refusal message and never invoke the LLM.

---

## Conversation Memory

Memory is handled automatically by LangGraph's `PostgresSaver`. Each unique `session_id` maps to an independent conversation thread stored in PostgreSQL. No manual history management is required.

---

## Connecting a Frontend (React Native)

CORS is fully enabled — all origins, methods, and headers are allowed. From React Native:

```javascript
const response = await fetch('https://your-api-domain.com/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    question: userInput,
    session_id: userId,
  }),
});
const data = await response.json();
console.log(data.answer);
```

---

## Running Tests

```bash
pip install pytest httpx
pytest tests/test_chat.py -v
```

Tests use mocks for Vertex AI and PostgreSQL — no real GCP credentials or database needed to run them.

---

## Extending with a Knowledge Graph

Retrieval currently uses keyword search over `documents.json`. To integrate a knowledge graph (issue #75), replace the `retrieve_context()` function in `graph/nodes.py`:

```python
def retrieve_context(query: str, top_k: int = 3) -> str:
    # Replace with your KG client query
    results = kg_client.query(query)
    return format_kg_results(results)
```

No other files need to change.

---