"""
LLM prompt templates for the pipeline refinement.

EXTRACTION_PROMPT
  The LLM reads the PDF and produces ONLY:
    1. document_type    — what kind of document this is
    2. document_purpose — one sentence: its role in the patient journey
    3. episode_body     — a rich clinical narrative paragraph

  Entity/edge types are NO LONGER part of the LLM output. They come from the
  fixed schema in medical_schema.py. Graphiti's internal LLM extracts entities
  from the narrative against that consistent schema — this is what enables
  entity merging and temporal updates across documents.

SUMMARY_UPDATE_PROMPT
  Updates the running patient journey summary after each document.
"""

# ── Document extraction prompt ────────────────────────────────────────────────

EXTRACTION_PROMPT = """\
You are a medical scribe preparing documents for a patient journey knowledge graph.

CONTEXT
=======
Document filename  : {filename}
Patient journey so far (previous summary):
{summary}

TASK
====
Read this medical document and write ONE rich clinical narrative paragraph
that captures everything medically relevant about this document.

This paragraph is what an AI knowledge graph engine will read to extract
entities (Patient, Diagnosis, Medication, LabTest, Procedure, Provider,
PathologyResult, TumorMarker, TreatmentPlan) and their relationships.

WHAT TO INCLUDE in the narrative
  • Patient identifiers: full name as written, date of birth, patient/case ID
  • All providers: doctor names, clinic names, departments, addresses
  • All dates: document date, test dates, procedure dates, diagnosis dates
  • All diagnoses: full name, ICD code if present, staging, status
  • All lab results: test name, value, unit, reference range, interpretation
  • All tumor markers: name, value, unit, normal range
  • All procedures done or planned: name, date, outcome
  • All medications: name, dosage, route, frequency, start/stop dates
  • Pathology findings: Gleason score, grade, specimen site, finding
  • Treatment decisions or recommendations made in this document
  • Any changes from previous findings (e.g. PSA changed from X to Y)

STYLE
  • Single flowing paragraph — no bullet points, no headers, no JSON
  • Write in English; keep original medical terms (ICD codes, drug names,
    lab abbreviations, German anatomical terms) exactly as written
  • Be specific and complete — include all numbers, dates, and values
  • Reference the patient by the same consistent identifier used in all
    documents (e.g. "Patient-1" if that is how they appear in the document)

OUTPUT FORMAT
=============
Return ONLY valid JSON with exactly these three keys — no markdown, no extra text.

{{
  "document_type": "Exact German document type: Laborbericht | Arztbrief | Verlaufsbericht | Befundbericht | Tumorkonferenzprotokoll | Überweisungsbrief | Pathologiebericht | etc.",
  "document_purpose": "One sentence: what this document is and its role in this patient's journey.",
  "episode_body": "Full clinical narrative paragraph here..."
}}
"""


# ── Journey summary update prompt ─────────────────────────────────────────────

SUMMARY_UPDATE_PROMPT = """\
You are a medical case manager maintaining a concise patient journey summary.

CURRENT SUMMARY
===============
{current_summary}

NEW DOCUMENT PROCESSED
=======================
File    : {doc_name}
Type    : {doc_type}
Purpose : {doc_purpose}

CLINICAL NARRATIVE FROM NEW DOCUMENT
=====================================
{episode_body}

TASK
====
Update the patient journey summary to reflect information from the new document.

RULES
  • 3–8 sentences maximum — be very concise
  • Chronological order where possible
  • Capture: diagnoses, key tests performed, treatments started/changed, important dates
  • Do not repeat information already in the summary unless it was updated by new data
  • If new info supersedes old, replace it — do not duplicate
  • Plain medical English — no bullet points, no markdown, no headers
  • Output ONLY the updated summary text, nothing else
"""
