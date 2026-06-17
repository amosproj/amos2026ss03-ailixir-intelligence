from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from kg_chat.models import QueryPlan
from kg_chat.schema_cache import GraphSchema


class QueryValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ValidatedQuery:
    generated_cypher: str
    cypher: str
    parameters: dict[str, Any]


DISALLOWED_PATTERNS = [
    r"\bCREATE\b",
    r"\bMERGE\b",
    r"\bDELETE\b",
    r"\bDETACH\b",
    r"\bSET\b",
    r"\bREMOVE\b",
    r"\bDROP\b",
    r"\bLOAD\s+CSV\b",
    r"\bCALL\b",
    r"\bAPOC\b",
    r"\bGDS\b",
    r"\bDBMS\b",
    r"\bGRANT\b",
    r"\bDENY\b",
    r"\bREVOKE\b",
    r"\bUSE\b",
]


def validate_query_plan(
    *,
    plan: QueryPlan,
    schema: GraphSchema,
    default_limit: int,
) -> ValidatedQuery:
    cypher = plan.cypher.strip()
    if not cypher:
        raise QueryValidationError("Generated Cypher was empty.")

    if cypher.endswith(";"):
        cypher = cypher[:-1].strip()
    if ";" in cypher:
        raise QueryValidationError("Generated Cypher contains multiple statements.")

    scrubbed = _scrub_strings_and_comments(cypher).upper()
    for pattern in DISALLOWED_PATTERNS:
        if re.search(pattern, scrubbed, flags=re.IGNORECASE):
            raise QueryValidationError(
                f"Generated Cypher uses a disallowed operation: {pattern}"
            )

    if not re.search(r"\bRETURN\b", scrubbed):
        raise QueryValidationError("Generated Cypher must return data.")
    if not re.search(r"\bMATCH\b", scrubbed):
        raise QueryValidationError("Generated Cypher must include MATCH.")

    _validate_parameters(plan.parameters)
    _validate_schema_identifiers(cypher, schema)

    if not re.search(r"\bLIMIT\s+(?:\d+|\$[A-Z_][A-Z0-9_]*)\b", scrubbed):
        cypher = f"{cypher}\nLIMIT {default_limit}"

    return ValidatedQuery(
        generated_cypher=plan.cypher,
        cypher=cypher,
        parameters=plan.parameters,
    )


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("No JSON object start found.")

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(cleaned)):
        char = cleaned[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = cleaned[start : index + 1]
                parsed = json.loads(candidate)
                if not isinstance(parsed, dict):
                    raise ValueError("Top-level JSON value is not an object.")
                return parsed

    raise ValueError("No complete JSON object found.")


def _validate_parameters(parameters: dict[str, Any]) -> None:
    for key in parameters:
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
            raise QueryValidationError(f"Invalid Cypher parameter name: {key}")


def _validate_schema_identifiers(cypher: str, schema: GraphSchema) -> None:
    allowed_labels = set(schema.labels)
    allowed_relationships = set(schema.relationship_types)

    node_labels = _extract_node_labels(cypher)
    relationship_types = _extract_relationship_types(cypher)

    if allowed_labels:
        unknown = sorted(node_labels - allowed_labels)
        if unknown:
            raise QueryValidationError(
                f"Generated Cypher uses unknown node label(s): {', '.join(unknown)}"
            )

    if allowed_relationships:
        unknown = sorted(relationship_types - allowed_relationships)
        if unknown:
            raise QueryValidationError(
                "Generated Cypher uses unknown relationship type(s): "
                + ", ".join(unknown)
            )


def _extract_node_labels(cypher: str) -> set[str]:
    labels: set[str] = set()
    for node_body in re.findall(r"\(([^()\[\]]*)\)", cypher):
        node_match = re.match(
            r"\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*)?"
            r"(?P<labels>(?::\s*`?[A-Za-z_][A-Za-z0-9_]*`?\s*)+)",
            node_body,
        )
        if not node_match:
            continue
        for label in re.findall(
            r":\s*`?([A-Za-z_][A-Za-z0-9_]*)`?",
            node_match.group("labels"),
        ):
            labels.add(label)
    return labels


def _extract_relationship_types(cypher: str) -> set[str]:
    relationship_types: set[str] = set()
    relationship_pattern = re.compile(
        r"(?:<-\s*|-\s*)\[([^\[\]]*)\]\s*(?:-\s*>|-)"
    )
    for rel_body in relationship_pattern.findall(cypher):
        for rel_type in re.findall(r":\s*`?([A-Za-z_][A-Za-z0-9_]*)`?", rel_body):
            relationship_types.add(rel_type)
    return relationship_types


def _scrub_strings_and_comments(cypher: str) -> str:
    no_block_comments = re.sub(r"/\*.*?\*/", " ", cypher, flags=re.DOTALL)
    no_line_comments = re.sub(r"//.*", " ", no_block_comments)
    no_single_strings = re.sub(r"'(?:\\.|[^'\\])*'", "''", no_line_comments)
    no_double_strings = re.sub(r'"(?:\\.|[^"\\])*"', '""', no_single_strings)
    return no_double_strings
