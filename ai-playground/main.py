from paddleocr import PaddleOCRVL
from schemas.medical_schema import MEDICAL_SCHEMA
from schemas.financial_schema import FINANCIAL_SCHEMA
from google import genai

import json
import os
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# ----------------------------
# config
# ----------------------------
DOC_TYPE = "medical"
GEMINI_MODEL = "gemini-2.5-flash"

# If you prefer, set GEMINI_API_KEY as an environment variable.
# The code below keeps your existing inline key behavior working.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyDxHSmfPrH2dUHSR9AsgHzQDxP-tXhw5bM")

BASE_DIR = Path(__file__).resolve().parent
IMAGES_DIR = BASE_DIR / "Images"
OUTPUT_DIR = BASE_DIR / "model_responses"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _image_sort_key(p: Path) -> int:
    """Sort like image (0).jpg, image (1).jpg, ..."""
    m = re.search(r"\((\d+)\)", p.stem)
    return int(m.group(1)) if m else 10**9


def _extract_raw_text(ocr: PaddleOCRVL, image_path: Path, simple_prompt: str) -> str:
    res = list(ocr.predict(str(image_path), prompt=simple_prompt))[0]
    if isinstance(res, dict):
        return res.get("text") or res.get("markdown_texts") or str(res)
    return str(res)


def _save_gemini_response(image_path: Path, output_text: str) -> Path:
    """
    Save the model response.
    - If it is valid JSON, save prettified JSON.
    - Otherwise, save the raw text.
    """
    out_path = OUTPUT_DIR / f"{image_path.stem}_gemini.json"
    try:
        parsed = json.loads(output_text)
        out_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        out_path.write_text(output_text, encoding="utf-8")
    return out_path


def main() -> None:
    # ----------------------------
    # 1. load PaddleOCR-VL
    # ----------------------------
    print("Loading PaddleOCR-VL...")
    ocr = PaddleOCRVL()
    print("Model loaded.")

    # ----------------------------
    # 2. pick schema (constant per run)
    # ----------------------------
    schema = MEDICAL_SCHEMA if DOC_TYPE == "medical" else FINANCIAL_SCHEMA

    # ----------------------------
    # 3. load Gemini client (constant per run)
    # ----------------------------
    client = genai.Client(api_key=GEMINI_API_KEY)

    # ----------------------------
    # 4. gather the 4 images
    # ----------------------------
    allowed_ext = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
    image_paths = [
        p
        for p in IMAGES_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in allowed_ext
    ]
    image_paths = sorted(image_paths, key=_image_sort_key)[:4]

    if not image_paths:
        raise FileNotFoundError(f"No images found in: {IMAGES_DIR}")

    simple_prompt = "Read and transcribe all text in this image exactly as it appears."

    for idx, image_path in enumerate(image_paths, start=1):
        print(f"\n=== [{idx}/{len(image_paths)}] Processing: {image_path.name} ===")

        # ----------------------------
        # 5. OCR (raw text)
        # ----------------------------
        print("Running OCR inference...")
        raw_text = _extract_raw_text(ocr, image_path, simple_prompt=simple_prompt)
        print("\n--- RAW OCR TEXT ---\n")
        print(raw_text)

        # ----------------------------
        # 6. send raw text + schema to Gemini
        # ----------------------------
        print("\nSending to Gemini for structured extraction...")
        gemini_prompt = f"""
You are a strict information extraction engine.

TASK:
Extract structured data from the text below and return ONLY valid JSON.

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

TEXT:
{raw_text}

Return ONLY JSON.
"""

        gemini_response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=gemini_prompt,
        )
        output = gemini_response.text.strip()

        # ----------------------------
        # 7. parse JSON (for console) + save to disk (for your request)
        # ----------------------------
        print("\n--- PARSED JSON ---\n")
        try:
            parsed = json.loads(output)
            print(json.dumps(parsed, indent=2))
        except Exception:
            match = re.search(r"\{.*\}", output, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                    print(json.dumps(parsed, indent=2))
                except Exception:
                    print("Found JSON-like block but failed parsing.")
            else:
                print("No valid JSON returned by Gemini.")

        saved_path = _save_gemini_response(image_path, output)
        print(f"Saved Gemini response to: {saved_path}")


if __name__ == "__main__":
    main()