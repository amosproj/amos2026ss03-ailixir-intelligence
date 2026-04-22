

# Verdict / Final Decision :

- Initially we can compare between **PaddleOCR-VL 1.5** & **dots.ocr** & **Gemini 3 Pro** because of there capabilities in dealing with complex Layouts.
- Th Other comprehensive information just in case we needed testing alternatives OCRs in the future.

# Open source OCR Models for Layout & Table Detection (2025–2026)


## Benchmark Glossary


| Benchmark | What it tests | Score type |
|---|---|---|
| **OmniDocBench v1.5** | End-to-end document parsing: text, tables, formulas, layout, reading order across 1,651 PDF pages (CVPR 2025) | 0–100, higher = better |
| **olmOCR-Bench** | Binary pass/fail on hard doc types: ArXiv papers, old scans, tables, multi-column, long text | 0–100 pass rate |
| **PubTabNet** | Table structure recognition — does the model correctly reconstruct a table's HTML/structure? | 0–100, higher = better |
| **TEDS** | Tree Edit Distance Similarity — measures how close the model's table output is to the real table structure | 0–100, higher = better |
| **OCRBench v2** | Pure text recognition across 10,000 QA pairs, 31 document scenarios | 0–100, higher = better |

---

## Top Models Compared

| Model                | Type                        | Params   | VRAM Needed               | Table Extraction | Layout Detection | Speed           | License             |
| -------------------- | --------------------------- | -------- | ------------------------- | ---------------- | ---------------- | --------------- | ------------------- |
| **PaddleOCR-VL 1.5** | VLM (2-stage pipeline)      | 0.9B     | ~6 GB                     | ✅ SOTA           | ✅ SOTA           | 🚀 Fastest      | Apache 2.0          |
| **dots.ocr**         | VLM (fine-tuned Qwen2.5-VL) | 1.7B     | ~8 GB                     | ✅ Strong         | ✅ Strong         | 🚀 Fast         | Apache 2.0          |
| **Qwen2.5-VL**       | VLM (general purpose)       | 7B – 72B | 16 GB (7B) / 80 GB+ (72B) | ✅ SOTA           | ✅ SOTA           | 🐢 Slow (large) | Apache 2.0 / Custom |
| **olmOCR**           | VLM (fine-tuned Qwen2-VL)   | 7B       | ~16 GB                    | ✅ Strong         | ✅ Strong         | ⚠️ Medium       | Apache 2.0          |
| **Surya**            | Transformer (lightweight)   | ~250M    | ~4 GB (or CPU)            | ✅ Good           | ✅ Strong         | 🚀 Fast         | GPL-3.0             |
| **Marker**           | Pipeline (built on Surya)   | ~500M    | ~6 GB                     | ✅ Good           | ✅ Strong         | ⚠️ Medium       | GPL-3.0             |

---

## Benchmark Scores

> Scores sourced from OmniDocBench v1.5 leaderboard (March 2026), olmOCR-Bench, and published model papers.


| Model                | OmniDocBench v1.5 ↑ | OCRBench v2 (Text) ↑ | PubTabNet (Table) ↑ | TEDS (Table) ↑ | olmOCR-Bench ↑ | Throughput        |
| -------------------- | ------------------- | -------------------- | ------------------- | -------------- | -------------- | ----------------- |
| **PaddleOCR-VL 1.5** | **94.5**            | 75.3                 | 84.6                | 83.3           | ~79–80         | 🚀 ~2 pages/sec   |
| **dots.ocr**         | 88.4                | **92.1**             | 71.0                | 62.4           | ~79–80         | 🚀 ~2 pages/sec   |
| **Qwen2.5-VL 72B**   | ~89+                | -                    | -                   | -              | -              | 🐢 Slow           |
| **olmOCR 7B**        | -                   | -                    | -                   | -              | **82.4**       | ⚠️ 1.78 pages/sec |
| **Surya**            | -                   | -                    | -                   | -              | -              | 🚀 Fast (CPU ok)  |
| **Marker**           | -                   | -                    | -                   | -              | -              | ⚠️ Medium         |
| *Gemini 3 Pro (ref)* | *90.3*              | *91.9*               | *91.4*              | *81.8*         | *-*            | *Cloud API*       |
| *GPT-5.2 (ref)*      | *85.4*              | *83.7*               | *84.4*              | *67.6*         | *-*            | *Cloud API*       |
_____




# Google OCrs


|                         | **Enterprise Document OCR** (`OCR_PROCESSOR`)                                  | **Form Parser** (`FORM_PARSER_PROCESSOR`)                                             | **Layout Parser** (`LAYOUT_PARSER_PROCESSOR`)                                       |
| ----------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| **Category**            | Digitize                                                                       | Extract                                                                               | Extract / Chunk                                                                     |
| **Purpose**             | Raw text & handwriting extraction, quality assessment                          | Structured form extraction — KVPs, tables, checkboxes, 11 generic entities            | Document layout analysis + context-aware chunking for RAG / GenAI pipelines         |
| **Best for**            | 200+ languages, handwriting, quality scoring                                   | Intake forms, invoices, surveys, high-volume                                          | PDFs, DOCX, PPTX, XLSX, HTML                                                        |
| **Key outputs**         | Text tokens, paragraphs, words, bounding boxes, quality signals, reading order | KVPs, tables, checkboxes, generic entities (email, phone, address, person…), OCR text | Headings, paragraphs, lists, tables — plus chunked sections ready for vector search |
| **Uptraining**          | No                                                                             | No                                                                                    | No                                                                                  |
| **Price (≤ threshold)** | $1.50 / 1K pages (up to 5M)                                                    | $30.00 / 1K pages (up to 1M)                                                          | $10.00 / 1K pages (flat)                                                            |
| **Price (> threshold)** | $0.60 / 1K pages after 5M                                                      | $20.00 / 1K pages after 1M                                                            | $10.00 / 1K pages (no discount)                                                     |
| **Sync page limit**     | 15 (30 w/ imageless)                                                           | 15 (30 w/ imageless)                                                                  | 15 (30 w/ imageless)                                                                |
| **Batch page limit**    | 500                                                                            | 100                                                                                   | 500                                                                                 |
| **File types**          | PDF, images, TIFF                                                              | PDF, images, TIFF                                                                     | PDF, HTML, DOCX, PPTX, XLSX                                                         |





# Preprocessing steps 

1. Grayscale (convert to black & white shades)
2. CLAHE (Contrast Limited Adaptive Histogram Equalization)


### Useful links

[AI Models Pricing & Benchmarks Comparison - 1900+ LLM Models | CloudPrice](https://cloudprice.net/models)

##### Google
###### 1. Planning & Cost
- [Pricing](https://cloud.google.com/document-ai/pricing)

###### 2. Available Processors
- [Processor List](https://docs.cloud.google.com/document-ai/docs/processors-list)

###### 3. OCR Processors
- [Enterprise Document OCR](https://docs.cloud.google.com/document-ai/docs/enterprise-document-ocr)
- [Digitize Text Processor](https://docs.cloud.google.com/document-ai/docs/processors-list#digitize_text)

###### 4. Parsing Processors
- [Layout Parser Processor](https://docs.cloud.google.com/document-ai/docs/processors-list#processor_layout-parser)
- [Form Parser](https://docs.cloud.google.com/document-ai/docs/form-parser)


###### 5. May be have potential in the future

[MedGemma – Vertex AI – Google Cloud console](https://console.cloud.google.com/vertex-ai/publishers/google/model-garden/medgemma) light weight and low cost




