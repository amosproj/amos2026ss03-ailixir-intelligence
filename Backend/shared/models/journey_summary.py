"""
Domain model for the patient journey summary.

One JourneySummary is stored in the `journey_summaries` Firestore collection
per user (keyed by uid). It is created when the first document is processed
and updated in-place after each subsequent document.

The summary is a concise, clinician-readable narrative of the patient's full
medical journey across all documents processed so far. It is also passed back
to the LLM extraction step as context, so each new document is interpreted
relative to the patient's known history.
"""

from datetime import datetime

from pydantic import BaseModel


class JourneySummary(BaseModel):
    uid: str
    summary: str
    document_count: int = 0
    last_updated: datetime | None = None
    last_extraction_id: str | None = None
