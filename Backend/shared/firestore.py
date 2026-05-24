"""
Firebase Admin SDK bootstrap and Firestore client accessor.

Both the API service and the (future) workers go through `get_firestore()` to obtain
a Firestore client. Initialisation is lazy and thread-safe: the first call sets up
the Firebase app and caches the client; later calls return the cached client.

When the FIRESTORE_EMULATOR_HOST or FIREBASE_AUTH_EMULATOR_HOST environment variable
is set, the SDK auto-routes traffic to the emulator and skips credential validation.
That makes local development and CI tests possible without a real service account key.
"""

import os
import threading
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import Client

# Backend root is the parent of this `shared/` directory. Resolving once at import
# time avoids surprises from changing working directories (e.g. uvicorn vs pytest).
BACKEND_ROOT = Path(__file__).resolve().parent.parent

_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "amos26")
_KEY_RELATIVE_PATH = os.getenv(
    "FIREBASE_KEY_RELATIVE_PATH",
    "amos26-firebase-adminsdk-fbsvc-c05787eb8f.json",
)
_KEY_PATH = BACKEND_ROOT / _KEY_RELATIVE_PATH

_init_lock = threading.Lock()
_db: Client | None = None


def _emulator_mode() -> bool:
    return bool(
        os.getenv("FIRESTORE_EMULATOR_HOST") or os.getenv("FIREBASE_AUTH_EMULATOR_HOST")
    )


def ensure_firebase_app() -> None:
    """Initialise the Firebase Admin SDK app exactly once. Safe to call repeatedly."""
    if firebase_admin._apps:
        return
    with _init_lock:
        # Re-check inside the lock — another thread may have completed init while we waited.
        if firebase_admin._apps:
            return
        if _emulator_mode():
            firebase_admin.initialize_app(options={"projectId": _PROJECT_ID})
            return
        if not _KEY_PATH.exists():
            raise FileNotFoundError(
                f"Firebase service account key not found.\n"
                f"  Expected at: {_KEY_PATH}\n"
                f"  Backend root: {BACKEND_ROOT}\n"
                f"  Relative path: {_KEY_RELATIVE_PATH}\n"
                f"Set FIREBASE_KEY_RELATIVE_PATH to override the default location."
            )
        cred = credentials.Certificate(str(_KEY_PATH))
        firebase_admin.initialize_app(cred)


def get_firestore() -> Client:
    """Return the singleton Firestore client. Initialises Firebase on first call."""
    global _db
    if _db is not None:
        return _db
    ensure_firebase_app()
    with _init_lock:
        if _db is None:
            _db = firestore.client()
    return _db
