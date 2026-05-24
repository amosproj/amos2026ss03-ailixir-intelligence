"""
Knowledge-graph episode prompts.

This file controls exactly what text Graphiti receives for each document.
Graphiti's internal LLM reads this text to decide which entities and
relationships to extract. Changing build_episode_body() changes the graph.

To tune entity extraction further, add custom Pydantic entity types here and
pass them via the entity_types parameter in builder.py.
"""

from __future__ import annotations


def build_episode_body(doc_id: str, file_name: str, ocr_data: dict) -> str:
    """
    Serialise the OCR output into a rich natural-language block.
    Graphiti extracts entities and relationships from this text.
    """
    lines: list[str] = []

    doc_type = ocr_data.get("document_type", "document")
    lines.append(f"Document ID: {doc_id}.")
    lines.append(f"This is a {doc_type} from file '{file_name}'.")

    meta = ocr_data.get("metadata", {})
    if meta.get("date_detected"):
        lines.append(f"Document date: {meta['date_detected']}.")
    if meta.get("language"):
        lines.append(f"Language: {meta['language']}.")

    extracted = ocr_data.get("extracted_fields", {})
    if extracted:
        lines.append("\nExtracted information:")
        lines.extend(_flatten(extracted))

    tables = ocr_data.get("tables", [])
    if tables:
        lines.append("\nTabular data:")
        for i, table in enumerate(tables, start=1):
            lines.append(f"Table {i}:")
            if isinstance(table, list):
                for row in table:
                    lines.append("  " + _row_str(row))
            elif isinstance(table, dict):
                lines.extend(f"  {k}: {v}" for k, v in table.items())

    raw_blocks = ocr_data.get("raw_text_blocks", [])
    if raw_blocks:
        lines.append("\nRaw text from document:")
        lines.extend(str(b) for b in raw_blocks if b)

    return "\n".join(lines)


def source_description(file_name: str, doc_type: str) -> str:
    """Short description attached to each Graphiti episode."""
    return f"OCR extraction — file: {file_name}, type: {doc_type}"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _flatten(d: dict, prefix: str = "") -> list[str]:
    out: list[str] = []
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.extend(_flatten(v, key))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    out.extend(_flatten(item, f"{key}[{i}]"))
                elif item is not None:
                    out.append(f"  {key}[{i}]: {item}")
        elif v is not None:
            out.append(f"  {key}: {v}")
    return out


def _row_str(row: object) -> str:
    if isinstance(row, dict):
        return " | ".join(f"{k}: {v}" for k, v in row.items())
    if isinstance(row, list):
        return " | ".join(str(x) for x in row)
    return str(row)
