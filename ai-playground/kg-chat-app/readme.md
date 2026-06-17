# AIlixir Knowledge Graph Chat

This is a standalone FastAPI chat service for asking natural-language questions
against an existing Neo4j knowledge graph.

It does not extract or create the graph. It:

1. Connects to Neo4j on startup.
2. Introspects labels, relationship types, properties, and observed patterns.
3. Caches that schema.
4. Gives the live schema and conversation history to a Gemini query planner.
5. Converts the question into a structured route plan.
6. Chooses a Cypher template, Graphiti hybrid search, or Graphiti search plus
   Cypher expansion.
7. Builds and validates a read-only Cypher query before execution.
8. Sends graph rows back to Gemini for a grounded final answer.

The main flow is:

```text
User question
  -> cached Neo4j schema
  -> Gemini creates a structured route plan
  -> strategy router chooses template/search/expansion
  -> backend builds and validates read-only Cypher
  -> Neo4j executes query
  -> Gemini answers from graph rows only
```

The router supports three retrieval strategies:

```text
cypher_template
graphiti_hybrid_search
graphiti_search_cypher_expansion
```

For the current Graphiti-style Neo4j schema, the strategies use `Entity`,
`Episodic`, `MENTIONS`, and `RELATES_TO` with optional `group_id` filtering.
The implementation lives in `kg_chat/router.py`.
Pass `group_id` in `/query` or `/chat` to scope retrieval to one Graphiti
group. If omitted, the planner can still infer a group from `group_id`,
`group id`, or `groub id` text in the question.

Planner JSON treats `target_entities` as explicit names mentioned by the user,
such as `Aspirin` or a document title. Generic topics and LLM-generated
synonyms belong in `related_terms`; they are used only as similarity-search
hints and are not assumed to exist as Neo4j node names.

Timeline questions with dates use `valid_at` range filters. Supported examples:
`2026`, `May 2026`, `May 3, 2026`, and `2026-05-03`.

## Search Logic

The app does not let the LLM write Cypher directly. The LLM first returns a
small route plan, then the backend chooses one of three retrieval strategies.

Planner output looks like:

```json
{
  "intent": "patient_specific_search",
  "group_id": "patient-1-temporal-20260603_060015",
  "semantic_query": "current prescribed medications dosage instructions",
  "target_entities": [],
  "related_terms": ["prescriptions", "dosage"],
  "anchor_event": null,
  "time_relation": null,
  "confidence": 0.9
}
```

`target_entities` are exact things to focus on, such as `C61 Prostatakarzinom`,
`Aspirin`, or `PSA`. `related_terms` are only semantic hints. They help Graphiti
understand the search meaning, but they are not assumed to be real Neo4j nodes.

### `cypher_template`

This is used for structured questions where deterministic graph logic is safer
than semantic similarity.

Examples:

```text
what happened in 2026
what happened in May 2026
what happened after discharge
which source mentioned aspirin
how many events happened
```

The backend builds a known read-only Cypher template. Date questions use
`valid_at` range filters:

```cypher
date(episode.valid_at) >= date($event_start)
date(episode.valid_at) < date($event_end)
```

For timeline questions with `target_entities`, the template filters timeline
rows by those explicit terms. If `target_entities` is empty, the template returns
the full timeline for the supplied `group_id`.

### `graphiti_hybrid_search`

This is native Graphiti semantic search. It is used for broad or ambiguous
semantic questions where there is no deterministic template.

Examples:

```text
what does the graph know about this patient?
find information about allergies
what is related to aspirin?
```

The backend sends the combined semantic text to Graphiti:

```text
semantic_query + related_terms + target_entities
```

Graphiti searches inside the supplied `group_id` and returns matching graph
facts/edges by meaning.

### `graphiti_search_cypher_expansion`

This is the main patient-question pipeline. It combines semantic search with
deterministic graph expansion.

Examples:

```text
what medications should i take
what is my diagnosis
summarize the patient
what is my name
```

The flow is:

```text
Graphiti semantic search
  -> returns matching edge UUIDs
  -> Cypher fetches those exact edges
  -> Cypher expands source/target neighbors and source episodes
  -> answer LLM summarizes only the returned rows
```

This gives the search semantic recall while keeping the final evidence grounded
in concrete Neo4j facts, neighboring facts, dates, and source documents.

### Removed Fallback

The old broad Cypher text fallback is disabled. The app no longer silently
searches text fields with generic `CONTAINS` matching when Graphiti search fails.
For semantic retrieval, native Graphiti search must be available. If it is not,
the API returns an explicit error instead of returning weak fallback results.

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

For native Graphiti semantic search:

```env
GRAPHITI_SEARCH_ENABLED=true
GRAPHITI_SEARCH_LIMIT=10
GRAPHITI_TELEMETRY_ENABLED=false
OPENAI_API_KEY=your-openai-api-key
```

If `OPENAI_API_KEY` already exists in `ai-playground/knowledge-graph-integration/.env`,
the chat app loads it automatically unless `.env` overrides it. Keep
`GRAPHITI_SEARCH_ENABLED=true` for semantic questions. If native Graphiti search
is disabled or unavailable, semantic retrieval fails explicitly instead of using
a broad Cypher text fallback.

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
  "session_id": "demo",
  "group_id": "patient-1"
}
```

Response:

```json
{
  "cypher": "MATCH ... RETURN ... LIMIT 20",
  "parameters": {"query": "Patient A", "group_id": "patient-1", "limit": 20},
  "reason": "Routed to Graphiti search plus Cypher neighborhood expansion.",
  "intent": "patient_specific_search",
  "strategy": "graphiti_search_cypher_expansion",
  "route_plan": {
    "intent": "patient_specific_search",
    "group_id": "patient-1",
    "semantic_query": "current prescribed medications",
    "target_entities": ["Patient A"],
    "related_terms": ["prescriptions", "dosage"],
    "anchor_event": null,
    "time_relation": null,
    "confidence": 0.82
  }
}
```

### `POST /chat`

Runs the full graph chat flow.

Request:

```json
{
  "question": "Does Warfarin interact with Aspirin?",
  "session_id": "demo",
  "group_id": "patient-1",
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
    "rows": [],
    "intent": "semantic_search",
    "strategy": "graphiti_hybrid_search",
    "route_plan": {}
  }
}
```

Set `include_debug` to `false` in frontend or production use if you do not want
to expose generated queries and rows.

## Routing Debug

For backend logs, run with:

```bash
KG_LOG_LEVEL=DEBUG uvicorn main:app --reload --port 8010
```

On PowerShell:

```powershell
$env:KG_LOG_LEVEL = "DEBUG"
uvicorn main:app --reload --port 8010
```

Use `/query` to inspect routing without running the final answer step. The
response includes:

```json
{
  "intent": "timeline_query",
  "strategy": "cypher_template",
  "route_plan": {},
  "planner_debug": {
    "source": "llm_json",
    "raw_response": "{\"intent\":\"timeline_query\",...}",
    "parsed_payload": {},
    "error": null,
    "selected_strategy": "cypher_template",
    "selected_solution": "cypher_template"
  }
}
```

In Streamlit, enable `Show query debug`. The debug panel shows the raw planner
LLM JSON, selected solution, route plan, generated Cypher, parameters,
retrieval debug, native Graphiti search results, and rows.

## How to Test

Start FastAPI with debug logging:

```powershell
$env:KG_LOG_LEVEL = "DEBUG"
uvicorn main:app --reload --port 8010
```

Check that native Graphiti search is available:

```powershell
Invoke-RestMethod http://127.0.0.1:8010/health
```

Expected fields:

```json
{
  "graphiti_search_configured": true,
  "graphiti_search_available": true
}
```

Inspect routing and retrieval without running the answer LLM:

```powershell
Invoke-RestMethod http://127.0.0.1:8010/query `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"question":"what is my name","session_id":"debug","group_id":"patient-1-temporal-20260615_141110"}'
```

For semantic questions, look for:

```json
{
  "strategy": "graphiti_search_cypher_expansion",
  "retrieval_debug": {
    "mode": "native_graphiti_search_then_cypher_expansion",
    "group_id": "patient-1-temporal-20260615_141110",
    "search_result_count": 1
  },
  "graphiti_search_results": []
}
```

Then test the full answer path:

```powershell
Invoke-RestMethod http://127.0.0.1:8010/chat `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"question":"what is my name","session_id":"debug","group_id":"patient-1-temporal-20260615_141110","include_debug":true}'
```

The debug response shows the planner JSON, selected solution, Graphiti search
hits, Cypher expansion query, parameters, and final rows. If native Graphiti
search fails, the API returns an explicit error. Cypher text fallback is not
enabled for semantic retrieval.

## Query Safety

The LLM never talks to Neo4j directly. It first returns planner JSON, and the
backend either runs native Graphiti search for semantic retrieval or builds
read-only Cypher from known templates. The backend rejects Cypher that contains
write/admin operations such
as:

```text
CREATE, MERGE, DELETE, DETACH, SET, REMOVE, DROP, LOAD CSV, CALL, APOC, GDS
```

It also checks labels and relationship types against the cached Neo4j schema
when those identifiers are available. Routing is intentionally driven by live
introspection plus a small strategy table instead of sending the raw user
question straight to Cypher generation.
