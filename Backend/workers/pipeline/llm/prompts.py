"""
LLM prompt templates for document analysis and journey summary updates.

EXTRACTION_PROMPT
  Gemini reads the raw PDF bytes (multimodal) and produces:
    document_type    — what kind of medical document this is
    document_purpose — one sentence: its role in the patient journey
    document_date    — the document's own date (ISO format or null)
    episode_body     — a rich clinical narrative for Graphiti to extract entities from

  Entity/edge extraction is NOT part of the LLM output. It is handled by
  Graphiti's internal LLM against the fixed schema in graph/medical_schema.py.
  This separation enables entity merging and temporal updates across documents.

SUMMARY_UPDATE_PROMPT
  Updates the running patient journey summary after each new document.
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
entities and their relationships. The engine understands these entity types:
  Patient, Diagnosis, Medication, LabTest, Procedure, Provider,
  PathologyResult, TumorMarker, TreatmentPlan,
  ImagingResult, Symptom, Allergy, VitalSigns, Referral, Appointment.

Write the narrative so that ALL entity types present in the document are
mentioned explicitly — even if this is a referral letter, radiology report,
discharge summary, or any other document type.

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
  • Imaging/radiology findings: modality, body region, key finding, impression
  • Symptoms or complaints: what the patient reports, severity, onset
  • Allergies or drug intolerances mentioned in the document
  • Vital signs: blood pressure, pulse, weight, height, temperature if present
  • Referrals: who is referring, to whom, for what reason
  • Scheduled appointments or follow-up plans
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
Return ONLY valid JSON with exactly these four keys — no markdown, no extra text.

{{
  "document_type": "Exact German document type: Laborbericht | Arztbrief | Verlaufsbericht | Befundbericht | Tumorkonferenzprotokoll | Überweisungsbrief | Pathologiebericht | Radiologiebericht | etc.",
  "document_purpose": "One sentence: what this document is and its role in this patient's journey.",
  "document_date": "The date of this document in YYYY-MM-DD format. Use the report date, visit date, or issue date — whichever appears in the document. Return null if no date is present.",
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
