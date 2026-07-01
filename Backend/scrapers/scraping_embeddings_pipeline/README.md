# Scraping and embedding pipeline

This folder is a standalone extraction of the project's scraping, chunking, OpenAI
embedding, and AstraDB storage pipeline. It includes AllRecipes, arXiv,
NutritionFacts, podcast, PubMed, and YouTube sources.

## Setup

Python 3.10 is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.template .env
```

Fill in the OpenAI and AstraDB values in `.env`. `YOUTUBE_DATA_API_V3` is only
needed for YouTube scraping. Podcast audio fallback additionally requires ffmpeg;
its Vosk model is downloaded on first use.

## Configure and run

Generate `data/config.json`:

```powershell
python -m src.backend.Config.main `
  --targets pubmed archive nutrition `
  --keywords prostate cancer nutrition `
  --since-date 2026-01-01 `
  --max-results 10
```

Then run the configured targets:

```powershell
python -m src.backend.Orchestrator.main
```

Run commands from this folder's root because data paths are relative to it.

## Duplicate protection

The `data/<source>/index.json` files contain IDs already processed by the current
project and are intentionally included. Keep these files in persistent storage
when moving or deploying the pipeline. Every vector also receives a deterministic
ID, so retries update the same AstraDB record rather than inserting another copy.

PubMed and arXiv additionally share `data/papers/index.json`. Before embedding,
the pipeline checks it by DOI and then by an exact normalized-title fingerprint.
Keep this registry persistent together with the source indexes.

The `raw` directories start empty; previously scraped documents and model files
were deliberately excluded from this portable folder.

## Vector Ingestion Metadata Schema

Each chunk is stored in AstraDB with the following metadata structure:

```json
{
  "domain": "medical | financial | other",
  "sub_domain": "nutrition | recipes | finance | other",
  "query_keywords": ["keyword1", "keyword2"],
  "document_keywords": ["keyword1", "keyword2"],
  "source": "allrecipes | archive | nutrition | podcast | pubmed | youtube",
  "source_type": "recipe | paper | transcript | article | video | other",
  "published_date": "ISO-8601 date string",
  "ingested_at": "ISO-8601 timestamp",
  "source_id": "unique element identifier",
  "chunk_index": "integer index of chunk within document",
  "content_section": "optional section type (e.g., transcript, keyPoints, ingredients, instructions)",
  "type": "optional content type indicator"
}
```

### Common Metadata Fields

- **domain**: Broad classification (medical, financial, etc.) set during pipeline configuration
- **sub_domain**: Finer classification (nutrition, recipes, etc.) set during pipeline configuration
- **query_keywords**: Search keywords used to discover the source
- **document_keywords**: Keywords extracted from document content
- **source**: The scraper that extracted the data
- **source_type**: The type of content (recipe, paper, transcript, etc.)
- **published_date**: Original publication date from source (if available)
- **ingested_at**: ISO-8601 timestamp when the chunk was processed
- **source_id**: Unique identifier for deduplication and retrieval
- **chunk_index**: Sequential index of this chunk within its source document

### Deterministic Vector IDs

Vector store IDs are generated deterministically from:
```
SHA256({scraper_class}:{element_id}:{chunk_index})
```

This ensures idempotent upserts—retries update existing vectors rather than creating duplicates.

## Supported Sources

| Source | Type | Key Metadata | Deduplication |
|--------|------|--------------|----------------|
| **AllRecipes** | Recipe | subTitle, rating, recipeDetails, ingredients, steps, nutritionFacts, nutritionInfo | By element_id + chunk |
| **arXiv** | Academic Paper | DOI, title, authors, abstract, published_date | By DOI (primary) or title fingerprint |
| **NutritionFacts** | Health Video/Article | Transcript, keyPoints, content_section | By element_id + chunk |
| **PubMed** | Medical Paper | DOI, title, authors, abstract, published_date | By DOI (primary) or title fingerprint |
| **YouTube** | Video/Transcript | Video metadata, transcript sections | By video_id + chunk |
| **Archive/Podcast** | Audio/Transcript | Transcript, timestamps | By element_id + chunk |

### Source-Specific Metadata

**AllRecipes recipes** additionally store:
- `subTitle`, `rating`, `recipeDetails` (prep time, cook time, servings)
- `ingredients`, `steps`, `nutritionFacts`, `nutritionInfo`

**PubMed & arXiv papers** additionally store:
- `doi`, `authors`, `abstract`, `journal` (PubMed only)
- Shared registry: `data/papers/index.json` for cross-source deduplication

**NutritionFacts & Podcasts** additionally store:
- `type`: 'transcript' or 'keyPoints'
- `content_section`: 'transcript' or 'keyPoints'

**YouTube** additionally store:
- Video metadata and transcript with timestamps
