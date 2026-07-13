# 05 — Workers Pipeline (`Backend/workers/pipeline/`)

The document-processing pipeline itself: orchestration, LLM extraction, and
knowledge-graph construction. Uses the clients from
[doc 04](04_workers_core.md). Full flow/rationale in
[doc 01 architecture](../architecture/01_extraction_and_knowledge_graph_pipeline.md).

## `pipeline/document_pipeline.py`

**Purpose:** The single orchestrator function called by `workers/main.py` for every `DocumentUploaded` event.
- `run(document_id, uid)` — the nine-step pipeline: dedup check → per-file download+analyze → aggregate → save extraction → Graphiti ingest → update journey summary (best-effort) → export Cypher → mark `EXTRACTED`. Any unhandled exception marks the document `FAILED` (with the error message attached) and re-raises so the worker's HTTP-level retry logic still applies.
- `_aggregate_extractions(per_file)` — combines multiple per-file LLM extractions into one record (first meaningful `document_type`, deduplicated `document_purpose`s, **earliest** `document_date`, concatenated `episode_body`). Single-file case is a pass-through.

## `pipeline/llm/extractor.py`

**Purpose:** Gemini multimodal document analysis — the step that replaced OCR.
- `analyze_document(file_bytes, filename, mime_type, previous_summary)` → `dict` with exactly `document_type`, `document_purpose`, `document_date`, `episode_body`. Sends the raw file bytes as a multimodal `Part` directly to Gemini (no OCR step). Paced (`pace_gemini_call()`) and time-bounded (`_LLM_CALL_TIMEOUT_S`, 120s default); a timeout raises `TimeoutError` (retryable).
- `update_journey_summary(current_summary, extraction, doc_name)` → updated summary string. Second, separate Gemini call.
- `_extract_json_object(text)` / `_strip_markdown_fences(text)` — tolerant parsing of the LLM's JSON response (finds the first balanced `{...}` block after stripping code fences).
- `_extract_finish_reason(response)` — surfaces Gemini's `finish_reason` (usually `MAX_TOKENS` or `SAFETY`) in the raised exception when the response text is empty, rather than an opaque "empty response."

## `pipeline/llm/prompts.py`

**Purpose:** The two prompt templates `extractor.py` fills in.
- `EXTRACTION_PROMPT` — instructs Gemini to write one rich clinical narrative paragraph covering every entity type the medical schema knows about (patient identifiers, providers, dates, diagnoses, lab results, medications, etc.), then return it plus `document_type`/`document_purpose`/`document_date` as strict JSON. Explicitly does **not** ask for structured entity/edge extraction — that's Graphiti's job against the fixed schema.
- `SUMMARY_UPDATE_PROMPT` — folds one new extraction into the existing journey summary, capped at 3-8 sentences, replacing (not duplicating) superseded facts.

## `pipeline/graph/builder.py`

**Purpose:** Turns one extraction into a Graphiti episode against the fixed medical schema.
- `ingest(graphiti, uid, doc_id, doc_name, extraction)` → `episode_name` (used by the exporter to scope its Cypher query). Prepends the patient-identity header, sets `reference_time` to the document's own parsed date, `group_id=uid`, and passes `MEDICAL_ENTITY_TYPES`/`MEDICAL_EDGE_TYPES`/`MEDICAL_EDGE_TYPE_MAP` on every call.
- `_build_patient_header(uid)` — the fixed `"Patient ID: {uid}.\n"` sentence prepended to every episode body, so Graphiti always anchors to one `Patient` node per user regardless of how a given document refers to the patient.
- `_parse_doc_date(extraction)` — tries 7 date formats (ISO, German, US, long-form, ...) pulled from the LLM's `document_date`; falls back to "now" if nothing parses.

## `pipeline/graph/medical_schema.py`

**Purpose:** The fixed Pydantic entity/edge schema that makes cross-document
entity merging and temporal fact updates possible. Full entity-relationship
picture in
[doc 01 architecture](../architecture/01_extraction_and_knowledge_graph_pipeline.md#component-4--graphiti-ingestion-with-a-fixed-medical-schema-workerspipelinegraph).
- 14 entity `BaseModel`s: `Patient`, `Diagnosis`, `Medication`, `LabTest`, `Procedure`, `Provider` (core); `PathologyResult`, `TumorMarker`, `TreatmentPlan` (oncology); `ImagingResult`, `Symptom`, `Allergy`, `VitalSigns`, `Referral`, `Appointment` (expanded). Each field becomes a structured property on the resulting graph node (e.g. `LabTest.test_value`, `Diagnosis.icd_code`).
- 20 edge `BaseModel`s (empty bodies — the type itself *is* the semantic label): e.g. `HAS_DIAGNOSIS`, `PRESCRIBED`, `INDICATES`, `TREATED_BY`, `RELATES_TO` (fallback).
- `MEDICAL_ENTITY_TYPES`, `MEDICAL_EDGE_TYPES` — the `{name: Model}` dicts passed to `graphiti.add_episode()`.
- `MEDICAL_EDGE_TYPE_MAP` — `{(source_type, target_type): [allowed_edge_types]}`, constraining which relationships are legal between which entity pairs.

## `pipeline/graph/exporter.py`

**Purpose:** Renders the per-document subgraph as a standalone Cypher script and uploads it to GCS for the frontend.
- `generate_and_upload(episode_name, doc_id, file_name, doc_type)` → the GCS URI of the uploaded script.
- `_query_episode_graph(episode_name)` — walks 2 hops out from the episode's `Episodic` node in Neo4j, deduplicating nodes/edges (`LIMIT 300`/`LIMIT 500`).
- `_render_cypher(...)` — builds the human-readable `.cypher` file (a `MATCH path = ... RETURN path` query plus a comment header, ready to paste into Neo4j Browser).
- `_clean(props)` — strips Graphiti-internal properties (`_STRIP` set: embeddings, `group_id`, temporal bookkeeping fields) before they'd otherwise leak into the exported file.
- `_q`, `_props`, `_var` — small Cypher-literal-escaping helpers.

---

## Deprecated / dead code (kept for historical reference only)

These files are **not called by `document_pipeline.py` or `workers/main.py`**
— confirmed by the current pipeline's imports and by
`workers/requirements.txt` no longer listing `google-cloud-documentai`.
Terraform has also removed the Document AI IAM bindings and env vars (see
[doc 05 architecture](../architecture/05_infrastructure_and_deployment.md)).
Do not treat them as describing current behavior.

- **`pipeline/ocr/document_ai.py`**, **`pipeline/ocr/extractor.py`** — the
  old Document AI OCR extraction path Gemini multimodal analysis
  (`pipeline/llm/extractor.py`) replaced.
- **`pipeline/graph/prompts.py`** — prompt templates from the same
  OCR-era pipeline; nothing imports this module anymore.
- Referenced only by `Backend/test_pipeline.py`, itself a standalone local
  smoke-test script for the old OCR+Graphiti path, not part of either
  service.
