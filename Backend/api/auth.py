"""
Firebase ID-token authentication for FastAPI endpoints.

Inject `get_current_user` as a dependency on any route that should require a
signed-in user. The function verifies the bearer token against Firebase Auth and
returns the decoded user info, or raises 401 if the token is bad.
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
    those are not auth failures.
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
