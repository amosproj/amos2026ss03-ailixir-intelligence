

# Allixer OCR – Document Extraction System

Domain-agnostic OCR pipeline that processes medical and financial documents and returns validated, normalized JSON output.

---

## 📄 Overview

A domain-aware OCR system that extracts structured information from document images using preprocessing and LLM-based understanding.

---

## 🚀 Features

* Domain-specific extraction (medical, financial)
* Image preprocessing (grayscale, CLAHE, resizing)
* Structured JSON output
* LLM-powered extraction via OpenRouter
* Modular architecture (preprocessor, extractor, prompts, schemas)

---

## 📁 Project Structure

```
OCR-Doc-Analysis/
│
├── allixer_ocr/
│   ├── extractor.py        # Core extraction logic
│   ├── preprocessor.py     # Image preprocessing
│   ├── prompts.py          # Prompt templates for LLM
│   ├── main.py             # Pipeline orchestration
│   └── schemas/            # JSON output schemas
│
├── images/                 # Input images (test files)
│   ├── medical.png
│   └── finanical.jpg
│
├── run.py                  # CLI entry point
├── requirements.txt        # Dependencies
├── .env                    # API keys (not committed)
└── README.md
```

---

## 🧠 Data Flow

```
Image file / bytes
       │
       ▼
preprocessor.preprocess()
  • Resize (longest side ≤ 2048 px)
  • Grayscale
  • CLAHE contrast enhancement
       │
       ▼
prompts.get_prompt_factory(domain)
  • System prompt (domain rules)
  • User prompt (schema + normalization instructions)
       │
       ▼
OpenRouter Vision LLM (baidu/qianfan-ocr-fast:free)
       │
       ▼
Raw JSON response
       │
       ▼
Pydantic validation + normalization
(alias resolution, date formatting, etc.)
       │
       ▼
MedicalDocument | FinancialDocument
```

---

## ⚙️ Setup

### Install dependencies

```bash
pip install -r requirements.txt
```

---

### Add API key

Create a `.env` file in the root folder:

```
OPENROUTER_API_KEY=your_api_key_here
```

---

## ▶️ How to Run

### Medical document

```bash
python run.py --image ./images/medical.png --domain medical
```

### Financial document

```bash
python run.py --image ./images/finanical.jpg --domain financial
```

---

## ⚠️ Important Notes

* Always use the correct image path
  ❌ `./medical.png`
  ✅ `./images/medical.png`

* Ensure `.env` file contains your API key

---

## 🛠️ Key Components

* `preprocessor.py` → image enhancement
* `extractor.py` → LLM interaction + parsing
* `prompts.py` → extraction logic
* `schemas/` → structured output format
* `run.py` → CLI interface

---

## 🧪 Example Output

```json
{
  "document_type": "lab_report",
  "provider": {
    "name": "TRIVEDI JITENDRA"
  },
  "lab_results": [
    {
      "test_name": "HEMOGLOBIN",
      "value": "11.0/9.6/9.6 gm%"
    }
  ]
}
```

---
## 📜 License

This project is licensed under the MIT License.

Note: This project uses external APIs (OpenRouter). Usage of those services is subject to their respective terms and conditions.
## 👨‍💻 Author

Muhammad Zeeshan


