"""
LLM prompt templates for the pipeline refinement.

EXTRACTION_PROMPT
  Reads the PDF and produces:
  1. episode_body  — a rich narrative paragraph that Graphiti will extract
                     entities and relationships from. This is the main text
                     Graphiti's LLM processes.
  2. entity_types  — which entity types (+ field schemas) Graphiti should
                     look for in that paragraph.
  3. edge_types    — the relationship classes Graphiti can create.
  4. edge_type_map — which relationships are valid between which entity pairs.

SUMMARY_UPDATE_PROMPT
  Updates the running patient journey summary after each document.
"""

# ── Document extraction prompt ────────────────────────────────────────────────

EXTRACTION_PROMPT = """\
You are a medical knowledge graph assistant preparing documents for a patient \
journey knowledge graph built with Graphiti (a temporal graph framework).

CONTEXT
=======
Document filename  : {filename}
Patient journey so far (previous summary):
{summary}

HOW GRAPHITI WORKS
==================
Graphiti takes a plain-text paragraph (called "episode_body") and automatically
extracts entities and relationships from it. You guide that extraction by also
providing:
  - entity_types : which kinds of entities to look for (e.g. Diagnosis, Medication)
  - edge_types   : which kinds of relationships exist
  - edge_type_map: which relationships are valid between which entity pairs

YOUR TASK
=========
Read this medical document and produce four things:

1. episode_body
   A single flowing narrative paragraph (200–400 words) that tells the story of
   what this document contains from the perspective of the patient's journey.
   Write it like a clinical case note — include all clinically relevant facts:
   who the patient is, who the provider is, what was found, measured or done,
   dates, values, units, diagnosis names, medication names, dosages, stages, etc.
   Write in English. Keep original medical terms (ICD codes, drug names, lab
   abbreviations) as-is. Do NOT use bullet points or headings inside this text.
   This paragraph is what Graphiti will read to build the knowledge graph.

2. entity_types
   A list of entity type definitions relevant to THIS document.
   Each entry has:
     name        — PascalCase type name (e.g. "Diagnosis", "LabTest")
     description — one sentence Graphiti uses to classify entities (important!)
     fields      — list of {{name, description}} for each property

   Only define types that genuinely appear in this document.
   Use these standard medical types where they fit:
     Patient, Diagnosis, Medication, LabTest, Procedure,
     Provider, TumorMarker, Pathology, TreatmentResponse, Symptom

3. edge_types
   A list of relationship type definitions.
   Each entry has:
     name        — UPPER_SNAKE_CASE (e.g. "HAS_DIAGNOSIS", "TREATED_BY")
     description — one sentence describing when this edge applies

4. edge_type_map
   A list of {{source, target, relations}} entries constraining which relationships
   are valid between which entity pairs.
   "Entity" can be used as a wildcard type for fallback rules.

OUTPUT FORMAT
=============
Return ONLY valid JSON — no markdown, no explanation, nothing outside the JSON.

{{
  "document_type": "Laborbericht | Arztbrief | Verlaufsbericht | Befundbericht | Tumorkonferenzprotokoll | Überweisungsbrief | Pathologiebericht | etc.",
  "document_purpose": "One sentence: what this document is and its role in the patient journey.",
  "episode_body": "Full clinical narrative paragraph here...",
  "entity_types": [
    {{
      "name": "EntityTypeName",
      "description": "One sentence Graphiti uses to classify this entity type.",
      "fields": [
        {{"name": "field_name", "description": "what this field captures"}}
      ]
    }}
  ],
  "edge_types": [
    {{
      "name": "EDGE_TYPE_NAME",
      "description": "One sentence describing when this relationship applies."
    }}
  ],
  "edge_type_map": [
    {{
      "source": "SourceEntityType",
      "target": "TargetEntityType",
      "relations": ["EDGE_TYPE_NAME"]
    }}
  ]
}}

RULES
  • episode_body must be prose — no JSON, no bullets, no headings inside it
  • entity_types and edge_types must only include types present in THIS document
  • Descriptions are read by Graphiti's LLM — make them precise and unambiguous
  • All field names: snake_case
  • Edge type names: UPPER_SNAKE_CASE
  • Entity type names: PascalCase
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
