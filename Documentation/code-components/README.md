# Ailixir Backend — Code Components

Stage 2 of the documentation pass. Where [`Documentation/architecture/`](../architecture/README.md)
explains how the pipelines *flow*, this folder is a **reference catalog of
the code itself** — every module in `Backend/api`, `Backend/workers`, and
`Backend/shared`, what it exports, and what each piece is responsible for.
Read the architecture docs first for the "why"; use these for "where is the
code that does X, and what does it export."

`Backend/scrapers/` (the literature-ingestion job) is out of scope here —
it's covered at the architecture level in
[`04_literature_ingestion_pipeline.md`](../architecture/04_literature_ingestion_pipeline.md)
and is a separate, standalone codebase from `api`/`workers`/`shared`.

## Documents in this folder

| Doc | Covers |
|---|---|
| [01 — Shared](01_shared.md) | `Backend/shared/` — Firestore models, repositories, and the GCS/Pub-Sub/Firestore infrastructure helpers both services import. |
| [02 — API Core](02_api_core.md) | `Backend/api/` top level — `main.py` (app + documents + auth endpoints), `auth.py`, `errors.py`, `middleware.py`, `chat.py`, `voice.py`. |
| [03 — API Chat Pipeline](03_api_chat_pipeline.md) | `Backend/api/chat_pipeline/` — the 9 modules implementing contextualize → retrieve → answer. |
| [04 — Workers Core](04_workers_core.md) | `Backend/workers/main.py` and `Backend/workers/connections/` — the Pub/Sub receiver and its Gemini/Neo4j/GCS clients. |
| [05 — Workers Pipeline](05_workers_pipeline.md) | `Backend/workers/pipeline/` — the document pipeline orchestrator, LLM extraction, Graphiti/medical-schema graph building, Cypher export, and the deprecated OCR path. |

## Directory map

```
Backend/
├── api/                       -> 02, 03
│   ├── main.py, auth.py, errors.py, middleware.py, chat.py, voice.py
│   └── chat_pipeline/
│       ├── gemini_client.py, pacer.py, graphiti_client.py
│       ├── contextualizer.py, retriever.py, answerer.py
│       ├── paper_retriever.py, reranker_client.py, astra_client.py
│       └── titler.py
├── workers/                   -> 04, 05
│   ├── main.py
│   ├── connections/
│   │   ├── gemini_client.py, graphiti_client.py, neo4j.py
│   │   ├── gcs.py, paced_gemini.py
│   └── pipeline/
│       ├── document_pipeline.py
│       ├── llm/ (extractor.py, prompts.py)
│       ├── graph/ (builder.py, medical_schema.py, exporter.py, prompts.py [dead])
│       └── ocr/ (document_ai.py, extractor.py [dead])
└── shared/                     -> 01
    ├── firestore.py, gcs.py, pubsub.py, retryable_errors.py
    ├── models/ (document, extraction, journey_summary, user, literature_paper, errors)
    └── repositories/ (documents, extractions, journey_summaries, users, literature_papers)
```

## Conventions used in these docs

- **Purpose** — one line, what the file is for.
- **Exports** — the functions/classes callers actually use, one line each.
- **Notes** — only when something is non-obvious (a gotcha, a constraint, a
  reason something is built the way it is). Omitted when there's nothing
  worth flagging.
- Modules already walked in detail in the architecture docs (e.g. the medical
  schema, the pacers) are kept short here with a link back, to avoid
  duplicating the same explanation twice.
