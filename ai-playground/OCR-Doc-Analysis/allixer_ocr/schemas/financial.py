"""
Financial document schema for the Allixer project.
Covers invoices, bank statements, receipts, tax forms, contracts.
"""

from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────
#  Normalisation helpers
# ─────────────────────────────────────────────

CURRENCY_ALIASES: dict[str, str] = {
    "$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY",
    "usd": "USD", "eur": "EUR", "gbp": "GBP", "jpy": "JPY",
    "egp": "EGP", "sar": "SAR", "aed": "AED",
}

DOCUMENT_TYPE_ALIASES: dict[str, str] = {
    "bill": "invoice",
    "receipt": "receipt",
    "bank statement": "bank_statement",
    "account statement": "bank_statement",
    "tax return": "tax_form",
    "w2": "tax_form",
    "1099": "tax_form",
    "payslip": "payroll",
    "pay stub": "payroll",
    "salary slip": "payroll",
    "contract": "contract",
    "agreement": "contract",
}


def normalize_currency(raw: str) -> str:
    return CURRENCY_ALIASES.get(raw.strip().lower(), raw.strip().upper())


def normalize_doc_type(raw: str) -> str:
    return DOCUMENT_TYPE_ALIASES.get(raw.strip().lower(), raw.strip().lower())


def clean_amount(raw: str) -> str:
    """Strip thousands separators and normalize decimal points."""
    return raw.strip().replace(",", "").replace(" ", "")


# ─────────────────────────────────────────────
#  Sub-models
# ─────────────────────────────────────────────

class Party(BaseModel):
    """Represents an issuer or recipient (company or individual)."""
    name: Optional[str] = None
    address: Optional[str] = None
    tax_id: Optional[str] = Field(None, description="VAT / EIN / TIN")
    registration_number: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    bank_account: Optional[str] = None
    iban: Optional[str] = None
    swift_bic: Optional[str] = None


class LineItem(BaseModel):
    description: str
    quantity: Optional[str] = None
    unit_price: Optional[str] = None
    total: Optional[str] = None
    tax_rate: Optional[str] = None
    product_code: Optional[str] = None

    @field_validator("unit_price", "total", mode="before")
    @classmethod
    def clean(cls, v: Optional[str]) -> Optional[str]:
        return clean_amount(v) if v else v


class TaxBreakdown(BaseModel):
    tax_type: str = Field(..., description="VAT / GST / Sales Tax / Withholding")
    rate: Optional[str] = None
    taxable_amount: Optional[str] = None
    tax_amount: Optional[str] = None


class BankTransaction(BaseModel):
    date: Optional[str] = None
    description: str
    debit: Optional[str] = None
    credit: Optional[str] = None
    balance: Optional[str] = None
    reference: Optional[str] = None
    category: Optional[str] = Field(None, description="Auto-categorised: salary / utilities / transfer etc.")


class PayrollEntry(BaseModel):
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    gross_salary: Optional[str] = None
    net_salary: Optional[str] = None
    deductions: List[dict] = Field(default_factory=list, description="List of {label, amount}")
    allowances: List[dict] = Field(default_factory=list, description="List of {label, amount}")


# ─────────────────────────────────────────────
#  Root schema
# ─────────────────────────────────────────────

class FinancialDocument(BaseModel):
    """Root schema for any extracted financial document."""

    document_type: str = Field(
        ...,
        description="invoice | receipt | bank_statement | tax_form | payroll | contract | other"
    )
    extraction_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

    # Document identifiers
    document_number: Optional[str] = Field(None, description="Invoice / statement number")
    document_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: Optional[str] = None
    payment_method: Optional[str] = None
    payment_status: Optional[str] = Field(None, description="Paid / Unpaid / Partial / Overdue")

    # Parties
    issuer: Party = Field(default_factory=Party)
    recipient: Party = Field(default_factory=Party)

    # Financials
    subtotal: Optional[str] = None
    discount: Optional[str] = None
    tax_total: Optional[str] = None
    grand_total: Optional[str] = None

    line_items: List[LineItem] = Field(default_factory=list)
    taxes: List[TaxBreakdown] = Field(default_factory=list)
    transactions: List[BankTransaction] = Field(default_factory=list)
    payroll: Optional[PayrollEntry] = None

    notes: Optional[str] = None

    @field_validator("currency", mode="before")
    @classmethod
    def normalise_currency(cls, v: Optional[str]) -> Optional[str]:
        return normalize_currency(v) if v else v

    @field_validator("document_type", mode="before")
    @classmethod
    def normalise_type(cls, v: str) -> str:
        return normalize_doc_type(v)
