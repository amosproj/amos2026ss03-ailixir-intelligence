import os
from pathlib import Path

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import firebase_admin
from firebase_admin import credentials, auth

# auth.py is inside: Backend/api/auth.py
# Backend root is:   Backend/
BACKEND_ROOT = Path(__file__).resolve().parent.parent

FIREBASE_KEY_RELATIVE_PATH = os.getenv(
    "FIREBASE_KEY_RELATIVE_PATH",
    "shared/keys/amos26-firebase-adminsdk-fbsvc-c05787eb8f.json",
)

FIREBASE_KEY_PATH = BACKEND_ROOT / FIREBASE_KEY_RELATIVE_PATH


if not firebase_admin._apps:
    if not FIREBASE_KEY_PATH.exists():
        raise FileNotFoundError(
            f"Firebase key file not found.\n"
            f"Resolved path: {FIREBASE_KEY_PATH}\n"
            f"auth.py location: {Path(__file__).resolve()}\n"
            f"Backend root: {BACKEND_ROOT}\n"
            f"Relative key path: {FIREBASE_KEY_RELATIVE_PATH}"
        )

    cred = credentials.Certificate(str(FIREBASE_KEY_PATH))
    firebase_admin.initialize_app(cred)


_bearer_scheme = HTTPBearer()


def get_current_user(
    credentials_obj: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    token = credentials_obj.credentials

    try:
        decoded = auth.verify_id_token(token)

    except auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please re-authenticate.",
        )

    except auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled.",
        )

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed.",
        )

    return {
        "uid": decoded["uid"],
        "email": decoded.get("email"),
        "name": decoded.get("name"),
        "email_verified": decoded.get("email_verified", False),
    }
