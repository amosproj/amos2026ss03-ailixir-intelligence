"""
main.py – Allixer OCR CLI entry point.

Replaces the original single-file script with the full pipeline.

Usage
-----
  python main.py --image test.jpg --domain medical
  python main.py --image invoice.png --domain financial --raw
"""

from __future__ import annotations
import argparse
import json
import sys
import logging
import os
from dotenv import load_dotenv

load_dotenv()

# ── Your API key ──────────────────────────────────────────────────────────────
API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = "baidu/qianfan-ocr-fast:free"
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(levelname)s │ %(message)s")

from .extractor import DocumentExtractor, ExtractionError


def main() -> None:
    parser = argparse.ArgumentParser(description="Allixer document extractor")
    parser.add_argument("--image", required=True, help="Path to the document image")
    parser.add_argument(
        "--domain",
        required=True,
        choices=["medical", "financial"],
        help="Document domain",
    )
    parser.add_argument(
        "--raw", action="store_true", help="Return raw dict (skip Pydantic validation)"
    )
    parser.add_argument("--no-clahe", action="store_true", help="Disable CLAHE")
    parser.add_argument(
        "--no-gray", action="store_true", help="Disable grayscale conversion"
    )
    args = parser.parse_args()

    extractor = DocumentExtractor(api_key=API_KEY, model=MODEL)

    pp_kwargs = {
        "grayscale": not args.no_gray,
        "clahe": not args.no_clahe,
    }

    try:
        if args.raw:
            result = extractor.extract_raw(
                args.image, domain=args.domain, preprocess_kwargs=pp_kwargs
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            result = extractor.extract(
                args.image, domain=args.domain, preprocess_kwargs=pp_kwargs
            )
            print(result.model_dump_json(indent=2))

    except ExtractionError as exc:
        print(f"[ExtractionError] {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[Unexpected error] {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
