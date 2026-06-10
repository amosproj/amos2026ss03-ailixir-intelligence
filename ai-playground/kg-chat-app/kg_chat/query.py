from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from kg_chat.llm import LlmClient
from kg_chat.models import QueryPlan
from kg_chat.prompts import build_query_prompt, build_query_repair_prompt
from kg_chat.schema_cache import GraphSchema


class QueryGenerationError(RuntimeError):
    pass


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


def generate_query_plan(
    *,
    llm: LlmClient,
    question: str,
    schema: GraphSchema,
    history_text: str,
    default_limit: int,
) -> QueryPlan:
    prompt = build_query_prompt(
        question=question,
        schema_text=schema.to_prompt(),
        history_text=history_text,
        default_limit=default_limit,
    )
    raw = llm.generate_text(prompt, temperature=0.0)
    schema_text = schema.to_prompt()
    try:
        payload = extract_json_object(raw)
        return QueryPlan.model_validate(payload)
    except Exception as first_exc:
        repair_prompt = build_query_repair_prompt(
            question=question,
            schema_text=schema_text,
            history_text=history_text,
            default_limit=default_limit,
            invalid_response=raw,
            error=str(first_exc),
        )
        repaired_raw = llm.generate_text(repair_prompt, temperature=0.0)
        try:
            payload = extract_json_object(repaired_raw)
            return QueryPlan.model_validate(payload)
        except Exception as second_exc:
            return _build_fallback_query_plan(
                schema=schema,
                question=question,
                default_limit=default_limit,
                error=(
                    "LLM query generation failed after retry. "
                    f"Last error: {second_exc}. "
                    f"Last raw response: {_shorten_raw_response(repaired_raw or raw)}"
                ),
            )


def _shorten_raw_response(text: str, max_chars: int = 800) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars] + "...<truncated>"


def _build_fallback_query_plan(
    *,
    schema: GraphSchema,
    question: str,
    default_limit: int,
    error: str,
) -> QueryPlan:
    if "Entity" in schema.labels and "RELATES_TO" in schema.relationship_types:
        return QueryPlan(
            cypher="""
MATCH (source:Entity)-[relationship:RELATES_TO]->(target:Entity)
WHERE toLower(
  coalesce(source.name, '') + ' ' +
  coalesce(source.summary, '') + ' ' +
  coalesce(target.name, '') + ' ' +
  coalesce(target.summary, '') + ' ' +
  coalesce(relationship.name, '') + ' ' +
  coalesce(relationship.fact, '')
) CONTAINS toLower($query)
RETURN source.name AS source,
       source.labels AS source_labels,
       relationship.name AS relationship,
       relationship.fact AS fact,
       target.name AS target,
       target.labels AS target_labels
LIMIT $limit
""".strip(),
            parameters={"query": question, "limit": default_limit},
            reason=f"Fallback Graphiti Entity/RELATES_TO search used. {error}",
        )

    if schema.observed_patterns:
        pattern = schema.observed_patterns[0]
        source_label = _first_identifier(pattern.get("source_labels")) or ""
        relationship_type = _identifier(pattern.get("relationship_type")) or ""
        target_label = _first_identifier(pattern.get("target_labels")) or ""
        source = f"source:{source_label}" if source_label else "source"
        relationship = (
            f"relationship:{relationship_type}" if relationship_type else "relationship"
        )
        target = f"target:{target_label}" if target_label else "target"
        return QueryPlan(
            cypher=(
                f"MATCH ({source})-[{relationship}]->({target}) "
                "RETURN source, relationship, target "
                "LIMIT $limit"
            ),
            parameters={"limit": default_limit},
            reason=f"Fallback observed-pattern query used. {error}",
        )

    return QueryPlan(
        cypher="MATCH (node) RETURN node LIMIT $limit",
        parameters={"limit": default_limit},
        reason=f"Fallback all-node query used. {error}",
    )


def _first_identifier(values: Any) -> str | None:
    if not isinstance(values, list) or not values:
        return None
    return _identifier(values[0])


def _identifier(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", value):
        return value
    return None


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
    for rel_body in re.findall(r"\[([^\[\]]*)\]", cypher):
        for rel_type in re.findall(r":\s*`?([A-Za-z_][A-Za-z0-9_]*)`?", rel_body):
            relationship_types.add(rel_type)
    return relationship_types


def _scrub_strings_and_comments(cypher: str) -> str:
    no_block_comments = re.sub(r"/\*.*?\*/", " ", cypher, flags=re.DOTALL)
    no_line_comments = re.sub(r"//.*", " ", no_block_comments)
    no_single_strings = re.sub(r"'(?:\\.|[^'\\])*'", "''", no_line_comments)
    no_double_strings = re.sub(r'"(?:\\.|[^"\\])*"', '""', no_single_strings)
    return no_double_strings
