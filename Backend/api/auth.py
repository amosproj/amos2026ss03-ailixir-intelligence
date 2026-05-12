"""
Firebase identity operations for the API service.

Two distinct responsibilities live here:

1. Token verification — `get_current_user` is the FastAPI dependency that turns
   an `Authorization: Bearer <id_token>` header into a decoded user dict.
2. User administration — `create_firebase_user` / `delete_firebase_user` wrap
   the Firebase Admin SDK calls used during signup. Keeping these as thin
   wrappers gives us one place to log, transform, or replace the underlying
   call without touching every caller.

Credential loading and Firebase app initialisation live in `shared/firestore.py`
so the API and workers go through one place.
"""

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth

from shared.firestore import ensure_firebase_app

_log = logging.getLogger(__name__)
_bearer_scheme = HTTPBearer()


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """Verify a Firebase ID token and return the decoded user info.

    Returns a dict with `uid` and optionally `email`, `name`, and `email_verified`.
    Raises HTTP 401 on any token-level failure. Infrastructure errors (e.g. unable
    to reach Google's certificate endpoint) propagate as 500, which is correct —
    those are not auth failures and the client retrying the same token won't help.
    """
    ensure_firebase_app()

    try:
        decoded = auth.verify_id_token(creds.credentials)
    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please re-authenticate.",
        )
    except auth.RevokedIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked.",
        )
    except auth.UserDisabledError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled.",
        )
    except (auth.InvalidIdTokenError, ValueError) as e:
        # Generic message to the client; full reason logged server-side so we can
        # debug invalid tokens without leaking auth internals to attackers.
        _log.warning("invalid_id_token: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token.",
        )

    return {
        "uid": decoded["uid"],
        "email": decoded.get("email"),
        "name": decoded.get("name"),
        "email_verified": decoded.get("email_verified", False),
    }


def create_firebase_user(
    *,
    email: str,
    password: str,
    display_name: str,
) -> str:
    """Create a Firebase Auth user and return their UID.

    Re-raises `firebase_admin.auth.EmailAlreadyExistsError` so the caller can map
    it to an HTTP 409, and `ValueError` for inputs that pass our Pydantic gates
    but fail the Admin SDK's own rules (e.g. password edge cases). Any other
    exception bubbles up as a 500.
    """
    ensure_firebase_app()
    record = auth.create_user(
        email=email,
        password=password,
        display_name=display_name,
    )
    _log.info("firebase_user_created uid=%s", record.uid)
    return record.uid


def delete_firebase_user(uid: str) -> None:
    """Delete a Firebase Auth user.

    Used as the compensating action when a signup writes the Auth record but
    fails to write the Firestore profile. Best-effort: callers should catch and
    log failures rather than re-raise, since the original error is what we want
    to surface to the client.
    """
    ensure_firebase_app()
    auth.delete_user(uid)
    _log.info("firebase_user_deleted uid=%s", uid)
