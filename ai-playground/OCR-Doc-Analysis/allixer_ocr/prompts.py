"""
Prompt templates for the Allixer OCR extraction system.

Design principle: the core extractor is domain-agnostic.
Each domain (medical, financial) registers its own prompt factory
and target schema.  Adding a new domain = adding one entry here.
"""

from __future__ import annotations
import json
from typing import Protocol, Any


# ─────────────────────────────────────────────────────────────────────────────
#  Protocol – every domain prompt factory must follow this interface
# ─────────────────────────────────────────────────────────────────────────────

class PromptFactory(Protocol):
    def system_prompt(self) -> str: ...
    def user_prompt(self) -> str: ...
    def schema_hint(self) -> dict: ...


# ─────────────────────────────────────────────────────────────────────────────
#  Shared instructions injected into every domain prompt
# ─────────────────────────────────────────────────────────────────────────────

SHARED_RULES = """
EXTRACTION RULES (apply to every domain):
1. Return ONLY a valid JSON object – no markdown fences, no prose, no comments.
2. If a field cannot be found, set it to null (never fabricate values).
3. Normalise dates to ISO-8601 (YYYY-MM-DD) wherever possible.
4. Normalise amounts: strip currency symbols, use plain decimal notation (e.g. 1234.56).
5. For entity aliases (e.g. "T2DM" → "Type 2 Diabetes Mellitus"), use the canonical form defined in the schema.
6. Include an "extraction_confidence" field (float 0.0–1.0) reflecting your overall certainty.
7. Preserve all lists as JSON arrays even if only one item is found.
8. Do NOT include any field that is not in the target schema.
""".strip()


# ─────────────────────────────────────────────────────────────────────────────
#  Medical prompt factory
# ─────────────────────────────────────────────────────────────────────────────

class MedicalPromptFactory:
    """Generates prompts tailored for medical documents."""

    _SCHEMA_HINT = {
        "document_type": "clinical_note | lab_report | prescription | discharge_summary | radiology_report | other",
        "extraction_confidence": "float 0-1",
        "patient": {
            "name": "string", "date_of_birth": "YYYY-MM-DD", "gender": "Male|Female|Other",
            "patient_id": "string", "national_id": "string", "contact": "string"
        },
        "provider": {
            "name": "string", "specialty": "string", "npi": "string",
            "facility": "string", "date_of_service": "YYYY-MM-DD"
        },
        "vital_signs": {
            "blood_pressure": "120/80 mmHg", "heart_rate": "bpm",
            "temperature": "°C", "respiratory_rate": "breaths/min",
            "oxygen_saturation": "%", "weight": "kg", "height": "cm", "bmi": "kg/m²"
        },
        "diagnoses": [{"name": "canonical name", "icd_code": "ICD-10", "status": "Active|Resolved|Suspected", "onset_date": "YYYY-MM-DD"}],
        "medications": [{"name": "generic name", "brand_name": "string", "dosage": "500 mg", "frequency": "twice daily", "route": "oral|IV|topical", "duration": "string"}],
        "lab_results": [{"test_name": "string", "value": "string", "unit": "string", "reference_range": "string", "flag": "H|L|Critical|Normal", "collection_date": "YYYY-MM-DD"}],
        "procedures": [{"name": "string", "cpt_code": "string", "date": "YYYY-MM-DD", "performing_physician": "string", "notes": "string"}],
        "chief_complaint": "string",
        "history_of_present_illness": "string",
        "past_medical_history": ["string"],
        "allergies": ["string"],
        "notes": "any remaining free-text"
    }

    def system_prompt(self) -> str:
        return (
            "You are a highly accurate medical document analysis AI for the Allixer platform. "
            "Your sole task is to extract structured information from the provided medical document image "
            "and return it as a JSON object that strictly follows the Allixer medical schema.\n\n"
            + SHARED_RULES
        )

    def user_prompt(self) -> str:
        schema_str = json.dumps(self._SCHEMA_HINT, indent=2)
        return (
            "Analyse the medical document in the image above.\n\n"
            "Extract ALL visible information and return it as a JSON object "
            "matching EXACTLY this schema structure:\n\n"
            f"{schema_str}\n\n"
            "NORMALISATION REQUIREMENTS:\n"
            "• Diagnoses: unify aliases → e.g. 'T2DM', 'Type 2 Diabetes', 'DM2' all become 'Type 2 Diabetes Mellitus'.\n"
            "• Medications: use INN generic names → e.g. 'Tylenol' → 'Acetaminophen', 'Glucophage' → 'Metformin'.\n"
            "• ICD-10 codes: infer from diagnosis if not explicitly written, mark confidence lower.\n"
            "• Vital signs: always include units.\n\n"
            "Return ONLY the JSON object."
        )

    def schema_hint(self) -> dict:
        return self._SCHEMA_HINT


# ─────────────────────────────────────────────────────────────────────────────
#  Financial prompt factory
# ─────────────────────────────────────────────────────────────────────────────

class FinancialPromptFactory:
    """Generates prompts tailored for financial documents."""

    _SCHEMA_HINT = {
        "document_type": "invoice | receipt | bank_statement | tax_form | payroll | contract | other",
        "extraction_confidence": "float 0-1",
        "document_number": "string",
        "document_date": "YYYY-MM-DD",
        "due_date": "YYYY-MM-DD",
        "currency": "ISO-4217 e.g. USD",
        "payment_method": "string",
        "payment_status": "Paid|Unpaid|Partial|Overdue",
        "issuer": {
            "name": "string", "address": "string", "tax_id": "string",
            "registration_number": "string", "contact_email": "string",
            "contact_phone": "string", "bank_account": "string",
            "iban": "string", "swift_bic": "string"
        },
        "recipient": {"name": "string", "address": "string", "tax_id": "string"},
        "subtotal": "decimal string e.g. 1000.00",
        "discount": "decimal string",
        "tax_total": "decimal string",
        "grand_total": "decimal string",
        "line_items": [{"description": "string", "quantity": "string", "unit_price": "decimal", "total": "decimal", "tax_rate": "string", "product_code": "string"}],
        "taxes": [{"tax_type": "VAT|GST|Sales Tax|Withholding", "rate": "string", "taxable_amount": "decimal", "tax_amount": "decimal"}],
        "transactions": [{"date": "YYYY-MM-DD", "description": "string", "debit": "decimal", "credit": "decimal", "balance": "decimal", "reference": "string", "category": "string"}],
        "payroll": {"period_start": "YYYY-MM-DD", "period_end": "YYYY-MM-DD", "gross_salary": "decimal", "net_salary": "decimal", "deductions": [{"label": "string", "amount": "decimal"}], "allowances": [{"label": "string", "amount": "decimal"}]},
        "notes": "string"
    }

    def system_prompt(self) -> str:
        return (
            "You are a highly accurate financial document analysis AI for the Allixer platform. "
            "Your sole task is to extract structured data from the provided financial document image "
            "and return it as a JSON object that strictly follows the Allixer financial schema.\n\n"
            + SHARED_RULES
        )

    def user_prompt(self) -> str:
        schema_str = json.dumps(self._SCHEMA_HINT, indent=2)
        return (
            "Analyse the financial document in the image above.\n\n"
            "Extract ALL visible information and return it as a JSON object "
            "matching EXACTLY this schema structure:\n\n"
            f"{schema_str}\n\n"
            "NORMALISATION REQUIREMENTS:\n"
            "• Currency: convert symbols to ISO-4217 codes → '$' → 'USD', '€' → 'EUR', '£' → 'GBP'.\n"
            "• Amounts: strip currency symbols and thousands separators; use decimal dot notation.\n"
            "• Dates: convert DD/MM/YYYY or MM-DD-YYYY to YYYY-MM-DD.\n"
            "• Document type: map 'bill'→'invoice', 'payslip'→'payroll', 'account statement'→'bank_statement'.\n"
            "• Tax IDs: preserve exact formatting (dashes, spaces).\n\n"
            "Return ONLY the JSON object."
        )

    def schema_hint(self) -> dict:
        return self._SCHEMA_HINT


# ─────────────────────────────────────────────────────────────────────────────
#  Registry  –  add new domains here
# ─────────────────────────────────────────────────────────────────────────────

DOMAIN_REGISTRY: dict[str, PromptFactory] = {
    "medical": MedicalPromptFactory(),
    "financial": FinancialPromptFactory(),
}


def get_prompt_factory(domain: str) -> PromptFactory:
    factory = DOMAIN_REGISTRY.get(domain.lower())
    if factory is None:
        supported = ", ".join(DOMAIN_REGISTRY.keys())
        raise ValueError(f"Unknown domain '{domain}'. Supported: {supported}")
    return factory
