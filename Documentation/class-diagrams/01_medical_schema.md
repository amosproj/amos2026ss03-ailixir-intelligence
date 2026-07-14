# Class Diagram — Medical Entity/Edge Schema

Source: `Backend/workers/pipeline/graph/medical_schema.py`. Prose reference:
[`code-components/05_workers_pipeline.md`](../code-components/05_workers_pipeline.md#pipelinegraphmedical_schemapy).

This is the fixed Pydantic schema passed to `graphiti.add_episode()` on
every ingestion call — it's what lets Graphiti merge the same `Patient`/
`Diagnosis`/`Medication` across multiple documents into one node instead of
creating a duplicate per upload, and enforce which relationship types are
legal between which entity pairs (`MEDICAL_EDGE_TYPE_MAP`).

All 15 entity classes and 20 edge classes extend `pydantic.BaseModel`
directly — no inheritance between them — so that single fact is noted once
here rather than drawn as 35 identical arrows below. Edge classes have empty
bodies; the class *name* is itself the semantic relationship label Graphiti
writes onto the graph edge. The associations below are exactly
`MEDICAL_EDGE_TYPE_MAP`, i.e. this is also an accurate map of what the
resulting Neo4j graph looks like.

```mermaid
classDiagram
    class Patient {
        +str patient_id
        +str date_of_birth
        +str gender
    }
    class Diagnosis {
        +str icd_code
        +str stage
        +str date_confirmed
        +str status
    }
    class Medication {
        +str dosage
        +str route
        +str frequency
        +str start_date
        +str end_date
    }
    class LabTest {
        +str test_value
        +str unit
        +str reference_range
        +str test_date
        +str result_status
    }
    class Procedure {
        +str procedure_date
        +str outcome
        +str indication
    }
    class Provider {
        +str specialty
        +str institution
        +str department
    }
    class PathologyResult {
        +str grade
        +str finding
        +str specimen_site
        +str pathology_date
    }
    class TumorMarker {
        +str marker_value
        +str unit
        +str reference_range
        +str test_date
    }
    class TreatmentPlan {
        +str therapy_type
        +str planned_start
        +str recommendation
        +str decision_date
    }
    class ImagingResult {
        +str modality
        +str body_region
        +str finding
        +str impression
        +str imaging_date
    }
    class Symptom {
        +str severity
        +str onset_date
        +str duration
        +str status
    }
    class Allergy {
        +str allergen
        +str reaction_type
        +str severity
        +str documented_date
    }
    class VitalSigns {
        +str measurement_date
        +str blood_pressure
        +str heart_rate
        +str weight
        +str height
        +str temperature
        +str oxygen_saturation
    }
    class Referral {
        +str referral_date
        +str reason
        +str urgency
        +str referring_provider
        +str target_specialty
    }
    class Appointment {
        +str appointment_date
        +str appointment_type
        +str purpose
        +str location
    }

    Patient --> Diagnosis : HAS_DIAGNOSIS
    Patient --> Procedure : UNDERWENT
    Patient --> Medication : PRESCRIBED
    Patient --> LabTest : HAD_LAB_TEST
    Patient --> TumorMarker : HAS_TUMOR_MARKER
    Patient --> PathologyResult : HAS_PATHOLOGY
    Patient --> ImagingResult : HAS_IMAGING
    Patient --> Symptom : HAS_SYMPTOM
    Patient --> Allergy : HAS_ALLERGY
    Patient --> VitalSigns : HAS_VITAL_SIGNS
    Patient --> Referral : WAS_REFERRED
    Patient --> Appointment : HAS_APPOINTMENT
    Patient --> Provider : MANAGED_AT
    Patient --> TreatmentPlan : HAS_TREATMENT_PLAN

    Diagnosis --> Medication : TREATED_BY
    Diagnosis --> LabTest : CONFIRMED_BY
    Diagnosis --> PathologyResult : CONFIRMED_BY
    Diagnosis --> ImagingResult : CONFIRMED_BY
    Diagnosis --> TreatmentPlan : HAS_TREATMENT_PLAN

    LabTest --> Diagnosis : INDICATES
    TumorMarker --> Diagnosis : INDICATES
    PathologyResult --> Diagnosis : CONFIRMED_BY
    ImagingResult --> Diagnosis : INDICATES
    Symptom --> Diagnosis : SYMPTOM_OF

    Procedure --> Provider : PERFORMED_BY
    ImagingResult --> Provider : PERFORMED_BY
    Referral --> Provider : REFERRED_TO
    Appointment --> Provider : RELATES_TO
```
