from __future__ import annotations

import json
from pathlib import Path


def save_model_response(*, output_dir: Path, image_path: Path, output_text: str) -> Path:
    """Save Gemini output; prettify JSON when possible."""
    out_path = output_dir / f"{image_path.stem}_gemini.json"
    try:
        parsed = json.loads(output_text)
        out_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        out_path.write_text(output_text, encoding="utf-8")
    return out_path
