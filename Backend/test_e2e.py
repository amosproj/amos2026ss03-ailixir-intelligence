"""
test_e2e.py -Local end-to-end pipeline test.

Phases:
  1. Create test user (or log in if already exists)
  2. Upload ueberweisungsbrief_e01.pdf via the local API
  3. Finalize the document (marks uploaded in Firestore)
  4. Print document_id + uid
  5. Simulate a Pub/Sub push to the local worker (triggers the full pipeline)

Run from the Backend/ directory:

    # Full flow (upload + trigger):
    python test_e2e.py

    # Skip upload -re-trigger an existing document:
    python test_e2e.py --doc-id <document_id> --uid <uid>

    # Upload only (don't call the worker yet):
    python test_e2e.py --no-trigger

Prerequisites:
  API running   :  uvicorn api.main:app --reload --port 8000
  Worker running:  PUBSUB_SKIP_OIDC_VERIFICATION=1 uvicorn workers.main:app --reload --port 8080
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Config ─────────────────────────────────────────────────────────────────────

API_URL    = os.getenv("API_URL",    "http://localhost:8000")
WORKER_URL = os.getenv("WORKER_URL", "http://localhost:8080")

FIREBASE_API_KEY = "AIzaSyBFdrKtznu96LA48eMqx6xUXqHR_HowY-Y"
_FB_BASE  = "https://identitytoolkit.googleapis.com/v1/accounts"
_SIGNIN_URL  = f"{_FB_BASE}:signInWithPassword?key={FIREBASE_API_KEY}"

# Test user credentials -override via env vars for CI
TEST_EMAIL    = os.getenv("TEST_EMAIL",    "pipeline.test@ailixir.dev")
TEST_PASSWORD = os.getenv("TEST_PASSWORD", "TestPipeline2026!")

# PDF to upload
BACKEND_DIR = Path(__file__).parent
PDF_PATH    = BACKEND_DIR.parent / "ai-playground" / "Patient-1" / "ueberweisungsbrief_e01.pdf"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _h(title: str) -> None:
    print(f"\n{'-' * 64}")
    print(f"  {title}")
    print(f"{'-' * 64}")


# ── Step 1 -Auth ──────────────────────────────────────────────────────────────

def signup_or_login() -> tuple[str, str]:
    """Create user via API (idempotent) + sign in via Firebase REST.

    Returns (uid, id_token).
    """
    _h("STEP 1 - Sign up / Sign in")

    # Create via API (handles Firestore profile creation atomically).
    # 409 = already exists -fall through to sign-in.
    signup = requests.post(
        f"{API_URL}/auth/signup",
        json={
            "email":      TEST_EMAIL,
            "password":   TEST_PASSWORD,
            "first_name": "Pipeline",
            "last_name":  "Test",
        },
        timeout=30,
    )
    if signup.status_code == 201:
        print(f"  ✓ User created via API")
    elif signup.status_code == 409:
        print(f"  ✓ User already exists -signing in")
    else:
        print(f"  ✗ Signup failed  status={signup.status_code}")
        print(f"    {signup.text[:400]}")
        signup.raise_for_status()

    # Firebase REST sign-in gives us the ID token the API accepts.
    signin = requests.post(
        _SIGNIN_URL,
        json={
            "email":              TEST_EMAIL,
            "password":           TEST_PASSWORD,
            "returnSecureToken":  True,
        },
        timeout=30,
    )
    if not signin.ok:
        print(f"  ✗ Firebase sign-in failed  status={signin.status_code}")
        print(f"    {signin.text[:400]}")
        signin.raise_for_status()

    body      = signin.json()
    uid       = body["localId"]
    id_token  = body["idToken"]
    print(f"  ✓ Signed in   uid={uid}")
    print(f"    token[:50] = {id_token[:50]}...")
    return uid, id_token


# ── Step 2 + 3 -Upload ────────────────────────────────────────────────────────

def upload_document(uid: str, id_token: str) -> tuple[str, str]:
    """Create document record, PUT file to GCS, finalize.

    Returns (document_id, domain).
    """
    _h("STEP 2 -Create Document Record")

    file_bytes = PDF_PATH.read_bytes()
    file_size  = len(file_bytes)
    print(f"  File : {PDF_PATH.name}")
    print(f"  Size : {file_size:,} bytes")

    create = requests.post(
        f"{API_URL}/documents",
        json={
            "domain": "medical",
            "title":  "Überweisung -local test",
            "files": [
                {
                    "file_name":    PDF_PATH.name,
                    "content_type": "application/pdf",
                    "size_bytes":   file_size,
                }
            ],
        },
        headers={"Authorization": f"Bearer {id_token}"},
        timeout=30,
    )
    create.raise_for_status()
    doc         = create.json()
    document_id = doc["document_id"]
    domain      = doc["domain"]
    print(f"  ✓ Document record created  document_id={document_id}")

    _h("STEP 3 -Upload File to GCS")
    instr          = doc["files"][0]
    upload_url     = instr["upload_url"]
    upload_headers = instr["upload_headers"]

    print(f"  PUT → {upload_url[:70]}...")
    put = requests.put(
        upload_url,
        data=file_bytes,
        headers=upload_headers,
        timeout=120,
    )
    put.raise_for_status()
    print(f"  ✓ Uploaded  GCS status={put.status_code}")
    return document_id, domain


def finalize(document_id: str, id_token: str) -> str:
    """Finalize document → marks uploaded in Firestore, publishes Pub/Sub in prod."""
    _h("STEP 4 -Finalize Document")
    fin = requests.post(
        f"{API_URL}/documents/{document_id}/finalize",
        headers={"Authorization": f"Bearer {id_token}"},
        timeout=60,
    )
    fin.raise_for_status()
    status = fin.json()["status"]
    print(f"  ✓ Finalized  status={status}")
    return status


# ── Step 5 -Simulate Pub/Sub push ─────────────────────────────────────────────

def trigger_worker(uid: str, document_id: str, domain: str = "medical") -> None:
    """POST a Pub/Sub push envelope directly to the local worker."""
    _h("STEP 5 -Simulate Pub/Sub Push to Worker")

    event = {
        "event_type":     "DocumentUploaded",
        "event_id":       f"evt_{uuid.uuid4().hex}",
        "schema_version": "v1",
        "occurred_at":    datetime.now(timezone.utc).isoformat(),
        "document_id":    document_id,
        "uid":            uid,
        "domain":         domain,
        "file_count":     1,
    }
    data_b64 = base64.b64encode(json.dumps(event, separators=(",", ":")).encode()).decode()

    envelope = {
        "message": {
            "data":        data_b64,
            "messageId":   f"test-{uuid.uuid4().hex[:10]}",
            "publishTime": datetime.now(timezone.utc).isoformat(),
        },
        "subscription":    "projects/amos26/subscriptions/document-uploaded-sub",
        "deliveryAttempt": 1,
    }

    print(f"  POST {WORKER_URL}/pubsub/push")
    print(f"  document_id={document_id}  uid={uid}")
    print(f"  (waiting -pipeline may take 30–120 s)\n")

    try:
        resp = requests.post(
            f"{WORKER_URL}/pubsub/push",
            json=envelope,
            timeout=600,
        )
        if resp.status_code == 204:
            print("  ✓ Worker ACKed (204) -pipeline completed!")
        else:
            print(f"  ✗ Worker returned {resp.status_code}")
            print(f"    {resp.text[:400]}")
    except requests.exceptions.ConnectionError:
        print(f"  ✗ Worker not reachable at {WORKER_URL}")
        _print_worker_start_hint(uid, document_id, domain, data_b64)


def _print_worker_start_hint(
    uid: str, document_id: str, domain: str, data_b64: str
) -> None:
    print()
    print("  -- Start the worker, then re-run with --doc-id + --uid: ------")
    print(f"  cd Backend")
    print(f"  PUBSUB_SKIP_OIDC_VERIFICATION=1 uvicorn workers.main:app --reload --port 8080")
    print()
    print(f"  python test_e2e.py --doc-id {document_id} --uid {uid}")
    print()
    print("  -- Or send the raw envelope with curl: -----------------------")
    # Reconstruct a minimal curl command for convenience
    event = {
        "event_type": "DocumentUploaded",
        "event_id": f"evt_test",
        "schema_version": "v1",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "document_id": document_id,
        "uid": uid,
        "domain": domain,
        "file_count": 1,
    }
    b64 = base64.b64encode(json.dumps(event, separators=(",", ":")).encode()).decode()
    envelope_json = json.dumps({
        "message": {"data": b64, "messageId": "curl-test", "publishTime": datetime.now(timezone.utc).isoformat()},
        "subscription": "projects/amos26/subscriptions/document-uploaded-sub",
        "deliveryAttempt": 1,
    })
    print(f"  curl -s -X POST {WORKER_URL}/pubsub/push \\")
    print(f"       -H 'Content-Type: application/json' \\")
    print(f"       -d '{envelope_json[:120]}...'")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="End-to-end pipeline test")
    parser.add_argument("--doc-id",     help="Skip upload; re-trigger this document")
    parser.add_argument("--uid",        help="uid for --doc-id (required with --doc-id)")
    parser.add_argument("--no-trigger", action="store_true", help="Skip worker trigger step")
    args = parser.parse_args()

    if args.doc_id and not args.uid:
        parser.error("--uid is required when using --doc-id")

    try:
        if args.doc_id:
            # Re-trigger mode: just call the worker with existing document
            document_id = args.doc_id
            uid         = args.uid
            domain      = "medical"
            print(f"\n  Re-trigger mode")
            print(f"  document_id = {document_id}")
            print(f"  uid         = {uid}")
        else:
            if not PDF_PATH.exists():
                print(f"\nERROR: PDF not found at {PDF_PATH}")
                sys.exit(1)

            uid, id_token = signup_or_login()
            document_id, domain = upload_document(uid, id_token)
            finalize(document_id, id_token)

        _h("RESULT")
        print(f"  document_id : {document_id}")
        print(f"  uid         : {uid}")
        print()

        if not args.no_trigger:
            trigger_worker(uid, document_id, domain=domain)
        else:
            print("  (--no-trigger set -skipping worker call)")
            print(f"  To trigger the worker later:")
            print(f"    python test_e2e.py --doc-id {document_id} --uid {uid}")

    except requests.exceptions.ConnectionError:
        print(f"\nERROR: Cannot reach API at {API_URL}")
        print(f"  Make sure the API is running:")
        print(f"    cd Backend && uvicorn api.main:app --reload --port 8000")
        sys.exit(1)
    except requests.exceptions.HTTPError as exc:
        print(f"\nHTTP error: {exc}")
        if exc.response is not None:
            print(f"  Body: {exc.response.text[:600]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
