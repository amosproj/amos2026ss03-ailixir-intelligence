# Running the Project

Stage 3 of the documentation pass. This folder answers one question: **how
do I actually run/use Ailixir**, as opposed to *how it's built*
([`Documentation/architecture/`](../architecture/README.md)) or *what each
file does* ([`Documentation/code-components/`](../code-components/README.md)).

Since the project is open source, there are two genuinely different
audiences here, and they need different instructions:

| | You want to... | Go to |
|---|---|---|
| **1** | Play with the **already-deployed** system — sign up, upload a document, watch it get extracted into a knowledge graph, chat against it — without installing or configuring anything yourself | [01 — Using the Deployed System](01_using_the_deployed_system.md) |
| **2** | Run your **own instance** — clone the repo, bring your own GCP/Firebase/Neo4j/AstraDB, and run the API + worker services locally (or deploy your own copy) | [02 — Running Locally](02_running_locally.md) |

Both paths hit the same API surface described in
[`Documentation/api-integration-guides/Document_API_FE_Integration_guide.md`](../api-integration-guides/Document_API_FE_Integration_guide.md)
(the full endpoint reference — request/response shapes, every error code).
The two docs in this folder are task-oriented walkthroughs; that guide is the
thing to open when you need the exact shape of a field.

## What "the project" actually is

There's no single thing to "start" — Ailixir's backend is two independent
services plus one scheduled job (see
[`architecture/05_infrastructure_and_deployment.md`](../architecture/05_infrastructure_and_deployment.md)):

- **`api`** — the public FastAPI service (auth, document upload, chat, voice).
- **`workers`** — the internal FastAPI service that does the actual document
  extraction + knowledge-graph building, triggered by Pub/Sub. You never call
  this directly; it reacts to what `api` publishes.
- **`scrapers`** — a standalone monthly batch job that fills the
  research-paper corpus chat reads from. Not needed to try the core
  upload/extract/chat flow — see
  [`architecture/04_literature_ingestion_pipeline.md`](../architecture/04_literature_ingestion_pipeline.md)
  if you want to run it too.

> **Note:** `Documentation/Run_Extraction_Pipeline.md` (repo root of
> `Documentation/`) is the earlier version of the walkthrough now expanded in
> [01 — Using the Deployed System](01_using_the_deployed_system.md) (which
> additionally covers chat, not just the extraction step). It hasn't been
> deleted — ping the maintainer if you want it removed now that this folder
> covers the same ground.
