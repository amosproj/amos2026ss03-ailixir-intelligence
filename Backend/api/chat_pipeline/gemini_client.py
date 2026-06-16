"""
Singleton async Gemini/Vertex AI client for the chat pipeline.

Mirrors workers/connections/gemini_client.py. Kept separate so the chat
pipeline is self-contained and the workers package is not imported by the API.

Uses Application Default Credentials (ADC):
  Local:  gcloud auth application-default login
  GCP:    the Cloud Run service account is used automatically

Required env vars:
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
            project  = os.environ["VERTEX_PROJECT"]
            location = os.environ.get("VERTEX_LOCATION", _DEFAULT_LOCATION)
            _client  = genai.Client(vertexai=True, project=project, location=location)
            _log.info("gemini_client_created project=%s location=%s", project, location)
    return _client
