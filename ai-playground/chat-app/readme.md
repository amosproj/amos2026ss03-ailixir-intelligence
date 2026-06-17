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
[3] Retrieval
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
    ├── requirements.txt
    ├── .env
    ├── .env.example
    └── graph/
        ├── __init__.py
        └── nodes.py
```

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
  "source": "documents.json"
}
```

### Response Fields

| Field | Description |
|-------|-------------|
| answer | Grounded answer |
| intent | NEW_QUESTION, FOLLOWUP, or BLOCKED |
| rewritten_question | Query used for retrieval |
| source | Retrieval source |

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

To integrate another retrieval backend (for example a Knowledge Graph), replace:

```python
retrieve_context()
```

inside:

```text
graph/nodes.py
```

The return signature must remain:

```python
(context_text, source_label)
```

Example:

```python
def retrieve_context(query: str, top_k: int = 3):

    results = kg_client.query(query)

    return (
        format_kg_results(results),
        "knowledge_graph"
    )
```