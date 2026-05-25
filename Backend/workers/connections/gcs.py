"""
Singleton GCS client with helpers for the pipeline.

  download_bytes(gcs_uri)              → (bytes, mime_type)  — fetch document for OCR
  upload_text(content, doc_id, suffix) → gcs_uri             — store Cypher file

Two buckets:
  GCS_DOCUMENTS_BUCKET  — uploaded documents (written by the API, read by workers)
  GCS_CYPHER_BUCKET     — exported Cypher graph files (written by workers, read by frontend)

GOOGLE_APPLICATION_CREDENTIALS — path to service account key (or use Workload Identity on Cloud Run)
"""

from __future__ import annotations

import logging
import os

from google.cloud import storage

_log = logging.getLogger(__name__)
_client: storage.Client | None = None


def get_client() -> storage.Client:
    global _client
    if _client is None:
        _client = storage.Client()
        _log.info("gcs_client_created")
    return _client


def download_bytes(gcs_uri: str) -> tuple[bytes, str]:
    """Download a GCS object by full URI (gs://bucket/path). Returns (bytes, content-type)."""
    bucket_name, blob_name = _parse_uri(gcs_uri)
    blob = get_client().bucket(bucket_name).blob(blob_name)
    mime = blob.content_type or "application/octet-stream"
    data = blob.download_as_bytes()
    _log.info("gcs_download bucket=%s blob=%s bytes=%d", bucket_name, blob_name, len(data))
    return data, mime


def download_document(gcs_object_path: str) -> tuple[bytes, str]:
    """Download a document file from GCS_DOCUMENTS_BUCKET by its object path.

    `gcs_object_path` is the value stored in DocumentFile.gcs_object_path —
    a path relative to the documents bucket (e.g. 'doc_abc/f_xyz.jpg').
    Returns (raw bytes, content-type).
    """
    bucket_name = os.environ["GCS_DOCUMENTS_BUCKET"]
    blob = get_client().bucket(bucket_name).blob(gcs_object_path)
    mime = blob.content_type or "application/octet-stream"
    data = blob.download_as_bytes()
    _log.info("gcs_download_doc bucket=%s path=%s bytes=%d", bucket_name, gcs_object_path, len(data))
    return data, mime


def upload_text(content: str, doc_id: str, suffix: str, folder: str = "graphs") -> str:
    """
    Upload a text file to the Cypher bucket.

    Object path:  {folder}/{doc_id}_{suffix}
    Returns the GCS URI:  gs://{GCS_CYPHER_BUCKET}/{folder}/{doc_id}_{suffix}
    """
    bucket_name = os.environ["GCS_CYPHER_BUCKET"]
    blob_name = f"{folder}/{doc_id}_{suffix}"
    blob = get_client().bucket(bucket_name).blob(blob_name)
    blob.upload_from_string(content, content_type="text/plain; charset=utf-8")
    gcs_uri = f"gs://{bucket_name}/{blob_name}"
    _log.info("gcs_upload blob=%s uri=%s", blob_name, gcs_uri)
    return gcs_uri


def _parse_uri(gcs_uri: str) -> tuple[str, str]:
    """Parse 'gs://bucket/path/to/blob' → ('bucket', 'path/to/blob')."""
    if not gcs_uri.startswith("gs://"):
        raise ValueError(f"Not a valid GCS URI: {gcs_uri!r}")
    without_scheme = gcs_uri[5:]
    bucket, _, blob = without_scheme.partition("/")
    return bucket, blob
