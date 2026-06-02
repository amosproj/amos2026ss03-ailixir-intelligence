"""
Shared config for the pipeline_refinement playground.

Auth: Application Default Credentials (ADC) — no API key needed.
  Local:  gcloud auth application-default login
  GCP:    service account on Cloud Run is used automatically

Env vars (set in ai-playground/.env or export before running):
  VERTEX_PROJECT   — GCP project ID  (required)
  VERTEX_LOCATION  — region          (default: us-central1)
  VERTEX_LLM_MODEL — Gemini model    (default: gemini-2.5-flash)
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials
from firebase_admin import firestore as fb_firestore
from google import genai
from google.cloud.firestore_v1 import Client

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent           # pipeline_refinement/
_PLAYGROUND = _HERE.parent                         # ai-playground/
_BACKEND = _PLAYGROUND.parent / "Backend"
_FIREBASE_KEY = (
    _BACKEND / "shared" / "keys" / "amos26-firebase-adminsdk-fbsvc-c05787eb8f.json"
)

# Load .env from ai-playground root
load_dotenv(dotenv_path=_PLAYGROUND / ".env")

# ── Vertex AI ─────────────────────────────────────────────────────────────────
VERTEX_PROJECT: str = os.environ.get("VERTEX_PROJECT", "")
VERTEX_LOCATION: str = os.environ.get("VERTEX_LOCATION", "us-central1")
LLM_MODEL: str = os.environ.get("VERTEX_LLM_MODEL", "gemini-2.5-flash")

_gemini_client: genai.Client | None = None
_gemini_lock = threading.Lock()


def get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    with _gemini_lock:
        if _gemini_client is None:
            if not VERTEX_PROJECT:
                raise EnvironmentError(
                    "VERTEX_PROJECT is not set. "
                    "Add it to ai-playground/.env: VERTEX_PROJECT=your-gcp-project-id\n"
                    "Also run: gcloud auth application-default login"
                )
            _gemini_client = genai.Client(
                vertexai=True,
                project=VERTEX_PROJECT,
                location=VERTEX_LOCATION,
            )
    return _gemini_client


# ── Firestore ─────────────────────────────────────────────────────────────────
_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "amos26")
_db: Client | None = None
_fs_lock = threading.Lock()


def get_firestore() -> Client:
    global _db
    if _db is not None:
        return _db
    with _fs_lock:
        if _db is None:
            if not firebase_admin._apps:
                if not _FIREBASE_KEY.is_file():
                    raise FileNotFoundError(
                        f"Firebase service account key not found at:\n  {_FIREBASE_KEY}\n"
                        "Make sure the Backend/shared/keys/ directory is present."
                    )
                cred = credentials.Certificate(str(_FIREBASE_KEY))
                firebase_admin.initialize_app(cred)
            _db = fb_firestore.client()
    return _db
