"""Standalone scraping subsystem (ported from amos2024ss06-health-ai-framework, MIT).

Scrapes external public sources and ingests chunked text into an AstraDB vector
store. This is intentionally decoupled from the Neo4j / Graphiti per-user knowledge
graph: it is a separate, global reference corpus with its own storage and retrieval.

Currently only the PubMed source is ported. Run from ``Backend/``:

    python -m scrapers.run_pubmed --keywords nutrition health --max-results 3

All scraped artefacts (raw JSON, temp PDFs, dedup index, logs) live under
``scrapers/data/`` (gitignored) so behaviour does not depend on the current working
directory.
"""

import json
import os

from dotenv import load_dotenv

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(PACKAGE_DIR)

# All scraped artefacts are anchored to the package, not the CWD.
DATA_DIR = os.path.join(PACKAGE_DIR, 'data')
RAW_DIR_PATH = os.path.join(DATA_DIR, 'pubmed', 'raw')
INDEX_FILE_PATH = os.path.join(DATA_DIR, 'pubmed', 'index.json')
PAPERS_DIR = os.path.join(DATA_DIR, 'papers')
LOG_DIR = os.path.join(DATA_DIR, 'log')

for _d in (RAW_DIR_PATH, PAPERS_DIR, LOG_DIR):
    os.makedirs(_d, exist_ok=True)

if not os.path.exists(INDEX_FILE_PATH):
    with open(INDEX_FILE_PATH, 'w') as _f:
        _f.write(json.dumps({'indexes': []}, indent=2))

# Reuse Backend/.env (AstraDB + OpenAI keys live there). Non-interactive, unlike the
# original src/backend/__init__.py which prompted for missing values via input().
load_dotenv(os.path.join(BACKEND_DIR, '.env'))
