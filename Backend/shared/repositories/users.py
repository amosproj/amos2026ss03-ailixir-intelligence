"""
Repository for the `users` Firestore collection.

Each document is keyed by Firebase UID so the profile and the Firebase Auth
record share an identifier. Callers go through these functions instead of
touching Firestore directly; this is the seam where caching or a fake
implementation for tests would slot in.
"""

import logging
from datetime import datetime, timezone

from firebase_admin import firestore

from shared.firestore import get_firestore
from shared.models.user import UserProfile

_log = logging.getLogger(__name__)
_COLLECTION = "users"


def create_user_profile(
    *,
    uid: str,
    email: str,
    first_name: str,
    last_name: str,
) -> UserProfile:
    """Persist a new user profile, keyed by Firebase UID.

    The returned object uses client-side timestamps as a best-effort approximation;
    the canonical values written to Firestore are SERVER_TIMESTAMP and may differ
    by up to a few hundred milliseconds.
    """
    db = get_firestore()
    now = datetime.now(timezone.utc)

    db.collection(_COLLECTION).document(uid).set(
        {
            "uid": uid,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
    )

    _log.info("user_profile_created uid=%s", uid)

    return UserProfile(
        uid=uid,
        email=email,
        first_name=first_name,
        last_name=last_name,
        created_at=now,
        updated_at=now,
    )


def get_user_profile(uid: str) -> UserProfile | None:
    """Fetch a user profile by Firebase UID. Returns None if not found."""
    db = get_firestore()
    snapshot = db.collection(_COLLECTION).document(uid).get()
    if not snapshot.exists:
        return None
    return UserProfile(**snapshot.to_dict())
