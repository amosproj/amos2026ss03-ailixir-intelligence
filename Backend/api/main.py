"""
Ailixir Documents API.

Sync HTTP entrypoint for the mobile client. The endpoints here are tuned for low
latency: heavy work (OCR, LLM extraction, embedding) lives in the worker services
and is reached asynchronously via Pub/Sub.

Run from the `Backend/` directory:
    uvicorn api.main:app --reload
"""

import logging

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from firebase_admin import auth as firebase_auth
from pydantic import BaseModel, EmailStr, Field, field_validator

from api.auth import (
    create_firebase_user,
    delete_firebase_user,
    get_current_user,
)
from shared.models.document import DocumentStatus
from shared.models.user import UserProfile
from shared.repositories.documents import create_document
from shared.repositories.users import create_user_profile, get_user_profile

load_dotenv()

_log = logging.getLogger(__name__)

app = FastAPI(
    title="Document Processing API",
    version="1.0.0",
    description="""
## API endpoints for Ailixir Intelligence
""",
    contact={
        "name": "Hasnat Ahmed",
        "email": "hasnatahmed331@gmail.com",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS only matters to browser clients. React Native does not enforce it. The
# middleware is kept so the FastAPI Swagger UI at /docs works during local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────────────────
# Request / response models
# ──────────────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    """Body for POST /auth/signup.

    Password length follows NIST 800-63B: at least 8 characters, no composition
    rules. The 128-character cap exists to prevent denial-of-service via giant
    payloads — Firebase Auth itself accepts much longer strings.
    """

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)

    @field_validator("first_name", "last_name")
    @classmethod
    def _strip_and_reject_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty or whitespace-only")
        return stripped


class SignupResponse(BaseModel):
    """Returned on successful signup. The client must call Firebase Auth SDK with
    the same email + password to obtain an ID token for subsequent API calls."""

    uid: str
    email: EmailStr
    first_name: str
    last_name: str


class UploadDocumentResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    file_name: str
    size_bytes: int


_ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png", "text/plain"}
_MAX_SIZE_BYTES = 10 * 1024 * 1024


# ──────────────────────────────────────────────────────────────────────────────
# System
# ──────────────────────────────────────────────────────────────────────────────

@app.get(
    "/health",
    tags=["System"],
    summary="Health Check",
    response_description="API is running",
)
def health() -> dict:
    return {"status": "ok"}


# ──────────────────────────────────────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────────────────────────────────────

@app.post(
    "/auth/signup",
    status_code=status.HTTP_201_CREATED,
    response_model=SignupResponse,
    tags=["Auth"],
    summary="Create a new user account",
    response_description="Account created; client must now sign in via Firebase Auth SDK",
    responses={
        201: {"description": "Signup successful"},
        400: {"description": "Inputs rejected by Firebase Admin SDK"},
        409: {"description": "An account with this email already exists"},
        422: {"description": "Request body failed validation (email/password/name rules)"},
    },
)
def signup(payload: SignupRequest) -> SignupResponse:
    """Create a Firebase Auth user and the matching Firestore profile atomically.

    Login itself is NOT a backend endpoint — the mobile client signs in directly
    with the Firebase Auth SDK to obtain an ID token. This endpoint exists only
    to atomically capture the profile fields (first_name, last_name) that
    Firebase Auth does not store.

    Atomicity is best-effort: if the Firestore write fails after the Firebase
    Auth record is created, we delete the Firebase user to compensate. A real
    distributed transaction across the two systems is not possible, so a
    background reconciliation job will eventually be needed for production.
    """
    display_name = f"{payload.first_name} {payload.last_name}"

    try:
        uid = create_firebase_user(
            email=payload.email,
            password=payload.password,
            display_name=display_name,
        )
    except firebase_auth.EmailAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )
    except ValueError as exc:
        # Firebase Admin SDK raises ValueError for inputs that pass our Pydantic
        # gate but fail its own rules. Surface the reason as a 400 so the client
        # can show it to the user.
        _log.warning("firebase_create_user_rejected reason=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    try:
        create_user_profile(
            uid=uid,
            email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
        )
    except Exception as profile_error:
        # Compensation: roll back the Firebase user so the system never holds an
        # auth record without a matching profile. If cleanup itself fails we log
        # the orphan for offline reconciliation and still return 500 to the
        # client — the original error is what they need to act on.
        _log.error(
            "profile_write_failed_compensating uid=%s error=%s",
            uid, profile_error,
        )
        try:
            delete_firebase_user(uid)
        except Exception as cleanup_error:
            # TODO(orphan-cleanup): production needs a periodic job that scans
            # Firebase Auth for users with no Firestore profile and either
            # provisions a profile (if recoverable) or deletes the user.
            _log.error(
                "orphan_firebase_user uid=%s cleanup_error=%s",
                uid, cleanup_error,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Signup failed; please retry.",
        )

    _log.info("signup_succeeded uid=%s", uid)

    return SignupResponse(
        uid=uid,
        email=payload.email,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )


@app.get(
    "/me",
    response_model=UserProfile,
    tags=["Auth"],
    summary="Get current user profile",
    response_description="Profile from Firestore, keyed by the authenticated Firebase UID",
    responses={
        200: {"description": "Profile returned"},
        401: {"description": "Missing or invalid Firebase token"},
        404: {"description": "Profile not found — user must complete signup via /auth/signup"},
    },
)
def get_me(user: dict = Depends(get_current_user)) -> UserProfile:
    """Return the authenticated user's profile.

    A 404 here typically means the user was created directly in the Firebase
    Console without going through /auth/signup — there's an Auth record but no
    profile. The fix is to delete the Auth record and have the user sign up
    properly through the API.
    """
    profile = get_user_profile(user["uid"])
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found. Please complete signup.",
        )
    return profile


# ──────────────────────────────────────────────────────────────────────────────
# Documents
# ──────────────────────────────────────────────────────────────────────────────

@app.post(
    "/documents/upload",
    status_code=status.HTTP_201_CREATED,
    response_model=UploadDocumentResponse,
    tags=["Documents"],
    summary="Upload a document",
    response_description="Document tracking record created",
    responses={
        201: {"description": "Document accepted; tracking record created in Firestore"},
        401: {"description": "Missing or invalid Firebase token"},
        413: {"description": "File exceeds 10 MB size limit"},
        415: {"description": "Unsupported file type"},
    },
)
async def upload_document(
    file: UploadFile = File(
        ..., description="PDF, JPEG, PNG, or plain text. Max 10 MB."
    ),
    user: dict = Depends(get_current_user),
) -> UploadDocumentResponse:
    """Accept a document upload and create a tracking record in Firestore.

    The bytes are not yet persisted to GCS — that is a follow-up step. A Firestore
    document is created in PENDING_UPLOAD state so the rest of the pipeline (and
    the mobile client) has a stable id to refer to.
    """
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{file.content_type}' is not allowed.",
        )

    # TODO(streaming): reading the entire body into memory is not safe for
    # large uploads. Switch to a streaming size validator before raising the
    # 10 MB cap.
    contents = await file.read()
    if len(contents) > _MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {_MAX_SIZE_BYTES // (1024 * 1024)} MB limit.",
        )

    # TODO(idempotency): a client retry will create duplicate records. Wire an
    # Idempotency-Key header from mobile and dedupe on it before this insert.
    # TODO(domain): currently hardcoded; pull from the request body once mobile
    # sends it. Domain-configurability is the load-bearing requirement of the project.
    document = create_document(
        uid=user["uid"],
        file_name=file.filename or "unknown",
        content_type=file.content_type,
        size_bytes=len(contents),
        domain="medical",
    )

    # TODO(gcs): upload bytes to GCS and update the Firestore record with
    # gcs_uri + status=UPLOADED.
    # TODO(pubsub): publish a DocumentUploaded event so the ingestion worker
    # can pick this up.

    return UploadDocumentResponse(
        document_id=document.id,
        status=document.status,
        file_name=document.file_name,
        size_bytes=document.size_bytes,
    )


# ──────────────────────────────────────────────────────────────────────────────
# OpenAPI customisation
# ──────────────────────────────────────────────────────────────────────────────

# FastAPI auto-generates an OpenAPI schema and emits a `HTTPBearer` security scheme
# whenever a route uses `Depends(HTTPBearer())` — which `get_current_user` does.
# We just decorate the auto-generated entry with `bearerFormat` and a description so
# the Swagger UI Authorize dialog shows useful guidance. Replacing the scheme outright
# would break the per-endpoint `security` references FastAPI already wired up.
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    schemes = schema.get("components", {}).get("securitySchemes", {})
    if "HTTPBearer" in schemes:
        schemes["HTTPBearer"]["bearerFormat"] = "JWT"
        schemes["HTTPBearer"]["description"] = (
            "Paste your Firebase ID token (without the 'Bearer ' prefix)"
        )

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi
