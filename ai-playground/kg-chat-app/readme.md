# AIlixir Knowledge Graph Chat

This is a standalone FastAPI chat service for asking natural-language questions
against an existing Neo4j knowledge graph.

It does not extract or create the graph. It:

1. Connects to Neo4j on startup.
2. Introspects labels, relationship types, properties, and observed patterns.
3. Caches that schema.
4. Gives the live schema to Gemini.
5. Lets Gemini generate one read-only Cypher query.
6. Validates the query before execution.
7. Sends graph rows back to Gemini for a grounded final answer.

The main flow is:

```text
User question
  -> cached Neo4j schema
  -> Gemini generates Cypher JSON
  -> backend validates read-only Cypher
  -> Neo4j executes query
  -> Gemini answers from graph rows only
```

## Folder Structure

```text
kg-chat-app/
├── main.py                  # FastAPI app and endpoints
├── requirements.txt
├── .env.example
└── kg_chat/
    ├── config.py            # Env loading
    ├── llm.py               # Gemini clients: Vertex AI or API key
    ├── models.py            # Request/response models
    ├── neo4j_client.py      # Neo4j connection and JSON-safe row formatting
    ├── prompts.py           # Query and answer prompts
    ├── query.py             # JSON parsing and Cypher validation
    ├── retriever.py         # Chat orchestration and memory
    └── schema_cache.py      # Neo4j schema introspection
```

## Setup

```bash
cd ai-playground/kg-chat-app
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` with your Neo4j credentials and one Gemini provider.

For Neo4j Desktop / local Neo4j:

```env
NEO4J_URI=neo4j://127.0.0.1:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-local-password
NEO4J_DATABASE=neo4j
```

For Neo4j Aura:

```env
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-aura-password
NEO4J_DATABASE=neo4j
```

For Vertex AI:

```env
LLM_PROVIDER=vertex
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GEMINI_MODEL=gemini-2.5-flash
```

For Gemini API key mode:

```env
LLM_PROVIDER=google-genai
GEMINI_API_KEY=your-api-key
GEMINI_MODEL=gemini-2.5-flash
```

Run:

```bash
uvicorn main:app --reload --port 8010
```

Open Swagger:

```text
http://localhost:8010/docs
```

Run the Streamlit chat UI in another terminal:

```bash
streamlit run streamlit_app.py
```

Keep the FastAPI server running while using Streamlit. The UI calls
`http://127.0.0.1:8010/chat` by default.

## Endpoints

### `GET /health`

Shows whether Neo4j, the LLM, and the schema cache are ready.

### `GET /schema`

Returns the cached introspected Neo4j schema.

### `POST /schema/refresh`

Refreshes the cached schema from Neo4j.

### `POST /query`

Generates and validates the Cypher query without executing a final answer step.

Request:

```json
{
  "question": "What does the graph know about Patient A?",
  "session_id": "demo"
}
```

Response:

```json
{
  "cypher": "MATCH ... RETURN ... LIMIT 20",
  "parameters": {"term": "Patient A"},
  "reason": "The question asks for neighboring graph facts."
}
```

### `POST /chat`

Runs the full graph chat flow.

Request:

```json
{
  "question": "Does Warfarin interact with Aspirin?",
  "session_id": "demo",
  "include_debug": true
}
```

Response:

```json
{
  "answer": "According to the graph, ...",
  "session_id": "demo",
  "debug": {
    "generated_cypher": "...",
    "executed_cypher": "...",
    "parameters": {},
    "rows": []
  }
}
```

Set `include_debug` to `false` in frontend or production use if you do not want
to expose generated queries and rows.

## Query Safety

The LLM never talks to Neo4j directly. The backend rejects generated Cypher that
contains write/admin operations such as:

```text
CREATE, MERGE, DELETE, DETACH, SET, REMOVE, DROP, LOAD CSV, CALL, APOC, GDS
```

It also checks generated labels and relationship types against the cached Neo4j
schema when those identifiers are available. Query generation is intentionally
driven by live introspection instead of prewritten Cypher patterns.
