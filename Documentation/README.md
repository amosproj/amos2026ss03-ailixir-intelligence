# Ailixir Intelligence — Documentation

Build, user, and technical documentation for the Ailixir Intelligence
backend. This page is the index — read it first, then follow whichever
folder below matches what you're trying to do.

## Where to start, by goal

| I want to... | Go to |
|---|---|
| Understand how the system is designed before touching code | [`architecture/`](architecture/README.md) |
| Look up what a specific file/function does | [`code-components/`](code-components/README.md) |
| Just try the deployed app, or run my own copy locally | [`running-the-project/`](running-the-project/README.md) |
| Integrate a frontend against the API | [`api-integration-guides/`](api-integration-guides/Document_API_FE_Integration_guide.md) |
| Follow the team's Git workflow | [`github-best-practices.md`](github-best-practices.md) |

## Folder-by-folder

### [`architecture/`](architecture/README.md) — how it's designed

The "why" and "how it flows" layer, with Mermaid diagrams. Covers the two AI
pipelines, the API service, the supporting literature-ingestion job, and the
GCP deployment topology.

| File | Covers |
|---|---|
| [`README.md`](architecture/README.md) | System overview, context diagram, tech stack summary |
| [`01_extraction_and_knowledge_graph_pipeline.md`](architecture/01_extraction_and_knowledge_graph_pipeline.md) | The worker pipeline: document upload → Gemini multimodal analysis → Graphiti/Neo4j knowledge graph → Cypher export |
| [`02_question_answering_pipeline.md`](architecture/02_question_answering_pipeline.md) | The chat/voice RAG pipeline: contextualize → retrieve (knowledge graph + research papers) → answer |
| [`03_api_service_architecture.md`](architecture/03_api_service_architecture.md) | FastAPI app structure, auth, the document upload lifecycle, middleware, error model, security boundaries |
| [`04_literature_ingestion_pipeline.md`](architecture/04_literature_ingestion_pipeline.md) | The standalone scraper job that feeds the research-paper corpus chat reads from |
| [`05_infrastructure_and_deployment.md`](architecture/05_infrastructure_and_deployment.md) | Cloud Run topology, service accounts/IAM, data stores, Pub/Sub, Terraform layout |

Also in this folder: `frontend_architecture_diagram` — a hand-drawn diagram
of the mobile app's voice/ElevenLabs/RTDB flow. Independent of the six docs
above; kept because it's still accurate.

### [`code-components/`](code-components/README.md) — what each file does

A per-file reference catalog of `Backend/api`, `Backend/workers`, and
`Backend/shared`: purpose, key exports, and non-obvious notes for every
module. Use this when you know *which* pipeline you're in (from
`architecture/`) and need to find the exact function.

| File | Covers |
|---|---|
| [`README.md`](code-components/README.md) | Index + directory map |
| [`01_shared.md`](code-components/01_shared.md) | `shared/` — Firestore models, repositories, GCS/Pub-Sub/Firestore infra clients |
| [`02_api_core.md`](code-components/02_api_core.md) | `api/main.py`, `auth.py`, `errors.py`, `middleware.py`, `chat.py`, `voice.py` |
| [`03_api_chat_pipeline.md`](code-components/03_api_chat_pipeline.md) | `api/chat_pipeline/` — all 9 modules behind contextualize → retrieve → answer |
| [`04_workers_core.md`](code-components/04_workers_core.md) | `workers/main.py` + `workers/connections/` (Gemini, Neo4j, GCS clients) |
| [`05_workers_pipeline.md`](code-components/05_workers_pipeline.md) | `workers/pipeline/` — orchestrator, LLM extraction, graph building, Cypher export, deprecated OCR path |

### [`running-the-project/`](running-the-project/README.md) — how to run it

Task-oriented, not reference. Splits into the two audiences an open-source
project actually has:

| File | Covers |
|---|---|
| [`README.md`](running-the-project/README.md) | Which of the two paths below you want, and what the project's compute topology actually is |
| [`01_using_the_deployed_system.md`](running-the-project/01_using_the_deployed_system.md) | Zero-setup path: curl walkthrough against the already-deployed backend — sign up, upload+extract a document, chat against it |
| [`02_running_locally.md`](running-the-project/02_running_locally.md) | Full local dev setup: prerequisites, credentials, environment variables per service, running `api`+`workers` with `uvicorn`, Docker, local smoke tests |

### [`api-integration-guides/`](api-integration-guides/Document_API_FE_Integration_guide.md) — the full API reference

| File | Covers |
|---|---|
| [`Document_API_FE_Integration_guide.md`](api-integration-guides/Document_API_FE_Integration_guide.md) | Every endpoint (auth, documents, **chat**, **voice**) with exact request/response shapes, every error code, the document status state machine, and the polling pattern for extraction progress |

This is the field-by-field reference; `running-the-project/` is the
shorter walkthrough that gets you to a working call fastest.

## Other docs at this level

- [`github-best-practices.md`](github-best-practices.md) — branching, commit
  message, and PR conventions for this repo. Team workflow, not
  system documentation.

## Backend subsystem docs (live next to their code, not duplicated here)

- [`Backend/scrapers/README.md`](../Backend/scrapers/README.md) — full
  setup/run instructions for the literature-scraping subsystem. The
  architecture-level explanation of *why* it exists is in
  [`architecture/04_literature_ingestion_pipeline.md`](architecture/04_literature_ingestion_pipeline.md);
  this README is the operational how-to.
- [`Backend/README.md`](../Backend/README.md), [`Backend/workers/README.md`](../Backend/workers/README.md) —
  short per-service READMEs (deployment summary, local run command).
  `running-the-project/` supersedes these for anything beyond a one-line
  reminder.

## A note on staleness

Documentation drifts from code. If something here contradicts the actual
code, the code is right — please open an issue or PR fixing the doc. As of
this pass (2026-07), the docs above are verified against the current
`Backend/` implementation; anything describing a previous architecture
(e.g. the Document AI OCR pipeline, superseded by Gemini multimodal
analysis) is explicitly called out as deprecated rather than presented as
current behavior.
