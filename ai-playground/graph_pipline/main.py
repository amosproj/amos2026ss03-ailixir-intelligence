from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

from google import genai

if __package__ in {None, ""}:
    # Allow running as a script: `python graph_pipline/main.py` from within `ai-playground/`.
    # Prefer module mode: `python -m graph_pipline.main`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph_pipline.gemini_extract import (  # noqa: E402
    extract_graph_payload_from_image,
    extract_json,
    extract_structured_from_image,
)
from graph_pipline.image_utils import ALLOWED_IMAGE_EXTS, image_sort_key  # noqa: E402
from graph_pipline.neo4j_ingest import ingest_graph_payload  # noqa: E402
from graph_pipline.output_utils import save_model_response  # noqa: E402
from graph_pipline.playground_config import load_config  # noqa: E402
from graph_pipline.schemas_loader import get_schema  # noqa: E402


def main() -> None:
    cfg = load_config(base_dir=Path(__file__).resolve().parent)
    if not cfg.gemini_api_key:
        raise ValueError(
            "Missing GEMINI_API_KEY. Put it in `ai-playground/graph_pipline/.env` "
            "or `ai-playground/.env`, or export it in your environment."
        )
    schema = get_schema(cfg.doc_type)
    client = genai.Client(api_key=cfg.gemini_api_key)

    image_paths = [p for p in cfg.images_dir.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_IMAGE_EXTS]
    image_paths = sorted(image_paths, key=image_sort_key)[1:2]## second image only

    if not image_paths:
        raise FileNotFoundError(f"No images found in: {cfg.images_dir}")

    for idx, image_path in enumerate(image_paths, start=1):
        print(f"\n=== [{idx}/{len(image_paths)}] Processing: {image_path.name} ===")

        # Use a stable document id for retrieval/dedup (independent of timestamped filenames).
        # This becomes the Neo4j :Document.source_id and relationship provenance key.
        image_bytes_for_id = image_path.read_bytes()
        content_hash = hashlib.sha256(image_bytes_for_id).hexdigest()[:16]
        source_id = f"{cfg.doc_type}:{content_hash}"

        output = ""
        if cfg.pipeline_mode == "gemini_graph_single":
            print("Sending image to Gemini (single-call graph + schema)...")
            output = extract_graph_payload_from_image(
                client,
                model=cfg.gemini_model,
                image_path=image_path,
                schema=schema,
                doc_type=cfg.doc_type,
            )
        elif cfg.pipeline_mode == "gemini_vision_single":
            print("Sending image to Gemini (one-step vision extraction)...")
            output = extract_structured_from_image(
                client,
                model=cfg.gemini_model,
                image_path=image_path,
                schema=schema,
            )
        else:
            raise ValueError(
                f"Unsupported PIPELINE_MODE={cfg.pipeline_mode}. "
                "Use gemini_graph_single or gemini_vision_single."
            )

        # ----------------------------
        # 7. parse JSON (for console) + save to disk (for your request)
        # ----------------------------
        print("\n--- PARSED JSON ---\n")
        try:
            # parsed = json.loads(output)
            parsed=extract_json(output)
            print(json.dumps(parsed, indent=2))
        except Exception:
            print("No valid JSON returned by Gemini.")

        saved_path = save_model_response(output_dir=cfg.output_dir, image_path=image_path, output_text=json.dumps(parsed, indent=2))
        print(f"Saved Gemini response to: {saved_path}")

        # ----------------------------
        # 8. Neo4j ingest (optional; still one Gemini call)
        # ----------------------------
        if not (cfg.enable_neo4j and cfg.neo4j_uri and cfg.neo4j_user and cfg.neo4j_password):
            continue

        try:
            payload = extract_json(output)
        except Exception:
            continue

        try:
            if cfg.pipeline_mode == "gemini_graph_single" and isinstance(payload, dict) and "graph" in payload:
                ingest_graph_payload(
                    payload,
                    source_id=source_id,
                    doc_type=cfg.doc_type,
                    neo4j_uri=cfg.neo4j_uri,
                    neo4j_user=cfg.neo4j_user,
                    neo4j_password=cfg.neo4j_password,
                    neo4j_database=cfg.neo4j_database,
                )
                print("Neo4j graph ingestion complete.")
        except Exception as exc:
            print(f"[Neo4j ingest skipped/failed] {exc}")
        ## one image


if __name__ == "__main__":
    main()