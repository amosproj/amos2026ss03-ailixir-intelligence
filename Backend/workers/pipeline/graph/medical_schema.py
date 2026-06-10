"""
Medical entity and edge type schema for patient journey knowledge graphs.

Passing a FIXED schema to graphiti.add_episode() on every call is what enables:
  - Cross-document entity merging (same Patient/Diagnosis/Medication node reused)
  - Temporal updates (old PSA value expired, new one created)
  - Consistent relationship types regardless of document type

The LLM extraction step (pipeline/llm/extractor.py) writes only the narrative
paragraph (episode_body). Graphiti's own internal LLM then extracts entities
from that narrative and maps them onto these types.

Schema covers oncology and general practice:
  Core:      Patient, Diagnosis, Medication, LabTest, Procedure, Provider
  Oncology:  PathologyResult, TumorMarker, TreatmentPlan
  Expanded:  ImagingResult, Symptom, Allergy, VitalSigns, Referral, Appointment
"""

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Entity types
# ─────────────────────────────────────────────────────────────────────────────

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


# ── Expanded entity types ─────────────────────────────────────────────────────

class ImagingResult(BaseModel):
    """A radiological or imaging finding from MRI, CT, X-ray, ultrasound, PET, or scintigraphy."""
    modality: str | None = Field(None, description="Imaging modality: MRI, CT, X-ray, Ultrasound, PET, Scintigraphy")
    body_region: str | None = Field(None, description="Anatomical region examined, e.g. abdomen, pelvis, thorax")
    finding: str | None = Field(None, description="Key radiological finding or observation")
    impression: str | None = Field(None, description="Radiologist's conclusion or impression")
    imaging_date: str | None = Field(None, description="Date the imaging was performed")


class Symptom(BaseModel):
    """A symptom, complaint, or clinical observation reported by the patient or clinician."""
    severity: str | None = Field(None, description="Severity: mild, moderate, severe")
    onset_date: str | None = Field(None, description="When the symptom first appeared")
    duration: str | None = Field(None, description="How long the symptom has been present, e.g. 3 weeks")
    status: str | None = Field(None, description="Current status: active, resolved, intermittent")


class Allergy(BaseModel):
    """A drug allergy, intolerance, or adverse reaction documented for the patient."""
    allergen: str | None = Field(None, description="Substance causing the allergy or intolerance")
    reaction_type: str | None = Field(None, description="Type of reaction: anaphylaxis, rash, nausea, intolerance")
    severity: str | None = Field(None, description="Severity: mild, moderate, severe, life-threatening")
    documented_date: str | None = Field(None, description="Date the allergy was first documented")


class VitalSigns(BaseModel):
    """Vital sign measurements: blood pressure, pulse, weight, height, temperature, etc."""
    measurement_date: str | None = Field(None, description="Date the vital signs were recorded")
    blood_pressure: str | None = Field(None, description="Blood pressure reading, e.g. 130/85 mmHg")
    heart_rate: str | None = Field(None, description="Heart rate in bpm, e.g. 72 bpm")
    weight: str | None = Field(None, description="Body weight, e.g. 82 kg")
    height: str | None = Field(None, description="Body height, e.g. 178 cm")
    temperature: str | None = Field(None, description="Body temperature, e.g. 37.2 °C")
    oxygen_saturation: str | None = Field(None, description="SpO2 reading, e.g. 98%")


class Referral(BaseModel):
    """A referral, consultation request, or transfer between medical providers or departments."""
    referral_date: str | None = Field(None, description="Date the referral was issued")
    reason: str | None = Field(None, description="Clinical reason or question for the referral")
    urgency: str | None = Field(None, description="Urgency level: routine, urgent, emergency")
    referring_provider: str | None = Field(None, description="Provider or department issuing the referral")
    target_specialty: str | None = Field(None, description="Specialty or department the patient is referred to")


class Appointment(BaseModel):
    """A scheduled medical appointment, follow-up visit, or planned review."""
    appointment_date: str | None = Field(None, description="Date of the scheduled appointment")
    appointment_type: str | None = Field(None, description="Type: follow-up, control, surgery, chemotherapy session")
    purpose: str | None = Field(None, description="Clinical purpose of the appointment")
    location: str | None = Field(None, description="Clinic, department, or institution where the appointment is scheduled")


# ─────────────────────────────────────────────────────────────────────────────
# Edge types
# ─────────────────────────────────────────────────────────────────────────────

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

class HAS_IMAGING(BaseModel):
    """Patient had this imaging study performed."""

class HAS_SYMPTOM(BaseModel):
    """Patient presents with or reported this symptom."""

class HAS_ALLERGY(BaseModel):
    """Patient has this documented allergy or intolerance."""

class HAS_VITAL_SIGNS(BaseModel):
    """Patient has these vital sign measurements recorded at a point in time."""

class WAS_REFERRED(BaseModel):
    """Patient was referred via this referral to another provider or specialty."""

class HAS_APPOINTMENT(BaseModel):
    """Patient has this scheduled appointment or follow-up."""

class TREATED_BY(BaseModel):
    """A diagnosis is being treated by this medication or procedure."""

class CONFIRMED_BY(BaseModel):
    """A diagnosis is confirmed or supported by this lab test, imaging, or pathology result."""

class INDICATES(BaseModel):
    """A lab test, imaging result, or tumor marker value indicates this diagnosis."""

class PERFORMED_BY(BaseModel):
    """A procedure or imaging study was performed by or at this provider."""

class MANAGED_AT(BaseModel):
    """Patient is managed, treated, or followed up at this provider or institution."""

class HAS_TREATMENT_PLAN(BaseModel):
    """Patient has this treatment plan or care recommendation."""

class REFERRED_TO(BaseModel):
    """A referral sends the patient to this provider or specialty."""

class SYMPTOM_OF(BaseModel):
    """This symptom is associated with or caused by this diagnosis."""

class RELATES_TO(BaseModel):
    """General relationship between two entities (fallback for uncovered cases)."""


# ─────────────────────────────────────────────────────────────────────────────
# Assembled dicts passed to graphiti.add_episode()
# ─────────────────────────────────────────────────────────────────────────────

MEDICAL_ENTITY_TYPES: dict = {
    # Core
    "Patient":          Patient,
    "Diagnosis":        Diagnosis,
    "Medication":       Medication,
    "LabTest":          LabTest,
    "Procedure":        Procedure,
    "Provider":         Provider,
    # Oncology
    "PathologyResult":  PathologyResult,
    "TumorMarker":      TumorMarker,
    "TreatmentPlan":    TreatmentPlan,
    # Expanded
    "ImagingResult":    ImagingResult,
    "Symptom":          Symptom,
    "Allergy":          Allergy,
    "VitalSigns":       VitalSigns,
    "Referral":         Referral,
    "Appointment":      Appointment,
}

MEDICAL_EDGE_TYPES: dict = {
    # Patient → clinical findings
    "HAS_DIAGNOSIS":      HAS_DIAGNOSIS,
    "UNDERWENT":          UNDERWENT,
    "PRESCRIBED":         PRESCRIBED,
    "HAD_LAB_TEST":       HAD_LAB_TEST,
    "HAS_TUMOR_MARKER":   HAS_TUMOR_MARKER,
    "HAS_PATHOLOGY":      HAS_PATHOLOGY,
    "HAS_IMAGING":        HAS_IMAGING,
    "HAS_SYMPTOM":        HAS_SYMPTOM,
    "HAS_ALLERGY":        HAS_ALLERGY,
    "HAS_VITAL_SIGNS":    HAS_VITAL_SIGNS,
    "WAS_REFERRED":       WAS_REFERRED,
    "HAS_APPOINTMENT":    HAS_APPOINTMENT,
    # Clinical relationships
    "TREATED_BY":         TREATED_BY,
    "CONFIRMED_BY":       CONFIRMED_BY,
    "INDICATES":          INDICATES,
    "PERFORMED_BY":       PERFORMED_BY,
    "MANAGED_AT":         MANAGED_AT,
    "HAS_TREATMENT_PLAN": HAS_TREATMENT_PLAN,
    "REFERRED_TO":        REFERRED_TO,
    "SYMPTOM_OF":         SYMPTOM_OF,
    # Fallback
    "RELATES_TO":         RELATES_TO,
}

MEDICAL_EDGE_TYPE_MAP: dict[tuple[str, str], list[str]] = {
    # Patient → direct findings
    ("Patient",   "Diagnosis"):        ["HAS_DIAGNOSIS"],
    ("Patient",   "Procedure"):        ["UNDERWENT"],
    ("Patient",   "Medication"):       ["PRESCRIBED"],
    ("Patient",   "LabTest"):          ["HAD_LAB_TEST"],
    ("Patient",   "TumorMarker"):      ["HAS_TUMOR_MARKER"],
    ("Patient",   "PathologyResult"):  ["HAS_PATHOLOGY"],
    ("Patient",   "ImagingResult"):    ["HAS_IMAGING"],
    ("Patient",   "Symptom"):          ["HAS_SYMPTOM"],
    ("Patient",   "Allergy"):          ["HAS_ALLERGY"],
    ("Patient",   "VitalSigns"):       ["HAS_VITAL_SIGNS"],
    ("Patient",   "Referral"):         ["WAS_REFERRED"],
    ("Patient",   "Appointment"):      ["HAS_APPOINTMENT"],
    ("Patient",   "Provider"):         ["MANAGED_AT"],
    ("Patient",   "TreatmentPlan"):    ["HAS_TREATMENT_PLAN"],
    # Diagnosis relationships
    ("Diagnosis", "Medication"):       ["TREATED_BY"],
    ("Diagnosis", "LabTest"):          ["CONFIRMED_BY"],
    ("Diagnosis", "PathologyResult"):  ["CONFIRMED_BY"],
    ("Diagnosis", "ImagingResult"):    ["CONFIRMED_BY"],
    ("Diagnosis", "TreatmentPlan"):    ["HAS_TREATMENT_PLAN"],
    # Tests and imaging indicate diagnoses
    ("LabTest",          "Diagnosis"): ["INDICATES"],
    ("TumorMarker",      "Diagnosis"): ["INDICATES"],
    ("PathologyResult",  "Diagnosis"): ["CONFIRMED_BY"],
    ("ImagingResult",    "Diagnosis"): ["INDICATES"],
    # Symptoms relate to diagnoses
    ("Symptom",          "Diagnosis"): ["SYMPTOM_OF"],
    # Procedures and imaging performed by providers
    ("Procedure",        "Provider"):  ["PERFORMED_BY"],
    ("ImagingResult",    "Provider"):  ["PERFORMED_BY"],
    # Medications treat diagnoses
    ("Medication",       "Diagnosis"): ["TREATED_BY"],
    # Referrals point to providers
    ("Referral",         "Provider"):  ["REFERRED_TO"],
    # Appointments at providers
    ("Appointment",      "Provider"):  ["RELATES_TO"],
    # Fallback for any other entity pair
    ("Entity",           "Entity"):    ["RELATES_TO"],
}
