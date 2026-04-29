
MEDICAL_SCHEMA = {

    # =========================
    # ENTITIES
    # =========================
    "entities": {

        # -------------------------
        # PERSON (split conceptually)
        # -------------------------
        "person": {
            "id": "",
            "type": "patient | doctor",
            "name": "",
            "gender": "",
            "date_of_birth": ""
        },

        # -------------------------
        # CLINICAL EVENT (CORE HUB NODE)
        # -------------------------
        "clinical_event": {
            "id": "",
            "type": "visit | lab | radiology | admission | prescription",
            "datetime": "",
            "status": "",
            "notes": ""
        },

        # -------------------------
        # CONDITION
        # -------------------------
        "condition": {
            "id": "",
            "name": "",
            "code": "",
            "status": "active | chronic | resolved"
        },

        # -------------------------
        # MEDICATION (normalized drug entity)
        # -------------------------
        "medication": {
            "id": "",
            "name": "",
            "code": "",
            "form": "",
            "dosage": "",
            "frequency": "",
            "route": ""
        },

        # -------------------------
        # OBSERVATION (LAB / VITALS / IMAGING METRICS)
        # -------------------------
        "observation": {
            "id": "",
            "name": "",
            "type": "lab | vital | imaging_metric",
            "value": "",
            "unit": "",
            "reference_range": {
                "low": "",
                "high": ""
            },
            "flag": "low | normal | high",
            "datetime": ""
        },

        # -------------------------
        # DOCUMENT (PROVENANCE LAYER)
        # -------------------------
        "document": {
            "id": "",
            "type": "prescription | lab_report | radiology | discharge",
            "source": "",
            "date": ""
        }
    },

    # =========================
    # RELATIONS (GRAPH EDGES)
    # =========================
    "relations": [

        # -------------------------
        # CORE PATIENT FLOW
        # -------------------------
        {"type": "HAS_EVENT", "from": "person", "to": "clinical_event"},

        # -------------------------
        # EVENT CONTEXT
        # -------------------------
        {"type": "ATTENDED_BY", "from": "clinical_event", "to": "person"},
        {"type": "HAS_CONDITION", "from": "clinical_event", "to": "condition"},
        {"type": "HAS_OBSERVATION", "from": "clinical_event", "to": "observation"},
        {"type": "PRESCRIBES", "from": "clinical_event", "to": "medication"},

        # -------------------------
        # MEDICATION RELATION
        # -------------------------
        {"type": "TREATS", "from": "medication", "to": "condition"},

        # -------------------------
        # PROVENANCE LAYER (CRITICAL FOR OCR SYSTEMS)
        # -------------------------
        {"type": "SOURCE_OF", "from": "document", "to": "clinical_event"},
        {"type": "EXTRACTS", "from": "document", "to": "observation"}
    ],

    # =========================
    # METADATA
    # =========================
    "metadata": {
        "confidence": "",
        "created_at": "",
        "source_bbox": "",
        "ocr_engine": "",
        "llm_model": ""
    }
}