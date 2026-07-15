# Class Diagrams (private — not pushed to GitHub)

This folder is listed in `.gitignore` (`Documentation/class-diagrams/`) —
it exists only in this local checkout and won't show up in `git status`,
`git add -A`, or any commit. It's meant to be zipped up and sent directly
rather than merged into the shared docs.

Derived from [`Documentation/code-components/`](../code-components/README.md)
(the per-file reference catalog) — these render the same modules as Mermaid
`classDiagram`s instead of prose. Most of the codebase is plain functions
(FastAPI routes, pipeline steps), so these diagrams focus on the parts that
are genuinely class-shaped: Pydantic models, dataclasses, and the handful of
real subclassing relationships.

## Files

| File | Covers |
|---|---|
| [01_medical_schema.md](01_medical_schema.md) | The fixed entity/edge type schema (`workers/pipeline/graph/medical_schema.py`) that drives the knowledge graph — the richest, most "class-diagram-shaped" part of the codebase |
| [02_domain_models.md](02_domain_models.md) | Firestore-backed domain models (`shared/models/`) — `Document`, `Extraction`, `JourneySummary`, `UserProfile`, `LiteraturePaper`, the error envelope |
| [03_api_request_response_models.md](03_api_request_response_models.md) | The API's wire-format types — every request/response Pydantic model across `main.py`, `chat.py`, `voice.py` |
| [04_pipeline_runtime_classes.md](04_pipeline_runtime_classes.md) | Dataclasses (`RetrievalResult`, `PaperRetrievalResult`, ...), custom exceptions (`APIError`, `DocumentStateError`, ...), and the real subclassing (`PacedGeminiClient(GeminiClient)`, ...) |

Diagrams are Mermaid — render in VS Code with the "Markdown Preview
Mermaid Support" extension, or paste a block into
[mermaid.live](https://mermaid.live) if your friend just wants to view them
without cloning anything.
