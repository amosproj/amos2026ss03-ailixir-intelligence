"""
test_ocr.py  —  Quick OCR test using OpenRouter Vision Models
─────────────────────────────────────────────────────────────
Reads images from a local folder, extracts structured JSON via an LLM.

NOTE: DeepSeek V4 Flash is TEXT-ONLY (no image support).
      For OCR we use a free vision model on the same OpenRouter API key:
        → qwen/qwen2.5-vl-72b-instruct   (default, best free OCR)
        → google/gemini-2.0-flash-exp     (alternative)
        → meta-llama/llama-4-maverick     (alternative)

Usage:
    python test_ocr.py                      # processes all images in ./Images/
    python test_ocr.py path/to/image.jpg    # single image
    python test_ocr.py Images/              # whole folder
"""

import base64
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

# ── Load .env from parent folder (where your .env lives) ──────────────────
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
load_dotenv()  # also try current dir as fallback

# ── Config ─────────────────────────────────────────────────────────────────
API_KEY = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPEN_ROUTER_API_KEY")
MODEL = "qwen/qwen2.5-vl-72b-instruct"  # ← free vision model
API_URL = "https://openrouter.ai/api/v1/chat/completions"
IMAGE_DIR = Path(__file__).parent.parent / "Images"  # ../Images relative to this file

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

# ── Domain-agnostic extraction prompt ──────────────────────────────────────
SYSTEM_PROMPT = """You are an expert document analysis AI. Extract ALL meaningful
information from document images — regardless of domain (medical, financial, legal,
technical, academic, etc.) — and return clean structured JSON.

Rules:
1. Auto-detect document type (invoice, lab report, form, receipt, contract, etc.).
2. Extract EVERY field with semantic value. Do NOT summarise or skip.
3. Use snake_case English keys (e.g. patient_name, total_amount).
4. Preserve original values exactly — do not convert units.
5. Missing or illegible values → null.
6. Group related fields into nested objects (e.g. patient_info, line_items).
7. Tables / repeating rows → JSON array.
8. Return ONLY valid JSON — no markdown, no explanation, no preamble.

Output schema (adapt fields to the actual document):
{
  "document_type": "<detected type>",
  "confidence_score": <0.0-1.0>,
  "metadata": {
    "language": "<ISO 639-1>",
    "date_detected": "<ISO 8601 or null>"
  },
  "extracted_fields": { ... },
  "tables": [ ... ],
  "raw_text_blocks": ["<paragraph 1>", "..."]
}"""


# ── Helpers ─────────────────────────────────────────────────────────────────


def encode_image(path: Path) -> str:
    """Return base64-encoded image string."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def mime_type(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(ext, "image/jpeg")


def call_openrouter(image_path: Path) -> dict:
    """Send one image to OpenRouter and return parsed JSON result."""
    b64 = encode_image(image_path)
    mime = mime_type(image_path)
    data_url = f"data:{mime};base64,{b64}"

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                    {
                        "type": "text",
                        "text": (
                            "Extract all information from this document image "
                            "and return structured JSON only."
                        ),
                    },
                ],
            },
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        API_URL, headers=headers, data=json.dumps(payload), timeout=120
    )
    response.raise_for_status()

    raw_text = response.json()["choices"][0]["message"]["content"]
    usage = response.json().get("usage", {})

    # Strip accidental markdown fences if the model adds them
    clean = raw_text.strip()
    if clean.startswith("```"):
        clean = clean.split("```", 1)[1]
        if clean.startswith("json"):
            clean = clean[4:]
        clean = clean.rsplit("```", 1)[0].strip()

    try:
        extracted = json.loads(clean)
        success = True
    except json.JSONDecodeError:
        extracted = {"parse_error": "Model did not return valid JSON", "raw": raw_text}
        success = False

    return {
        "file": image_path.name,
        "success": success,
        "extracted_data": extracted,
        "tokens_used": usage,
    }


def collect_images(source: str | None) -> list[Path]:
    """Return list of image paths from a file, folder, or default Images/ dir."""
    if source is None:
        target = IMAGE_DIR
    else:
        target = Path(source)

    if target.is_file():
        return [target]

    if target.is_dir():
        images = sorted(
            p for p in target.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        if not images:
            print(f"⚠  No supported images found in {target}")
        return images

    print(f"❌  Path not found: {target}")
    return []


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    if not API_KEY:
        print("❌  OPENROUTER_API_KEY not found.")
        print("    Add it to your .env file:  OPENROUTER_API_KEY=sk-or-...")
        sys.exit(1)

    source = sys.argv[1] if len(sys.argv) > 1 else None
    images = collect_images(source)

    if not images:
        sys.exit(1)

    print(f"\n🔍  Model : {MODEL}")
    print(f"📁  Found : {len(images)} image(s)\n")
    print("=" * 60)

    all_results = []

    for idx, img_path in enumerate(images, 1):
        print(f"\n[{idx}/{len(images)}]  Processing:  {img_path.name}")
        print(f"           Size   :  {img_path.stat().st_size // 1024} KB")

        try:
            result = call_openrouter(img_path)

            status = "✅ OK" if result["success"] else "⚠  JSON parse failed"
            print(f"           Status :  {status}")
            print(f"           Tokens :  {result['tokens_used']}")
            print("\n--- Extracted JSON " + "-" * 41)
            print(json.dumps(result["extracted_data"], indent=2, ensure_ascii=False))
            print("-" * 60)

        except requests.HTTPError as e:
            result = {"file": img_path.name, "success": False, "error": str(e)}
            print(f"           ❌ HTTP Error: {e}")
        except Exception as e:
            result = {"file": img_path.name, "success": False, "error": str(e)}
            print(f"           ❌ Error: {e}")

        all_results.append(result)

    # Save combined output
    out_path = Path(__file__).parent / "ocr_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    success_count = sum(1 for r in all_results if r.get("success"))
    print(f"\n✅  Done: {success_count}/{len(images)} succeeded")
    print(f"💾  Results saved → {out_path}\n")


if __name__ == "__main__":
    main()
