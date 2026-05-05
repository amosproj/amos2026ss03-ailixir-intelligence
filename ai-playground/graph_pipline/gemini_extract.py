from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from graph_pipline.image_utils import infer_mime_type


def extract_structured_from_image(
    client: genai.Client,
    *,
    model: str,
    image_path: Path,
    schema: dict[str, Any],
) -> str:
    prompt = f"""
You are a strict information extraction engine.

TASK:
Extract structured data from the document image and return ONLY valid JSON.

RULES (VERY IMPORTANT):
- Output MUST be valid JSON
- No markdown (no ``` or text)
- No explanation
- No extra keys
- Must follow schema exactly
- If a value is missing, use null
- Do not include any text outside the JSON

SCHEMA:
{json.dumps(schema, indent=2)}

Return ONLY JSON.
""".strip()

    image_bytes = image_path.read_bytes()
    mime_type = infer_mime_type(image_path)

    resp = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_text(text=prompt),
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ],
    )
    return (resp.text or "").strip()


def extract_graph_payload_from_image(
    client: genai.Client,
    *,
    model: str,
    image_path: Path,
    schema: dict[str, Any],
    doc_type: str,
) -> str:
    prompt = f"""
You are a strict information extraction engine for knowledge graph ingestion.

TASK:
From the document image, produce ONE JSON object containing BOTH:
1) "schema_json": extracted structured data following the provided SCHEMA exactly
2) "graph": a small knowledge graph derived from the same document

RULES (VERY IMPORTANT):
- Output MUST be valid JSON
- No markdown (no ```), no explanations, no extra text
- Do not invent facts. If missing, use null or omit a graph element.
- "schema_json" MUST follow SCHEMA exactly (no extra keys)

SCHEMA:
{json.dumps(schema, indent=2)}

GRAPH FORMAT:
{{
  "nodes": [
    {{
      "id": "stable-string-id",
      "labels": ["EntityType"],
      "properties": {{"name": "..." }}
    }}
  ],
  "relationships": [
    {{
      "source": "node-id",
      "type": "RELATION_TYPE_IN_CAPS_WITH_UNDERSCORES",
      "target": "node-id",
      "properties": {{}}
    }}
  ]
}}

STABLE IDs:
- Use deterministic ids like: "{doc_type}:patient:<name>", "{doc_type}:provider:<name>", "{doc_type}:doc:{image_path.stem}"
- Keep ids consistent across nodes/relationships within this output.

Return ONLY JSON with keys: "schema_json" and "graph".
""".strip()

    image_bytes = image_path.read_bytes()
    mime_type = infer_mime_type(image_path)

    resp = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_text(text=prompt),
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ],
    )
    return (resp.text or "").strip()


def extract_json(text: str) -> Any:
    text = text.strip()

    # remove markdown fences
    text = text.replace("```json", "").replace("```", "")

    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON start found")

    stack = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            stack += 1
        elif text[i] == "}":
            stack -= 1

        if stack == 0:
            candidate = text[start : i + 1]
            return json.loads(candidate)

    raise ValueError("No valid JSON object found")
