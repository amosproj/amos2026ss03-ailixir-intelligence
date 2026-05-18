
# Domain-Agnostic OCR Service

A lightweight **vision-based OCR extraction service** that converts document images into **structured JSON** using OpenRouter multimodal LLMs.

Supports:
- Medical reports
- Prescriptions
- Financial documents
- Legal/technical documents
- Any general scanned image

Part of the AILixir document extraction pipeline.

---
```md
## 📁 Project Structure
ai-playground/
|
├── document-extraction/          # OCR + document parsing service (LLM-based OCR pipeline)         
│   ├── ocr_results.json          # Auto-generated OCR outputs (batch results)
│   ├── ocr_service.py            # Core OCR engine (OpenRouter vision models)
│   ├── requirements.txt          # Python dependencies
│   ├── readme.md                 # Project documentation
│   └── __pycache__/             # Python cache files
|
├── graph_pipline/               # Graph pipeline (likely KG / Neo4j / Graphiti integration)
|
├── Images/                      # Input dataset (all test images)
|
├── model_responses/            # Stored LLM raw outputs / debugging logs
|
├── OCR-Doc-Analysis/           # Legacy or experimental OCR project
|
├── schemas/                    # JSON schemas / structured output definitions
|
├── venv/                      # Python virtual environment
|
├── main.py                   # Main entry point for orchestration / pipeline execution                   
└── .env                      # Environment variables (API keys etc.)

```

---

## ⚙️ How It Works

```text
Image(s)
   ↓
ocr_service.py
   ├─ Encode image (base64)
   ├─ Send to OpenRouter vision model
   ├─ Extract structured JSON (LLM)
   └─ Save results to file
```

---

## 🚀 Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
````

### 2. Set API Key

You must set your OpenRouter API key:

**PowerShell (Windows):**

```powershell
$env:OPENROUTER_API_KEY="sk-or-..."
```

**Linux / Mac:**

```bash
export OPENROUTER_API_KEY="sk-or-..."
```

---

## ▶️ Running the Project

### ✅ 1. Run OCR on all images (default behavior)

```bash
python ocr_service.py
```

This will:

* Automatically detect all images in the folder
* Process them using the selected vision model
* Print structured JSON output
* Save results into `ocr_results.json`

---

### 🧪 2. Run tests (batch or single image)

#### Run all images:

```bash
python test_ocr.py
```

#### Run single image:

```bash
python test_ocr.py "..\Images\image (0).jpg"
```

---

## 🤖 Supported Models

Configured via OpenRouter:

| Model Key | Model                        | Notes                   |
| --------- | ---------------------------- | ----------------------- |
| `qwen-vl` | qwen/qwen2.5-vl-72b-instruct | Best free OCR accuracy  |
| `gemini`  | google/gemini-2.0-flash-exp  | Fast & lightweight      |
| `llama4`  | meta-llama/llama-4-maverick  | Free general vision     |
| `claude`  | anthropic/claude-3.5-sonnet  | Highest accuracy (paid) |

---

## 📤 Output Format

Each image is converted into structured JSON:

```json
{
  "document_type": "lab_report",
  "confidence_score": 0.95,
  "metadata": {
    "language": "en",
    "date_detected": "2025-04-16"
  },
  "extracted_fields": {
    ...
  },
  "tables": [],
  "raw_text_blocks": []
}
```

---

## 💾 Output Storage

After execution:

* Results are saved in:

```
ocr_results.json
```

This contains all processed images in a single batch.

---

## 🧠 Core Features

* 🔍 Vision-based OCR (no traditional OCR dependency)
* 📦 Fully structured JSON output
* 🧾 Table extraction support
* 🏥 Medical + general document support
* ⚡ Batch processing
* 💰 Token/cost tracking per request

---

## 🔧 Example Usage

### Run full pipeline:

```bash
python ocr_service.py
```

### Expected output:

```
🔍 Model : qwen/qwen2.5-vl-72b-instruct
📁 Found : 4 image(s)

[1/4] Processing image (0).jpg → ✅ OK
[2/4] Processing image (1).jpg → ✅ OK
...

💾 Results saved → ocr_results.json
```

---

## 📌 Notes

* Requires **OPENROUTER_API_KEY**
* Works with:

  * `.jpg`
  * `.png`
  * `.jpeg`
* Fully offline image processing except LLM API call

---

## 🔮 Future Extensions

* FastAPI endpoint (`api.py`)
* Graph ingestion (Neo4j / Graphiti)
* Multi-page PDF support
* Streaming OCR responses


