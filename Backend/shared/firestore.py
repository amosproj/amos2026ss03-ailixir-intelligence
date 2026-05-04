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

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import Client

_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID", "amos26-7b955")
_CRED_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "api/serviceAccountKey.json")

_init_lock = threading.Lock()
_db: Client | None = None


def _emulator_mode() -> bool:
    return bool(
        os.getenv("FIRESTORE_EMULATOR_HOST")
        or os.getenv("FIREBASE_AUTH_EMULATOR_HOST")
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
        else:
            cred = credentials.Certificate(_CRED_PATH)
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
