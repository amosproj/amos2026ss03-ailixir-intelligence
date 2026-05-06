from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlaygroundConfig:
    doc_type: str
    gemini_model: str
    pipeline_mode: str
    gemini_api_key: str | None

    enable_neo4j: bool
    neo4j_uri: str | None
    neo4j_user: str | None
    neo4j_password: str | None
    neo4j_database: str | None

    base_dir: Path
    images_dir: Path
    output_dir: Path


def load_config(*, base_dir: Path) -> PlaygroundConfig:
    # Load `.env` if python-dotenv is installed (keeps playground simple).
    try:
        from dotenv import load_dotenv  # type: ignore

        # Prefer a local `.env` next to this pipeline, but also support the common layout
        # where `.env` lives in `ai-playground/.env` (one directory above `graph_pipline/`).
        env_candidates = [
            base_dir / ".env",
            base_dir.parent / ".env",
        ]
        for env_path in env_candidates:
            if env_path.exists():
                load_dotenv(env_path)
                break
    except Exception:
        pass

    # Support both layouts:
    # - ai-playground/graph_pipline/{Images,model_responses}
    # - ai-playground/{Images,model_responses}
    images_candidates = [
        base_dir / "Images",
        base_dir.parent / "Images",
    ]
    images_dir = next((p for p in images_candidates if p.exists()), images_candidates[0])

    output_candidates = [
        base_dir / "model_responses",
        base_dir.parent / "model_responses",
    ]
    output_dir = next((p for p in output_candidates if p.exists()), output_candidates[0])
    output_dir.mkdir(parents=True, exist_ok=True)

    return PlaygroundConfig(
        doc_type=os.environ.get("DOC_TYPE", "medical"),
        gemini_model=os.environ.get("GEMINI_MODEL", "gemini-2.5-pro"),
        pipeline_mode=os.environ.get("PIPELINE_MODE", "gemini_graph_single"),
        gemini_api_key=os.environ.get("GEMINI_API_KEY"),
        enable_neo4j=os.environ.get("ENABLE_NEO4J", "true").lower() in {"1", "true", "yes", "on"},
        neo4j_uri=os.environ.get("NEO4J_URI"),
        # Support both common env var names.
        neo4j_user=os.environ.get("NEO4J_USER") or os.environ.get("NEO4J_USERNAME"),
        neo4j_password=os.environ.get("NEO4J_PASSWORD"),
        # AuraDB often uses database name "neo4j". If unset, driver uses default.
        neo4j_database=os.environ.get("NEO4J_DATABASE") or None,
        base_dir=base_dir,
        images_dir=images_dir,
        output_dir=output_dir,
    )

