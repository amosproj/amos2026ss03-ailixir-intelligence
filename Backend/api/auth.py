import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import credentials, auth

_FIREBASE_CRED_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json")

if not firebase_admin._apps:
    cred = credentials.Certificate(_FIREBASE_CRED_PATH)
    firebase_admin.initialize_app(cred)


_bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> dict:
    """
    FastAPI dependency.  Inject with:  user = Depends(get_current_user)

    Verifies the Firebase ID token sent as:
        Authorization: Bearer <firebase_id_token>

    Returns a dict with at minimum:
        {
            "uid":   "firebase_user_id",
            "email": "user@example.com",   # if available
        }

    Raises HTTP 401 on any failure so the endpoint never runs with a bad token.
    """
    token = credentials.credentials
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
            detail="Invalid token.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
        )

    return {
        "uid": decoded["uid"],
        "email": decoded.get("email"),
        "name": decoded.get("name"),
        "email_verified": decoded.get("email_verified", False),
    }
