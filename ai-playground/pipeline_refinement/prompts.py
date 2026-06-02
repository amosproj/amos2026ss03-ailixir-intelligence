"""
LLM prompt templates for the pipeline refinement.

Two prompts:
  EXTRACTION_PROMPT   — Gemini reads the PDF and produces a structured JSON with
                        entity_types, edge_types, extracted entities and relationships.
  SUMMARY_UPDATE_PROMPT — Gemini updates the running patient journey summary
                          after each new document.
"""

# ── Document extraction prompt ────────────────────────────────────────────────
# The model receives the raw PDF bytes + this text prompt.
# It decides which entity/edge types are relevant for THIS document
# given the patient's existing journey context.

EXTRACTION_PROMPT = """\
You are a medical knowledge graph extraction engine for patient journey analysis.

CONTEXT
=======
Document filename : {filename}
Patient journey so far (previous summary):
{summary}

TASK
====
Read this medical document and extract structured information for a patient journey
knowledge graph. The graph tracks what happened to the patient over time.

STEP 1 – Understand the document
  Determine the document's type and its precise role in the patient's journey.

STEP 2 – Decide relevant entity + edge types
  Based on what is ACTUALLY IN this document (and the journey context above),
  choose which entity types and relationship types to extract.
  Only include types that genuinely appear in this document.

STEP 3 – Extract entities and relationships
  Pull out every clinically meaningful piece of information.
  Stay faithful to the source — do not invent or infer beyond what is written.

FOCUS ON (journey-relevant only)
  Diagnoses (name, ICD code, stage, date)
  Medications / treatments (name, dosage, route, start/end dates)
  Lab tests and results (name, value, unit, reference range, date)
  Procedures / interventions (name, date, outcome)
  Medical providers (name, specialty, institution)
  Key clinical dates and timeline events
  Tumor markers, pathology findings, staging info when present

IGNORE
  Administrative data, billing codes, page headers/footers, signatures

EXAMPLE ENTITY TYPES (adapt — only use types present in this document)
  Patient      : name, date_of_birth, patient_id, gender
  Diagnosis    : name, icd_code, stage, date_confirmed, status
  Medication   : name, dosage, route, frequency, start_date, end_date
  LabTest      : name, value, unit, reference_range, date, status
  Procedure    : name, date, description, outcome
  Provider     : name, specialty, institution
  TumorMarker  : name, value, unit, date
  Pathology    : finding, grade, date, specimen_site

EXAMPLE EDGE TYPES (adapt to what you find)
  Patient → HAS_DIAGNOSIS → Diagnosis
  Patient → UNDERWENT → Procedure
  Patient → TAKES_MEDICATION → Medication
  Diagnosis → TREATED_BY → Medication
  Diagnosis → CONFIRMED_BY → LabTest / Pathology
  Procedure → PERFORMED_BY → Provider
  LabTest → MONITORS → Medication
  Medication → CONTRAINDICATED_WITH → Medication

OUTPUT FORMAT
=============
Return ONLY valid JSON — no markdown fences, no explanation, nothing outside the JSON.

{{
  "document_purpose": "One precise sentence describing this document's role in the patient journey",
  "document_type": "exact German type: Laborbericht | Arztbrief | Verlaufsbericht | Befundbericht | Tumorkonferenzprotokoll | Überweisungsbrief | Pathologiebericht | etc.",
  "entity_types": {{
    "EntityTypeName": {{
      "property_name": "what this property captures"
    }}
  }},
  "edge_types": [
    {{
      "source_type": "SourceEntityType",
      "target_type": "TargetEntityType",
      "relations": ["RELATION_IN_UPPER_SNAKE_CASE"]
    }}
  ],
  "entities": [
    {{
      "type": "EntityTypeName",
      "id": "entitytype:key-info",
      "properties": {{
        "property_name": "extracted value or null"
      }}
    }}
  ],
  "relationships": [
    {{
      "source_id": "entity-id",
      "target_id": "entity-id",
      "type": "RELATION_IN_UPPER_SNAKE_CASE",
      "properties": {{}}
    }}
  ]
}}

RULES
  • entity_types  → schema only (property names + their purpose), not values
  • entities      → actual instances with real extracted values
  • null          → for missing/unknown values, never empty string
  • Entity IDs    → deterministic: "type:key-info"  e.g. "diagnosis:breast-cancer", "labtest:cbc-2024-01-15"
  • Relation types → UPPER_SNAKE_CASE
  • Entity type names → PascalCase
  • Document is likely in German — translate entity type names to English,
    keep property values as-is (original German/Latin medical terms are fine)
"""


# ── Journey summary update prompt ─────────────────────────────────────────────
# The model receives the current plain-text summary and the key facts from
# the new extraction, and produces a concise updated summary.

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

KEY FINDINGS FROM THE NEW DOCUMENT
===================================
{findings}

TASK
====
Update the patient journey summary to reflect information from the new document.

RULES
  • 3–8 sentences maximum — be very concise
  • Chronological order where possible
  • Capture: diagnoses, key tests performed, treatments started/changed, important dates
  • Do not repeat information already in the summary unless it was updated
  • If new info supersedes old info, replace it — do not duplicate
  • Plain medical language — no bullet points, no markdown, no headers
  • Output ONLY the updated summary text, nothing else
"""
