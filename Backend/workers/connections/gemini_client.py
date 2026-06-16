"""
Singleton Gemini/Vertex AI client for the LLM extraction step.

Uses Application Default Credentials (ADC) — no API key needed.
  Local:  gcloud auth application-default login
  GCP:    the service account attached to the Cloud Run instance is used automatically.

The service account needs roles/aiplatform.user (same grant used by Graphiti).

This client handles only the document analysis and summary update steps.
Graphiti maintains its own internal Gemini client (via the paced wrappers
in workers/connections/paced_gemini.py) for entity extraction and embeddings.

Configure via (same env vars as Graphiti):
  VERTEX_PROJECT  — GCP project ID
  VERTEX_LOCATION — region (default: us-central1)
"""

from __future__ import annotations

import asyncio
import logging
import os

from google import genai

_log = logging.getLogger(__name__)

_client: genai.Client | None = None
_lock = asyncio.Lock()
_DEFAULT_LOCATION = "us-central1"


async def get_gemini_client() -> genai.Client:
    """Return the shared Gemini client, initialising on first call."""
    global _client
    async with _lock:
        if _client is None:
            project = os.environ["VERTEX_PROJECT"]
            location = os.environ.get("VERTEX_LOCATION", _DEFAULT_LOCATION)
            _client = genai.Client(
                vertexai=True,
                project=project,
                location=location,
            )
            _log.info(
                "gemini_client_created project=%s location=%s",
                project,
                location,
            )
    return _client
