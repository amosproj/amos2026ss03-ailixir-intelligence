"""
Medical document schema for the Allixer project.
Covers clinical notes, lab reports, prescriptions, discharge summaries.
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import date


# ─────────────────────────────────────────────
#  Normalisation maps  (extend as needed)
# ─────────────────────────────────────────────

DIAGNOSIS_ALIASES: dict[str, str] = {
    # Diabetes
    "t2dm": "Type 2 Diabetes Mellitus",
    "type 2 diabetes": "Type 2 Diabetes Mellitus",
    "diabetes mellitus type ii": "Type 2 Diabetes Mellitus",
    "diabetes mellitus type 2": "Type 2 Diabetes Mellitus",
    "dm2": "Type 2 Diabetes Mellitus",
    "niddm": "Type 2 Diabetes Mellitus",
    "t1dm": "Type 1 Diabetes Mellitus",
    "type 1 diabetes": "Type 1 Diabetes Mellitus",
    # Hypertension
    "htn": "Hypertension",
    "high blood pressure": "Hypertension",
    "arterial hypertension": "Hypertension",
    # MI
    "heart attack": "Myocardial Infarction",
    "mi": "Myocardial Infarction",
    "ami": "Acute Myocardial Infarction",
    # COPD
    "chronic obstructive pulmonary disease": "COPD",
    "copd": "COPD",
    # CKD
    "chronic kidney disease": "CKD",
    "renal failure": "CKD",
}

MEDICATION_ALIASES: dict[str, str] = {
    "paracetamol": "Acetaminophen",
    "tylenol": "Acetaminophen",
    "advil": "Ibuprofen",
    "nurofen": "Ibuprofen",
    "aspirin": "Acetylsalicylic Acid",
    "metformin hcl": "Metformin",
    "glucophage": "Metformin",
    "amlodipine besylate": "Amlodipine",
    "norvasc": "Amlodipine",
    "atorvastatin calcium": "Atorvastatin",
    "lipitor": "Atorvastatin",
}


def normalize_diagnosis(raw: str) -> str:
    key = raw.strip().lower()
    return DIAGNOSIS_ALIASES.get(key, raw.strip().title())


def normalize_medication(raw: str) -> str:
    key = raw.strip().lower()
    return MEDICATION_ALIASES.get(key, raw.strip().title())


# ─────────────────────────────────────────────
#  Sub-models
# ─────────────────────────────────────────────

class PatientInfo(BaseModel):
    name: Optional[str] = Field(None, description="Full name of the patient")
    date_of_birth: Optional[str] = Field(None, description="DOB in YYYY-MM-DD or as extracted")
    gender: Optional[str] = Field(None, description="Male / Female / Other")
    patient_id: Optional[str] = Field(None, description="Hospital / clinic patient ID")
    national_id: Optional[str] = Field(None, description="National ID / SSN if present")
    contact: Optional[str] = Field(None, description="Phone or address if present")


class Diagnosis(BaseModel):
    name: str = Field(..., description="Normalised diagnosis label")
    icd_code: Optional[str] = Field(None, description="ICD-10 code if extractable")
    status: Optional[str] = Field(None, description="Active / Resolved / Suspected")
    onset_date: Optional[str] = None

    @field_validator("name", mode="before")
    @classmethod
    def normalise(cls, v: str) -> str:
        return normalize_diagnosis(v)


class Medication(BaseModel):
    name: str = Field(..., description="Normalised generic drug name")
    brand_name: Optional[str] = None
    dosage: Optional[str] = Field(None, description="e.g. 500 mg")
    frequency: Optional[str] = Field(None, description="e.g. twice daily")
    route: Optional[str] = Field(None, description="oral / IV / topical")
    duration: Optional[str] = None

    @field_validator("name", mode="before")
    @classmethod
    def normalise(cls, v: str) -> str:
        return normalize_medication(v)


class LabResult(BaseModel):
    test_name: str
    value: Optional[str] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    flag: Optional[str] = Field(None, description="H / L / Critical / Normal")
    collection_date: Optional[str] = None


class VitalSigns(BaseModel):
    blood_pressure: Optional[str] = Field(None, description="e.g. 120/80 mmHg")
    heart_rate: Optional[str] = Field(None, description="e.g. 72 bpm")
    temperature: Optional[str] = Field(None, description="e.g. 37.2 °C")
    respiratory_rate: Optional[str] = None
    oxygen_saturation: Optional[str] = None
    weight: Optional[str] = None
    height: Optional[str] = None
    bmi: Optional[str] = None


class Procedure(BaseModel):
    name: str
    cpt_code: Optional[str] = None
    date: Optional[str] = None
    performing_physician: Optional[str] = None
    notes: Optional[str] = None


class ProviderInfo(BaseModel):
    name: Optional[str] = None
    specialty: Optional[str] = None
    npi: Optional[str] = None
    facility: Optional[str] = None
    date_of_service: Optional[str] = None


# ─────────────────────────────────────────────
#  Root schema
# ─────────────────────────────────────────────

class MedicalDocument(BaseModel):
    """Root schema for any extracted medical document."""

    document_type: str = Field(
        ...,
        description="clinical_note | lab_report | prescription | discharge_summary | radiology_report | other"
    )
    extraction_confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0,
        description="Model's self-reported confidence (0–1)"
    )

    patient: PatientInfo = Field(default_factory=PatientInfo)
    provider: ProviderInfo = Field(default_factory=ProviderInfo)
    vital_signs: VitalSigns = Field(default_factory=VitalSigns)
    diagnoses: List[Diagnosis] = Field(default_factory=list)
    medications: List[Medication] = Field(default_factory=list)
    lab_results: List[LabResult] = Field(default_factory=list)
    procedures: List[Procedure] = Field(default_factory=list)

    chief_complaint: Optional[str] = None
    history_of_present_illness: Optional[str] = None
    past_medical_history: List[str] = Field(default_factory=list)
    allergies: List[str] = Field(default_factory=list)
    notes: Optional[str] = Field(None, description="Any additional free-text not captured above")
