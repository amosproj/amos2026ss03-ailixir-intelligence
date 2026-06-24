"""
Domain model for a paper in the global literature corpus.

One LiteraturePaper is stored in the `literature_papers` Firestore collection per
unique paper, keyed by its PubMed ID (pmid). This collection is the *global dedup
ledger*: before the scraper downloads + embeds a paper it checks whether the pmid
is already here, so the same paper is never embedded twice — even when it surfaces
under more than one disease (the new disease is just appended to `diseases`).

The heavy data (chunk embeddings) lives once in the AstraDB vector store; this ledger
holds only the lightweight paper-level record. Patient documents reference the corpus
by disease tag, never by copying embeddings.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class LiteraturePaper(BaseModel):
    pmid: str
    doi: str | None = None
    title: str | None = None
    diseases: list[str] = Field(default_factory=list)  # curated disease tags this paper covers
    chunk_count: int = 0                                # number of chunks embedded into AstraDB
    full_text: bool = False                             # True if PDF text, False if abstract-only
    source: str = "pubmed"
    embedded_at: datetime | None = None                 # first time the paper was embedded
    updated_at: datetime | None = None
