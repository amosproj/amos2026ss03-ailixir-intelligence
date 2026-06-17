"""
Temporal Graphiti runner for Patient-1-Data.

This script processes every PDF in Patient-1-Data through the GCP Document AI
processor configured in CR_PROCESSOR, then stores each PDF as a Graphiti episode
using the OCR-detected document date as reference_time. After ingestion it
queries Neo4j for temporal properties so you can inspect whether facts are
valid, invalidated, or visible in as-of snapshots.

Usage:
    python temporal_patient1_runner.py
    python temporal_patient1_runner.py --order reverse
    python temporal_patient1_runner.py --group-id patient-1-temporal-test

Required env:
    OPENAI_API_KEY
    CR_PROCESSOR
    GCP_PROJECT_ID, if CR_PROCESSOR is only a processor ID
    GOOGLE_APPLICATION_CREDENTIALS, unless using application default credentials
    NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tiktoken
from dotenv import load_dotenv
from neo4j import GraphDatabase

from graphiti_core import Graphiti
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.nodes import EpisodeType


# HERE = Path(__file__).resolve().parent
HERE = Path(__file__).resolve().parent
_PLAYGROUND = HERE.parent
DATA_DIR = _PLAYGROUND / "data" / "Patient-7"
REPORT_DIR = HERE / "graph_outputs"
OCR_DIR = REPORT_DIR / "ocr_cache"

load_dotenv(dotenv_path=HERE / ".env")
load_dotenv(dotenv_path=HERE.parent / ".env")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "your_secure_password")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

CR_PROCESSOR = os.getenv("CR_PROCESSOR", "")
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT", "")
GCP_LOCATION = os.getenv("GCP_LOCATION", os.getenv("DOCUMENTAI_LOCATION", "eu"))

CURRENCY = os.getenv("COST_CURRENCY", "USD")


def env_float(name: str, default: float = 0.0) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


OPENAI_LLM_INPUT_USD_PER_1M = env_float("OPENAI_LLM_INPUT_USD_PER_1M")
OPENAI_LLM_OUTPUT_USD_PER_1M = env_float("OPENAI_LLM_OUTPUT_USD_PER_1M")
OPENAI_EMBEDDING_USD_PER_1M = env_float("OPENAI_EMBEDDING_USD_PER_1M")
GCP_DOCUMENT_AI_USD_PER_1000_PAGES = env_float("GCP_DOCUMENT_AI_USD_PER_1000_PAGES")


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default

GERMAN_MONTHS = {
    "januar": 1,
    "februar": 2,
    "m\u00e4rz": 3,
    "maerz": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "dezember": 12,
}

EXTRACTION_RULES = """
Extract only medically relevant longitudinal facts from the clinical document.

Use a conservative extraction policy:
- Extract a fact only if it describes the patient's medical state, clinical event,
  treatment, result, plan, or a change over time.
- Prefer one precise relationship over several vague relationships.
- Prefer updating/connecting to existing patient facts over creating new concepts.
- If a sentence is administrative, provenance-only, boilerplate, or decorative,
  ignore it completely.
- If a person, organization, department, address, document title, or location is
  not necessary to understand the patient's medical timeline, do not create it.
- Do not create entities for isolated OCR fragments, headings, greetings,
  signatures, contact details, page furniture, or generic document structure.
- Do not create relationships that only say two things appeared in the same
  document.
- Do not infer facts that are not explicitly supported by the OCR text.

Keep the graph small. For each document, extract only the facts a clinician would
want to see on a longitudinal patient timeline.

Prefer fewer high-confidence facts over many weak facts. If a detail is administrative
or only provenance, ignore it.
"""


@dataclass(frozen=True)
class PatientDoc:
    path: Path
    ocr_data: dict[str, Any]
    episode_text: str
    doc_date: datetime
    token_usage: dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process Patient-1 PDFs with GCP OCR, Graphiti, and temporal checks."
    )
    parser.add_argument(
        "--data-dir",
        default=str(DATA_DIR),
        help="Folder containing Patient-1 PDF files.",
    )
    parser.add_argument(
        "--group-id",
        default="",
        help=(
            "Graphiti group_id. Defaults to a fresh patient-1-temporal-<timestamp> "
            "so every run is isolated."
        ),
    )
    parser.add_argument(
        "--patient-name",
        default=os.getenv("PATIENT_NAME", "Patient-1"),
        help="Patient anchor name injected into each episode.",
    )
    parser.add_argument(
        "--patient-dob",
        default=os.getenv("PATIENT_DOB", "18.01.1959"),
        help="Patient DOB injected into each episode.",
    )
    parser.add_argument(
        "--order",
        choices=("chronological", "reverse", "filename"),
        default="chronological",
        help="Episode insertion order. Use reverse to test out-of-order ingestion.",
    )
    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="Ignore cached GCP OCR JSON and call Document AI again.",
    )
    parser.add_argument(
        "--add-episode-retries",
        type=int,
        default=env_int("GRAPHITI_ADD_EPISODE_RETRIES", 5),
        help="Retries per Graphiti add_episode call after transient OpenAI/httpx failures.",
    )
    parser.add_argument(
        "--retry-base-delay",
        type=float,
        default=env_float("GRAPHITI_RETRY_BASE_DELAY_SECONDS", 5.0),
        help="Initial retry delay in seconds for add_episode failures.",
    )
    parser.add_argument(
        "--retry-max-delay",
        type=float,
        default=env_float("GRAPHITI_RETRY_MAX_DELAY_SECONDS", 90.0),
        help="Maximum retry delay in seconds for add_episode failures.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Do not skip episode names that already exist for the selected group_id.",
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="After exhausting retries for one PDF, continue with the remaining PDFs.",
    )
    return parser.parse_args()


def ocr_pdf(path: Path, force_ocr: bool) -> dict[str, Any]:
    cache_path = OCR_DIR / f"{path.stem}_gcp_ocr.json"
    if cache_path.exists() and not force_ocr:
        return json.loads(cache_path.read_text(encoding="utf-8"))

    print(f"  GCP Document AI OCR: {path.name}")
    ocr_data = process_pdf_with_documentai(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(ocr_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return ocr_data


def process_pdf_with_documentai(path: Path) -> dict[str, Any]:
    try:
        from google.api_core.client_options import ClientOptions
        from google.cloud import documentai_v1 as documentai
    except ImportError as exc:
        raise RuntimeError(
            "google-cloud-documentai is not installed. "
            "Install it with: pip install google-cloud-documentai"
        ) from exc

    processor_name = resolve_processor_name(documentai)
    location = processor_name.split("/locations/", 1)[1].split("/", 1)[0]
    client = documentai.DocumentProcessorServiceClient(
        client_options=ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
    )

    request = documentai.ProcessRequest(
        name=processor_name,
        raw_document=documentai.RawDocument(
            content=path.read_bytes(),
            mime_type="application/pdf",
        ),
    )
    result = client.process_document(request=request)
    return document_to_ocr_data(path, result.document, processor_name)


def resolve_processor_name(documentai_module: Any) -> str:
    if not CR_PROCESSOR:
        raise RuntimeError(
            "CR_PROCESSOR is not set. Use a full Document AI processor name, "
            "or set CR_PROCESSOR=<processor_id> with GCP_PROJECT_ID."
        )

    if CR_PROCESSOR.startswith("projects/"):
        return CR_PROCESSOR

    if not GCP_PROJECT_ID:
        raise RuntimeError(
            "GCP_PROJECT_ID is required when CR_PROCESSOR is only a processor ID."
        )

    return documentai_module.DocumentProcessorServiceClient.processor_path(
        GCP_PROJECT_ID,
        GCP_LOCATION,
        CR_PROCESSOR,
    )


def document_to_ocr_data(path: Path, document: Any, processor_name: str) -> dict[str, Any]:
    full_text = document.text or ""
    pages = []
    tables = []
    form_fields = []

    for page_index, page in enumerate(document.pages, start=1):
        page_payload: dict[str, Any] = {
            "page": page_index,
            "text": text_from_layout(full_text, page.layout),
        }

        if page.dimension:
            page_payload["dimension"] = {
                "width": page.dimension.width,
                "height": page.dimension.height,
                "unit": page.dimension.unit,
            }

        page_fields = []
        for field in page.form_fields:
            field_payload = {
                "field_name": text_from_layout(full_text, field.field_name),
                "field_value": text_from_layout(full_text, field.field_value),
            }
            page_fields.append(field_payload)
            form_fields.append({"page": page_index, **field_payload})
        if page_fields:
            page_payload["form_fields"] = page_fields

        page_tables = [table_to_dict(full_text, table) for table in page.tables]
        if page_tables:
            page_payload["tables"] = page_tables
            tables.extend({"page": page_index, **table} for table in page_tables)

        pages.append(page_payload)

    entities = []
    for entity in document.entities:
        entities.append(
            {
                "type": entity.type_,
                "mention_text": entity.mention_text,
                "normalized_value": normalized_value_to_string(entity.normalized_value),
                "confidence": entity.confidence,
            }
        )

    return {
        "document_type": "gcp_document_ai_ocr",
        "confidence_score": None,
        "metadata": {
            "source_pdf": path.name,
            "ocr_engine": "gcp_document_ai",
            "processor": processor_name,
            "page_count": len(pages),
            "date_detected": first_document_date(full_text, entities),
        },
        "extracted_fields": {
            "entities": entities,
            "form_fields": form_fields,
            "pages": pages,
        },
        "tables": tables,
        "raw_text_blocks": [full_text],
    }


def text_from_layout(full_text: str, layout: Any) -> str:
    if not layout or not layout.text_anchor:
        return ""
    parts = []
    for segment in layout.text_anchor.text_segments:
        start = int(segment.start_index or 0)
        end = int(segment.end_index or 0)
        parts.append(full_text[start:end])
    return "".join(parts).strip()


def table_to_dict(full_text: str, table: Any) -> dict[str, Any]:
    return {
        "header_rows": rows_to_values(full_text, table.header_rows),
        "body_rows": rows_to_values(full_text, table.body_rows),
    }


def rows_to_values(full_text: str, rows: Any) -> list[list[str]]:
    values = []
    for row in rows:
        values.append([text_from_layout(full_text, cell.layout) for cell in row.cells])
    return values


def normalized_value_to_string(value: Any) -> str | None:
    if not value:
        return None
    for attr in ("text", "date_value", "datetime_value", "money_value"):
        nested = getattr(value, attr, None)
        if nested:
            return str(nested)
    return None


def first_document_date(text: str, entities: list[dict[str, Any]]) -> str | None:
    for entity in entities:
        if "date" in str(entity.get("type", "")).lower():
            normalized = entity.get("normalized_value")
            if normalized:
                return normalized
            mention = entity.get("mention_text")
            if mention:
                return mention

    detected = detect_doc_date_from_text(text)
    return detected.date().isoformat() if detected else None


def detect_doc_date(ocr_data: dict[str, Any], fallback_path: Path) -> datetime:
    raw_values = [
        ocr_data.get("metadata", {}).get("date_detected"),
        ocr_data.get("extracted_fields", {}).get("date"),
        ocr_data.get("extracted_fields", {}).get("document_date"),
        ocr_data.get("extracted_fields", {}).get("report_date"),
        ocr_data.get("extracted_fields", {}).get("visit_date"),
        json.dumps(ocr_data, ensure_ascii=False),
    ]
    detected = detect_doc_date_from_text("\n".join(str(value) for value in raw_values if value))
    if detected:
        return detected

    raise ValueError(
        f"Could not detect a document date for {fallback_path.name}. "
        "Refusing to use extraction time as Graphiti reference_time."
    )


def detect_doc_date_from_text(text: str) -> datetime | None:
    candidates: list[datetime] = []

    for year, month, day in re.findall(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text):
        dt = _date_candidate(int(year), int(month), int(day))
        if dt:
            candidates.append(dt)

    for day, month, year in re.findall(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b", text):
        dt = _date_candidate(int(year), int(month), int(day))
        if dt:
            candidates.append(dt)

    month_names = "|".join(re.escape(name) for name in GERMAN_MONTHS)
    pattern = rf"\b(\d{{1,2}})\.\s*({month_names})\s+(\d{{4}})\b"
    for day, month_name, year in re.findall(pattern, text, flags=re.IGNORECASE):
        month = GERMAN_MONTHS[month_name.lower()]
        dt = _date_candidate(int(year), month, int(day))
        if dt:
            candidates.append(dt)

    clinical_dates = [dt for dt in candidates if dt.year >= 2020]
    return min(clinical_dates) if clinical_dates else None


def _date_candidate(year: int, month: int, day: int) -> datetime | None:
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def load_patient_docs(data_dir: Path, order: str, force_ocr: bool) -> list[PatientDoc]:
    docs = []
    for path in sorted(data_dir.glob("*.pdf")):
        print(f"OCR source PDF: {path.name}")
        ocr_data = ocr_pdf(path, force_ocr=force_ocr)
        episode_text = ocr_data_to_episode_text(path, ocr_data)
        docs.append(
            PatientDoc(
                path=path,
                ocr_data=ocr_data,
                episode_text=episode_text,
                doc_date=detect_doc_date(ocr_data, path),
                token_usage=build_token_usage(path, ocr_data, episode_text),
            )
        )

    if order == "chronological":
        return sorted(docs, key=lambda doc: (doc.doc_date, doc.path.name))
    if order == "reverse":
        return sorted(docs, key=lambda doc: (doc.doc_date, doc.path.name), reverse=True)
    return sorted(docs, key=lambda doc: doc.path.name)


def ocr_data_to_episode_text(path: Path, ocr_data: dict[str, Any]) -> str:
    lines = [
        f"This is a GCP Document AI OCR extraction from PDF '{path.name}'.",
        f"Document type: {ocr_data.get('document_type', 'document')}.",
    ]
    meta = ocr_data.get("metadata", {})
    if meta.get("date_detected"):
        lines.append(f"OCR detected document date: {meta['date_detected']}.")
    if meta.get("ocr_engine"):
        lines.append(f"OCR engine: {meta['ocr_engine']}.")
    if meta.get("processor"):
        lines.append(f"OCR processor: {meta['processor']}.")

    raw_blocks = [str(block) for block in ocr_data.get("raw_text_blocks", []) if block]
    if raw_blocks:
        lines.append("\nOCR text:")
        lines.extend(raw_blocks)

    return "\n".join(lines)


def estimate_tokens(text: str, model: str | None = None) -> int:
    if not text:
        return 0
    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        # Offline-safe fallback. Medical OCR text is usually close enough at ~4 chars/token.
        return max(1, (len(text) + 3) // 4)


def build_token_usage(path: Path, ocr_data: dict[str, Any], episode_text: str) -> dict[str, Any]:
    raw_ocr_text = "\n".join(str(block) for block in ocr_data.get("raw_text_blocks", []) if block)
    ocr_json = json.dumps(ocr_data, ensure_ascii=False, default=str)
    return {
        "estimation_method": "tiktoken",
        "model_for_estimate": "cl100k_base_or_4_chars_per_token_fallback",
        "layers": {
            "gcp_document_ai_output_text": estimate_tokens(raw_ocr_text),
            "gcp_document_ai_output_json": estimate_tokens(ocr_json),
            "graphiti_episode_text": estimate_tokens(episode_text),
            "graphiti_embedding_input_estimate": estimate_tokens(episode_text),
            "graphiti_custom_instructions": estimate_tokens(EXTRACTION_RULES),
            "source_file_name": estimate_tokens(path.name),
        },
        "characters": {
            "gcp_document_ai_output_text": len(raw_ocr_text),
            "gcp_document_ai_output_json": len(ocr_json),
            "graphiti_episode_text": len(episode_text),
        },
    }


def serialize_token_tracker(graphiti: Graphiti) -> dict[str, Any]:
    usage_by_prompt = {}
    for prompt_name, usage in graphiti.token_tracker.get_usage().items():
        usage_by_prompt[prompt_name] = {
            "call_count": usage.call_count,
            "input_tokens": usage.total_input_tokens,
            "output_tokens": usage.total_output_tokens,
            "total_tokens": usage.total_tokens,
            "avg_input_tokens": usage.avg_input_tokens,
            "avg_output_tokens": usage.avg_output_tokens,
        }

    total = graphiti.token_tracker.get_total_usage()
    return {
        "source": "graphiti.token_tracker",
        "by_prompt": usage_by_prompt,
        "total": {
            "input_tokens": total.input_tokens,
            "output_tokens": total.output_tokens,
            "total_tokens": total.total_tokens,
        },
    }


def summarize_estimated_token_usage(docs: list[PatientDoc]) -> dict[str, Any]:
    totals: dict[str, int] = {}
    char_totals: dict[str, int] = {}
    for doc in docs:
        for layer, count in doc.token_usage.get("layers", {}).items():
            totals[layer] = totals.get(layer, 0) + int(count)
        for layer, count in doc.token_usage.get("characters", {}).items():
            char_totals[layer] = char_totals.get(layer, 0) + int(count)

    totals["all_estimated_layers"] = sum(totals.values())
    return {
        "estimation_method": "tiktoken",
        "model_for_estimate": "cl100k_base_or_4_chars_per_token_fallback",
        "estimated_tokens_by_layer": totals,
        "characters_by_layer": char_totals,
    }


def document_page_count(doc: PatientDoc) -> int:
    page_count = doc.ocr_data.get("metadata", {}).get("page_count")
    if isinstance(page_count, int):
        return page_count
    pages = doc.ocr_data.get("extracted_fields", {}).get("pages", [])
    return len(pages) if isinstance(pages, list) else 0


def usd_per_million(tokens: int, price_per_1m: float) -> float:
    return (tokens / 1_000_000) * price_per_1m


def usd_per_thousand_pages(pages: int, price_per_1000_pages: float) -> float:
    return (pages / 1_000) * price_per_1000_pages


def calculate_cost_estimate(
    docs: list[PatientDoc], graphiti_token_usage: dict[str, Any]
) -> dict[str, Any]:
    estimated_usage = summarize_estimated_token_usage(docs)
    tokens_by_layer = estimated_usage["estimated_tokens_by_layer"]
    graphiti_total = graphiti_token_usage.get("total", {})

    graphiti_input_tokens = int(graphiti_total.get("input_tokens", 0) or 0)
    graphiti_output_tokens = int(graphiti_total.get("output_tokens", 0) or 0)
    embedding_tokens = int(tokens_by_layer.get("graphiti_embedding_input_estimate", 0) or 0)
    document_ai_pages = sum(document_page_count(doc) for doc in docs)

    llm_input_cost = usd_per_million(graphiti_input_tokens, OPENAI_LLM_INPUT_USD_PER_1M)
    llm_output_cost = usd_per_million(graphiti_output_tokens, OPENAI_LLM_OUTPUT_USD_PER_1M)
    embedding_cost = usd_per_million(embedding_tokens, OPENAI_EMBEDDING_USD_PER_1M)
    document_ai_cost = usd_per_thousand_pages(
        document_ai_pages, GCP_DOCUMENT_AI_USD_PER_1000_PAGES
    )

    per_document = []
    for doc in docs:
        layers = doc.token_usage.get("layers", {})
        doc_pages = document_page_count(doc)
        doc_embedding_tokens = int(layers.get("graphiti_embedding_input_estimate", 0) or 0)
        doc_episode_tokens = int(layers.get("graphiti_episode_text", 0) or 0)
        per_document.append(
            {
                "file": doc.path.name,
                "pages": doc_pages,
                "estimated_episode_tokens": doc_episode_tokens,
                "estimated_embedding_tokens": doc_embedding_tokens,
                "estimated_document_ai_cost": usd_per_thousand_pages(
                    doc_pages, GCP_DOCUMENT_AI_USD_PER_1000_PAGES
                ),
                "estimated_embedding_cost": usd_per_million(
                    doc_embedding_tokens, OPENAI_EMBEDDING_USD_PER_1M
                ),
            }
        )

    total_cost = llm_input_cost + llm_output_cost + embedding_cost + document_ai_cost
    rates_configured = any(
        rate > 0
        for rate in (
            OPENAI_LLM_INPUT_USD_PER_1M,
            OPENAI_LLM_OUTPUT_USD_PER_1M,
            OPENAI_EMBEDDING_USD_PER_1M,
            GCP_DOCUMENT_AI_USD_PER_1000_PAGES,
        )
    )

    return {
        "currency": CURRENCY,
        "rates_configured": rates_configured,
        "configured_rates": {
            "OPENAI_LLM_INPUT_USD_PER_1M": OPENAI_LLM_INPUT_USD_PER_1M,
            "OPENAI_LLM_OUTPUT_USD_PER_1M": OPENAI_LLM_OUTPUT_USD_PER_1M,
            "OPENAI_EMBEDDING_USD_PER_1M": OPENAI_EMBEDDING_USD_PER_1M,
            "GCP_DOCUMENT_AI_USD_PER_1000_PAGES": GCP_DOCUMENT_AI_USD_PER_1000_PAGES,
        },
        "layers": {
            "gcp_document_ai": {
                "pages": document_ai_pages,
                "estimated_cost": document_ai_cost,
            },
            "graphiti_llm": {
                "input_tokens": graphiti_input_tokens,
                "output_tokens": graphiti_output_tokens,
                "input_cost": llm_input_cost,
                "output_cost": llm_output_cost,
                "estimated_cost": llm_input_cost + llm_output_cost,
            },
            "graphiti_embeddings": {
                "estimated_input_tokens": embedding_tokens,
                "estimated_cost": embedding_cost,
            },
        },
        "per_document_estimates": per_document,
        "total_estimated_cost": total_cost,
        "notes": [
            "Prices default to 0. Set the *_USD_PER_* env vars to calculate non-zero costs.",
            "Graphiti LLM cost uses actual tracked input/output tokens.",
            "Embedding and Document AI costs are estimates from episode tokens and OCR page counts.",
        ],
    }


def _flatten_to_sentences(value: Any, prefix: str = "") -> list[str]:
    out = []
    if isinstance(value, dict):
        for key, child in value.items():
            label = f"{prefix}.{key}" if prefix else str(key)
            out.extend(_flatten_to_sentences(child, label))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            label = f"{prefix}[{index}]"
            out.extend(_flatten_to_sentences(child, label))
    elif value is not None:
        out.append(f"  {prefix}: {value}")
    return out


def build_episode_body(doc: PatientDoc, patient_name: str, patient_dob: str, group_id: str) -> str:
    return "\n".join(
        [
            f"Patient: {patient_name}.",
            f"Patient identifier / group_id: {group_id}.",
            f"Date of birth: {patient_dob}.",
            f"Document file: {doc.path.name}.",
            f"Document date: {doc.doc_date.date().isoformat()}.",
            "",
            doc.episode_text,
        ]
    )


def existing_episode_names(group_id: str) -> set[str]:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            rows = session.run(
                """
                MATCH (ep:Episodic {group_id: $group_id})
                WHERE ep.name IS NOT NULL
                RETURN ep.name AS name
                """,
                group_id=group_id,
            )
            return {str(row["name"]) for row in rows if row.get("name")}
    finally:
        driver.close()


def is_retryable_add_episode_error(exc: BaseException) -> bool:
    retryable_names = (
        "APITimeoutError",
        "APIConnectionError",
        "APIStatusError",
        "ConnectTimeout",
        "ConnectError",
        "ReadTimeout",
        "RemoteProtocolError",
        "RateLimitError",
        "TimeoutException",
    )
    for current in _exception_chain(exc):
        name = current.__class__.__name__
        if name in retryable_names or "timeout" in name.lower():
            return True
    return False


def _exception_chain(exc: BaseException) -> list[BaseException]:
    chain = []
    current: BaseException | None = exc
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


async def add_episode_with_retry(
    graphiti: Graphiti,
    *,
    episode_name: str,
    episode_body: str,
    source_description: str,
    group_id: str,
    reference_time: datetime,
    max_retries: int,
    base_delay: float,
    max_delay: float,
) -> None:
    attempt = 0
    while True:
        attempt += 1
        try:
            await graphiti.add_episode(
                name=episode_name,
                episode_body=episode_body,
                source=EpisodeType.text,
                source_description=source_description,
                group_id=group_id,
                reference_time=reference_time,
                custom_extraction_instructions=EXTRACTION_RULES,
            )
            return
        except Exception as exc:
            if attempt > max_retries + 1 or not is_retryable_add_episode_error(exc):
                raise

            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            jitter = random.uniform(0, min(2.0, delay * 0.2))
            sleep_seconds = delay + jitter
            print(
                "    transient add_episode failure "
                f"({exc.__class__.__name__}: {exc}); "
                f"retry {attempt}/{max_retries} in {sleep_seconds:.1f}s"
            )
            await asyncio.sleep(sleep_seconds)


async def ingest_docs(
    docs: list[PatientDoc],
    group_id: str,
    patient_name: str,
    patient_dob: str,
    *,
    add_episode_retries: int,
    retry_base_delay: float,
    retry_max_delay: float,
    resume: bool,
    continue_on_failure: bool,
) -> dict[str, Any]:
    llm_client = OpenAIClient(config=LLMConfig(api_key=OPENAI_API_KEY))
    embedder = OpenAIEmbedder(config=OpenAIEmbedderConfig(api_key=OPENAI_API_KEY))
    graphiti = Graphiti(
        NEO4J_URI,
        NEO4J_USER,
        NEO4J_PASSWORD,
        llm_client=llm_client,
        embedder=embedder,
    )

    graphiti_token_usage: dict[str, Any] = {}
    skipped_existing: list[str] = []
    succeeded: list[str] = []
    failed: list[dict[str, str]] = []
    existing_names = existing_episode_names(group_id) if resume else set()
    if existing_names:
        print(
            f"Resume enabled: found {len(existing_names)} existing episodes "
            f"for group_id={group_id}"
        )

    try:
        await graphiti.build_indices_and_constraints()
        for index, doc in enumerate(docs, start=1):
            episode_name = f"{group_id}_{doc.path.stem}_{doc.doc_date:%Y%m%d}"
            if episode_name in existing_names:
                print(f"[{index}/{len(docs)}] skip existing episode {episode_name}")
                skipped_existing.append(episode_name)
                continue

            print(f"[{index}/{len(docs)}] add_episode {episode_name}")
            try:
                await add_episode_with_retry(
                    graphiti,
                    episode_name=episode_name,
                    episode_body=build_episode_body(
                        doc,
                        patient_name,
                        patient_dob,
                        group_id,
                    ),
                    source_description=f"Patient-1 GCP OCR temporal PDF: {doc.path.name}",
                    group_id=group_id,
                    reference_time=doc.doc_date,
                    max_retries=add_episode_retries,
                    base_delay=retry_base_delay,
                    max_delay=retry_max_delay,
                )
                succeeded.append(episode_name)
            except Exception as exc:
                failed.append(
                    {
                        "episode_name": episode_name,
                        "file": doc.path.name,
                        "error_type": exc.__class__.__name__,
                        "error": str(exc),
                    }
                )
                print(
                    f"    add_episode failed after retries for {episode_name}: "
                    f"{exc.__class__.__name__}: {exc}"
                )
                if not continue_on_failure:
                    raise

        graphiti_token_usage = serialize_token_tracker(graphiti)
        graphiti_token_usage["ingestion"] = {
            "resume": resume,
            "add_episode_retries": add_episode_retries,
            "retry_base_delay_seconds": retry_base_delay,
            "retry_max_delay_seconds": retry_max_delay,
            "skipped_existing_count": len(skipped_existing),
            "succeeded_count": len(succeeded),
            "failed_count": len(failed),
            "skipped_existing": skipped_existing,
            "succeeded": succeeded,
            "failed": failed,
        }
    finally:
        await graphiti.close()
    return graphiti_token_usage


def run_temporal_queries(
    group_id: str, docs: list[PatientDoc], graphiti_token_usage: dict[str, Any]
) -> dict[str, Any]:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        with driver.session() as session:
            edge_rows = session.run(
                """
                MATCH (a)-[r]->(b)
                WHERE r.group_id = $group_id
                  AND NOT a:Episodic
                  AND NOT b:Episodic
                RETURN
                  coalesce(a.name, a.uuid, elementId(a)) AS source,
                  type(r) AS type,
                  coalesce(b.name, b.uuid, elementId(b)) AS target,
                  r.name AS name,
                  r.fact AS fact,
                  r.valid_at AS valid_at,
                  r.invalid_at AS invalid_at,
                  r.expired_at AS system_expired_at,
                  r.reference_time AS reference_time,
                  r.episodes AS episodes
                ORDER BY r.valid_at, source, target
                """,
                group_id=group_id,
            )
            edges = [_clean_record(dict(row)) for row in edge_rows]

            episode_rows = session.run(
                """
                MATCH (ep:Episodic {group_id: $group_id})
                RETURN ep.name AS name, ep.created_at AS created_at,
                       ep.valid_at AS valid_at, ep.source AS source
                ORDER BY ep.valid_at, ep.name
                """,
                group_id=group_id,
            )
            episodes = [_clean_record(dict(row)) for row in episode_rows]

            snapshots = []
            for doc in docs:
                as_of = doc.doc_date.isoformat()
                snapshot_rows = session.run(
                    """
                    MATCH (a)-[r]->(b)
                    WHERE r.group_id = $group_id
                      AND NOT a:Episodic
                      AND NOT b:Episodic
                      AND r.valid_at IS NOT NULL
                      AND datetime(toString(r.valid_at)) <= datetime($as_of)
                      AND (
                        r.invalid_at IS NULL OR datetime(toString(r.invalid_at)) > datetime($as_of)
                      )
                    RETURN coalesce(a.name, a.uuid, elementId(a)) AS source,
                           type(r) AS type,
                           coalesce(b.name, b.uuid, elementId(b)) AS target,
                           r.fact AS fact,
                           r.valid_at AS valid_at,
                           r.invalid_at AS invalid_at
                    ORDER BY source, target
                    LIMIT 50
                    """,
                    group_id=group_id,
                    as_of=as_of,
                )
                snapshot_edges = [_clean_record(dict(row)) for row in snapshot_rows]
                snapshots.append(
                    {
                        "as_of": doc.doc_date.date().isoformat(),
                        "source_document": doc.path.name,
                        "active_edge_count_sampled": len(snapshot_edges),
                        "active_edges_sample": snapshot_edges,
                    }
                )
    finally:
        driver.close()

    invalidated = [
        edge
        for edge in edges
        if edge.get("invalid_at") is not None
    ]
    temporal_edges = [
        edge
        for edge in edges
        if edge.get("valid_at") is not None
        or edge.get("invalid_at") is not None
        or edge.get("reference_time") is not None
    ]

    return {
        "group_id": group_id,
        "documents": [
            {
                "file": doc.path.name,
                "detected_date": doc.doc_date.isoformat(),
                "ocr_chars": len(doc.episode_text),
                "ocr_document_type": doc.ocr_data.get("document_type"),
                "ocr_cache_source": str(OCR_DIR / f"{doc.path.stem}_gcp_ocr.json"),
                "token_usage_estimate": doc.token_usage,
            }
            for doc in docs
        ],
        "summary": {
            "episode_count": len(episodes),
            "edge_count": len(edges),
            "temporal_edge_count": len(temporal_edges),
            "invalidated_edge_count": len(invalidated),
        },
        "token_usage": {
            "estimated_by_layer": summarize_estimated_token_usage(docs),
            "actual_graphiti_llm": graphiti_token_usage,
            "notes": [
                "GCP Document AI OCR does not report LLM-style tokens here; OCR layer tokens are estimated from returned text/JSON.",
                "Graphiti actual usage comes from graphiti.token_tracker and is grouped by internal prompt name.",
                "Embedding token usage is estimated from episode text because OpenAI embedding responses are not exposed by Graphiti's embedder wrapper.",
            ],
        },
        "cost_estimate": calculate_cost_estimate(docs, graphiti_token_usage),
        "episodes": episodes,
        "temporal_edges": temporal_edges,
        "invalidated_edges": invalidated,
        "as_of_snapshots": snapshots,
    }


def _clean_record(record: dict[str, Any]) -> dict[str, Any]:
    clean = {}
    for key, value in record.items():
        if isinstance(value, datetime):
            clean[key] = value.isoformat()
        elif isinstance(value, list):
            clean[key] = [str(item) for item in value]
        elif value is None or isinstance(value, (str, int, float, bool)):
            clean[key] = value
        else:
            clean[key] = str(value)
    return clean


async def main() -> None:
    args = parse_args()
    if not OPENAI_API_KEY:
        raise SystemExit("OPENAI_API_KEY is not set.")
    if not CR_PROCESSOR:
        raise SystemExit("CR_PROCESSOR is not set.")

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        raise SystemExit(f"Data directory not found: {data_dir}")

    group_id = args.group_id.strip() or f"patient-1-temporal-{datetime.now(timezone.utc):%Y%m%d_%H%M%S}"
    docs = load_patient_docs(data_dir, args.order, force_ocr=args.force_ocr)
    if not docs:
        raise SystemExit(f"No PDFs found in {data_dir}")

    print("Temporal Graphiti run")
    print(f"  data_dir : {data_dir}")
    print(f"  group_id : {group_id}")
    print(f"  order    : {args.order}")
    print(f"  docs     : {len(docs)}")
    print(f"  resume   : {not args.no_resume}")
    print(f"  retries  : {max(0, args.add_episode_retries)}")
    for doc in docs:
        print(f"    {doc.doc_date.date().isoformat()}  {doc.path.name}")

    graphiti_token_usage = await ingest_docs(
        docs,
        group_id,
        args.patient_name,
        args.patient_dob,
        add_episode_retries=max(0, args.add_episode_retries),
        retry_base_delay=max(0.1, args.retry_base_delay),
        retry_max_delay=max(0.1, args.retry_max_delay),
        resume=not args.no_resume,
        continue_on_failure=args.continue_on_failure,
    )

    report = run_temporal_queries(group_id, docs, graphiti_token_usage)
    REPORT_DIR.mkdir(exist_ok=True)
    report_path = REPORT_DIR / f"{group_id}_temporal_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    print("\nTemporal report")
    print(f"  output       : {report_path}")
    print(f"  episodes     : {report['summary']['episode_count']}")
    print(f"  edges        : {report['summary']['edge_count']}")
    print(f"  temporal     : {report['summary']['temporal_edge_count']}")
    print(f"  invalidated  : {report['summary']['invalidated_edge_count']}")
    estimated_tokens = report["token_usage"]["estimated_by_layer"]["estimated_tokens_by_layer"]
    actual_graphiti = report["token_usage"]["actual_graphiti_llm"]["total"]
    print("\nToken usage")
    print(f"  estimated OCR text     : {estimated_tokens.get('gcp_document_ai_output_text', 0)}")
    print(f"  estimated episode text : {estimated_tokens.get('graphiti_episode_text', 0)}")
    print(f"  estimated instructions : {estimated_tokens.get('graphiti_custom_instructions', 0)}")
    print(f"  actual Graphiti LLM    : {actual_graphiti.get('total_tokens', 0)}")
    ingestion = report["token_usage"]["actual_graphiti_llm"].get("ingestion", {})
    if ingestion:
        print("\nIngestion")
        print(f"  skipped existing       : {ingestion.get('skipped_existing_count', 0)}")
        print(f"  succeeded this run     : {ingestion.get('succeeded_count', 0)}")
        print(f"  failed this run        : {ingestion.get('failed_count', 0)}")
    cost = report["cost_estimate"]
    print("\nCost estimate")
    print(f"  rates configured       : {cost['rates_configured']}")
    print(f"  Document AI pages      : {cost['layers']['gcp_document_ai']['pages']}")
    print(f"  Graphiti LLM cost      : {cost['layers']['graphiti_llm']['estimated_cost']:.6f} {cost['currency']}")
    print(f"  Embedding cost         : {cost['layers']['graphiti_embeddings']['estimated_cost']:.6f} {cost['currency']}")
    print(f"  Document AI cost       : {cost['layers']['gcp_document_ai']['estimated_cost']:.6f} {cost['currency']}")
    print(f"  total estimated cost   : {cost['total_estimated_cost']:.6f} {cost['currency']}")
    print("\nTry reverse insertion next if you want the out-of-order test:")
    print("  python temporal_patient1_runner.py --order reverse")


if __name__ == "__main__":
    asyncio.run(main())
