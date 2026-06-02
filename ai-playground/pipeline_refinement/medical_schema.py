"""
Fixed medical entity and edge type schema for patient journey knowledge graphs.

This schema is CONSISTENT across every document upload. Using a fixed schema
is what enables Graphiti to:
  - Recognise the same real-world entity across multiple documents and merge them
  - Track temporal changes (e.g. PSA level changes, diagnosis stage updates)
  - Build a patient-centred graph rather than isolated per-document snapshots

The LLM only writes the narrative paragraph (episode_body). Graphiti's own
internal LLM then extracts entities from that narrative and maps them onto
these types — including resolving "Patient-1" in document 1 with "Patient-1"
in document 5 as the same node, and expiring old facts when new ones contradict.
"""

from pydantic import BaseModel, Field


# ── Entity types ──────────────────────────────────────────────────────────────

class Patient(BaseModel):
    """The patient whose medical journey is being tracked."""
    patient_id: str | None = Field(None, description="Hospital or clinic patient ID / Fallnummer")
    date_of_birth: str | None = Field(None, description="Patient's date of birth")
    gender: str | None = Field(None, description="Patient's gender")


class Diagnosis(BaseModel):
    """A confirmed or suspected medical diagnosis or condition."""
    icd_code: str | None = Field(None, description="ICD-10 diagnosis code, e.g. C61")
    stage: str | None = Field(None, description="Disease stage or classification, e.g. T2a, ISUP Grade 2")
    date_confirmed: str | None = Field(None, description="Date the diagnosis was confirmed")
    status: str | None = Field(None, description="Diagnosis status: active, resolved, suspected, remission")


class Medication(BaseModel):
    """A medication, drug, or pharmaceutical treatment prescribed or administered."""
    dosage: str | None = Field(None, description="Dosage amount and unit, e.g. 500mg")
    route: str | None = Field(None, description="Administration route: oral, IV, subcutaneous")
    frequency: str | None = Field(None, description="Dosing frequency, e.g. once daily, every 3 weeks")
    start_date: str | None = Field(None, description="Date medication was started or prescribed")
    end_date: str | None = Field(None, description="Date medication was stopped or completed")


class LabTest(BaseModel):
    """A laboratory test, blood test, or diagnostic measurement."""
    test_value: str | None = Field(None, description="Measured value of the test result, e.g. 7.6")
    unit: str | None = Field(None, description="Unit of measurement, e.g. ng/ml, g/dL")
    reference_range: str | None = Field(None, description="Normal reference range, e.g. 0–4.0 ng/ml")
    test_date: str | None = Field(None, description="Date the test was performed or reported")
    result_status: str | None = Field(None, description="Result interpretation: normal, elevated, low, critical")


class Procedure(BaseModel):
    """A medical procedure, surgery, biopsy, or clinical intervention."""
    procedure_date: str | None = Field(None, description="Date the procedure was performed")
    outcome: str | None = Field(None, description="Outcome or result of the procedure")
    indication: str | None = Field(None, description="Clinical reason or indication for the procedure")


class Provider(BaseModel):
    """A medical provider, doctor, hospital, clinic, or department."""
    specialty: str | None = Field(None, description="Medical specialty, e.g. Oncology, Urology, Radiology")
    institution: str | None = Field(None, description="Hospital, clinic, or institution name")
    department: str | None = Field(None, description="Department or ward within the institution")


class PathologyResult(BaseModel):
    """A pathology finding from biopsy, tissue analysis, or histological examination."""
    grade: str | None = Field(None, description="Pathological grade or scoring, e.g. Gleason 3+4=7")
    finding: str | None = Field(None, description="Key pathological finding or diagnosis")
    specimen_site: str | None = Field(None, description="Anatomical site of the tissue or specimen")
    pathology_date: str | None = Field(None, description="Date of the pathology report")


class TumorMarker(BaseModel):
    """A tumor marker or cancer biomarker measurement, e.g. PSA, CA-125, CEA."""
    marker_value: str | None = Field(None, description="Measured biomarker value, e.g. 7.6")
    unit: str | None = Field(None, description="Unit of measurement, e.g. ng/ml, U/ml")
    reference_range: str | None = Field(None, description="Normal reference range for the marker")
    test_date: str | None = Field(None, description="Date the biomarker was measured")


class TreatmentPlan(BaseModel):
    """A clinical treatment plan, therapy decision, or care recommendation."""
    therapy_type: str | None = Field(None, description="Type of therapy: surgery, radiotherapy, chemotherapy, surveillance")
    planned_start: str | None = Field(None, description="Planned or actual start date of treatment")
    recommendation: str | None = Field(None, description="Clinical recommendation or decision made")
    decision_date: str | None = Field(None, description="Date the treatment decision was made")


# ── Edge types ────────────────────────────────────────────────────────────────

class HAS_DIAGNOSIS(BaseModel):
    """Patient has or received this diagnosis."""

class UNDERWENT(BaseModel):
    """Patient underwent or is scheduled for this procedure."""

class PRESCRIBED(BaseModel):
    """Patient was prescribed or is taking this medication."""

class HAD_LAB_TEST(BaseModel):
    """Patient had this laboratory test performed."""

class HAS_TUMOR_MARKER(BaseModel):
    """Patient has this tumor marker measurement."""

class HAS_PATHOLOGY(BaseModel):
    """Patient has this pathology result from biopsy or tissue analysis."""

class TREATED_BY(BaseModel):
    """A diagnosis is being treated by this medication or procedure."""

class CONFIRMED_BY(BaseModel):
    """A diagnosis is confirmed or supported by this lab test or pathology result."""

class INDICATES(BaseModel):
    """A lab test or tumor marker value indicates this diagnosis."""

class PERFORMED_BY(BaseModel):
    """A procedure was performed by or at this provider."""

class MANAGED_AT(BaseModel):
    """Patient is managed, treated, or followed up at this provider or institution."""

class HAS_TREATMENT_PLAN(BaseModel):
    """Patient has this treatment plan or care recommendation."""

class RELATES_TO(BaseModel):
    """General relationship between two entities (fallback)."""


# ── Assembled dicts for graphiti.add_episode() ────────────────────────────────

MEDICAL_ENTITY_TYPES: dict = {
    "Patient":        Patient,
    "Diagnosis":      Diagnosis,
    "Medication":     Medication,
    "LabTest":        LabTest,
    "Procedure":      Procedure,
    "Provider":       Provider,
    "PathologyResult": PathologyResult,
    "TumorMarker":    TumorMarker,
    "TreatmentPlan":  TreatmentPlan,
}

MEDICAL_EDGE_TYPES: dict = {
    "HAS_DIAGNOSIS":     HAS_DIAGNOSIS,
    "UNDERWENT":         UNDERWENT,
    "PRESCRIBED":        PRESCRIBED,
    "HAD_LAB_TEST":      HAD_LAB_TEST,
    "HAS_TUMOR_MARKER":  HAS_TUMOR_MARKER,
    "HAS_PATHOLOGY":     HAS_PATHOLOGY,
    "TREATED_BY":        TREATED_BY,
    "CONFIRMED_BY":      CONFIRMED_BY,
    "INDICATES":         INDICATES,
    "PERFORMED_BY":      PERFORMED_BY,
    "MANAGED_AT":        MANAGED_AT,
    "HAS_TREATMENT_PLAN": HAS_TREATMENT_PLAN,
    "RELATES_TO":        RELATES_TO,
}

MEDICAL_EDGE_TYPE_MAP: dict[tuple[str, str], list[str]] = {
    ("Patient",   "Diagnosis"):       ["HAS_DIAGNOSIS"],
    ("Patient",   "Procedure"):       ["UNDERWENT"],
    ("Patient",   "Medication"):      ["PRESCRIBED"],
    ("Patient",   "LabTest"):         ["HAD_LAB_TEST"],
    ("Patient",   "TumorMarker"):     ["HAS_TUMOR_MARKER"],
    ("Patient",   "PathologyResult"): ["HAS_PATHOLOGY"],
    ("Patient",   "Provider"):        ["MANAGED_AT"],
    ("Patient",   "TreatmentPlan"):   ["HAS_TREATMENT_PLAN"],
    ("Diagnosis", "Medication"):      ["TREATED_BY"],
    ("Diagnosis", "LabTest"):         ["CONFIRMED_BY"],
    ("Diagnosis", "PathologyResult"): ["CONFIRMED_BY"],
    ("Diagnosis", "TreatmentPlan"):   ["HAS_TREATMENT_PLAN"],
    ("Procedure", "Provider"):        ["PERFORMED_BY"],
    ("LabTest",   "Diagnosis"):       ["INDICATES"],
    ("TumorMarker", "Diagnosis"):     ["INDICATES"],
    ("PathologyResult", "Diagnosis"): ["CONFIRMED_BY"],
    ("Medication", "Diagnosis"):      ["TREATED_BY"],
    ("Entity",    "Entity"):          ["RELATES_TO"],  # fallback
}
