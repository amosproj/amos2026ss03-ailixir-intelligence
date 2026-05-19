"""
Google Cloud Storage client and signed URL helpers.

The API never streams file bytes through itself. Clients receive time-limited
v4 signed URLs and upload directly to GCS, which keeps the API stateless and
its bandwidth bill bounded.

Two signing modes are supported transparently:

  - Local development: credentials loaded from a service-account JSON key.
    The private key is available in-process, so URLs are signed locally with no
    extra network call.

  - Production on Cloud Run: the service runs as a Google-managed service
    account with no private key. Signing falls back to the IAM Credentials API,
    which requires the service account to hold `iam.serviceAccountTokenCreator`
    on itself (configured in terraform).
"""

import asyncio
import logging
import os
import threading
from datetime import timedelta
from pathlib import Path

import google.auth
from google.auth.credentials import Credentials
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.cloud import storage
from google.oauth2 import service_account


# IAM Credentials' SignBlob endpoint requires this scope. The storage client
# requests narrower devstorage.* scopes for its own calls, so we maintain a
# separate credentials object specifically for v4 URL signing.
_SIGNING_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)

_log = logging.getLogger(__name__)

# Repo layout: Backend/shared/gcs.py → Backend root is two levels up.
BACKEND_ROOT = Path(__file__).resolve().parent.parent

_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "ailixir-documents-amos26")
_KEY_RELATIVE_PATH = os.getenv(
    "FIREBASE_KEY_RELATIVE_PATH",
    "secrets/serviceAccountKey.json",
)
_KEY_PATH = BACKEND_ROOT / _KEY_RELATIVE_PATH

# How long signed URLs (upload + download) remain valid. Short enough to limit
# blast radius if a URL leaks; long enough to tolerate slow mobile networks.
DEFAULT_SIGNED_URL_TTL = timedelta(
    seconds=int(os.getenv("GCS_SIGNED_URL_TTL_SECONDS", "900"))
)

_init_lock = threading.Lock()
_client: storage.Client | None = None
_signing_creds: Credentials | None = None
_signing_init_lock = threading.Lock()


def _init_client() -> storage.Client:
    """Create the GCS client once.

    Three distinct paths matching `shared/firestore.py`:
      - empty env var → Application Default Credentials (Cloud Run path)
      - non-empty + valid file → load JSON key
      - non-empty + missing file → fail loudly (a typo masquerading as ADC
        intent is a real production hazard)
    """
    if not _KEY_RELATIVE_PATH:
        return storage.Client()

    if not _KEY_PATH.is_file():
        raise FileNotFoundError(
            f"Firebase credentials file not found at {_KEY_PATH}.\n"
            f"Set FIREBASE_KEY_RELATIVE_PATH to a valid file, "
            f"or leave it empty to use Application Default Credentials."
        )

    return storage.Client.from_service_account_json(str(_KEY_PATH))


def get_storage_client() -> storage.Client:
    """Return the singleton GCS client. Initialised lazily on first call."""
    global _client
    if _client is not None:
        return _client
    with _init_lock:
        if _client is None:
            _client = _init_client()
    return _client


def get_bucket() -> storage.Bucket:
    return get_storage_client().bucket(_BUCKET_NAME)


def build_object_path(*, uid: str, document_id: str, file_id: str, extension: str) -> str:
    """Compose the canonical GCS object path for a document's file.

    Layout: `users/{uid}/documents/{doc_id}/{file_id}.{ext}`. Per-user prefix
    makes uid-scoped lifecycle policies and bulk deletion trivial.
    """
    return f"users/{uid}/documents/{document_id}/{file_id}.{extension}"


def _get_signing_credentials() -> Credentials:
    """Resolve a credentials object suitable for v4 URL signing.

    Important: the storage client's own credentials are scoped to `devstorage.*`,
    which is sufficient for object operations but NOT for IAM Credentials'
    SignBlob call. Reusing them produces `ACCESS_TOKEN_SCOPE_INSUFFICIENT` 403s
    in production. We maintain a separate credentials object explicitly scoped
    to `cloud-platform` for signing.
    """
    global _signing_creds
    if _signing_creds is not None:
        return _signing_creds
    with _signing_init_lock:
        if _signing_creds is not None:
            return _signing_creds

        if _KEY_RELATIVE_PATH and _KEY_PATH.is_file():
            # JSON service account key: returns service_account.Credentials,
            # which has a local private signer and never needs IAM Credentials.
            _signing_creds = service_account.Credentials.from_service_account_file(
                str(_KEY_PATH),
                scopes=list(_SIGNING_SCOPES),
            )
        else:
            # ADC path (Cloud Run): request the cloud-platform scope explicitly
            # so the metadata-server token can satisfy IAM Credentials.SignBlob.
            creds, _ = google.auth.default(scopes=list(_SIGNING_SCOPES))
            _signing_creds = creds

    return _signing_creds


def _signing_kwargs() -> dict:
    """Return kwargs for `generate_signed_url`.

    Service-account-with-private-key: sign in-process, no kwargs needed.
    Compute-engine ADC: pass `service_account_email` + a freshly-refreshed
    `access_token` so the library uses IAM Credentials' SignBlob.
    """
    creds = _get_signing_credentials()
    if isinstance(creds, service_account.Credentials):
        return {}

    if not creds.valid:
        creds.refresh(GoogleAuthRequest())

    return {
        "service_account_email": creds.service_account_email,
        "access_token": creds.token,
    }


def generate_upload_url(
    *,
    object_path: str,
    content_type: str,
    max_size_bytes: int,
    ttl: timedelta = DEFAULT_SIGNED_URL_TTL,
) -> str:
    """Generate a v4 PUT signed URL bound to a specific object path.

    The returned URL imposes three constraints the client cannot work around:

      - `Content-Type` must match `content_type` exactly.
      - Body size must be within `0..max_size_bytes` (enforced server-side by
        GCS via `x-goog-content-length-range`).
      - The object must not already exist (`x-goog-if-generation-match: 0`).
        This makes the upload effectively write-once and prevents a malicious
        client from overwriting their own document's files after finalize.
    """
    blob = get_bucket().blob(object_path)
    return blob.generate_signed_url(
        version="v4",
        expiration=ttl,
        method="PUT",
        content_type=content_type,
        headers={
            "x-goog-content-length-range": f"0,{max_size_bytes}",
            "x-goog-if-generation-match": "0",
        },
        **_signing_kwargs(),
    )


def generate_download_url(
    *,
    object_path: str,
    ttl: timedelta = DEFAULT_SIGNED_URL_TTL,
) -> str:
    """Generate a v4 GET signed URL for an existing object."""
    blob = get_bucket().blob(object_path)
    return blob.generate_signed_url(
        version="v4",
        expiration=ttl,
        method="GET",
        **_signing_kwargs(),
    )


async def verify_object_exists(object_path: str) -> bool:
    """Async HEAD check on a GCS object.

    Wraps the synchronous `blob.exists()` in a thread so callers can issue
    many checks concurrently via `asyncio.gather`, which is what `finalize`
    relies on for documents with multiple files.
    """
    def _check() -> bool:
        return get_bucket().blob(object_path).exists()
    return await asyncio.to_thread(_check)


def delete_object(object_path: str) -> None:
    """Delete a single object. Idempotent: missing objects return silently."""
    blob = get_bucket().blob(object_path)
    try:
        blob.delete()
    except Exception as exc:
        # The reconciliation job is the authoritative cleaner; the API never
        # blocks user-facing operations on GCS delete success.
        _log.warning("gcs_delete_failed path=%s error=%s", object_path, exc)
