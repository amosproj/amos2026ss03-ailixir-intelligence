"""
Ailixir Documents + Chat API.

Sync HTTP entrypoint for the mobile client. The API never streams file bytes
through itself — clients receive time-limited signed URLs and upload directly
to GCS. Heavy AI ingestion work happens in the worker service, triggered via
Pub/Sub events the API publishes after finalize.

Chat queries (POST /chat/query) are handled inline here — the three-step
graph-RAG pipeline (contextualize → retrieve → answer) is fast enough to
serve synchronously within Cloud Run's request timeout.

Run from the `Backend/` directory:
    uvicorn api.main:app --reload
"""

import asyncio
import logging
import os
import re
import unicodedata
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from firebase_admin import auth as firebase_auth
from pydantic import BaseModel, EmailStr, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.auth import (
    create_firebase_user,
    delete_firebase_user,
    get_current_user,
)
from api.chat import router as chat_router
from api.errors import (
    APIError,
    api_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from api.middleware import RequestIDLogFilter, RequestIDMiddleware
from shared import gcs, pubsub
from shared.models.document import (
    ALLOWED_FILE_CONTENT_TYPES,
    EXTENSION_BY_CONTENT_TYPE,
    MAX_FILE_SIZE_BYTES,
    MAX_FILES_PER_DOCUMENT,
    MAX_TOTAL_SIZE_BYTES,
    SUPPORTED_DOMAINS,
    Document,
    DocumentFile,
    DocumentStatus,
)
from shared.models.errors import ErrorCode
from shared.models.user import UserProfile
from shared.repositories.documents import (
    DocumentStateError,
    FileCreationSpec,
    create_document_with_files,
    decode_cursor,
    find_document_by_idempotency_key,
    find_document_for_user,
    list_documents_for_user,
    mark_uploaded,
    pending_files,
    soft_delete,
)
from shared.repositories.extractions import get_extraction
from shared.repositories.users import create_user_profile, get_user_profile

load_dotenv()

# Inject request id into every log line. Format is keep-it-simple key=value so
# Cloud Logging parses it reasonably without a custom JSON formatter for v1.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
)
for handler in logging.getLogger().handlers:
    handler.addFilter(RequestIDLogFilter())

_log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: nothing needed — Graphiti initialises lazily on first request
    yield
    # shutdown: close the Neo4j connection held by the chat pipeline
    from api.chat_pipeline.graphiti_client import close_graphiti
    await close_graphiti()


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
    lifespan=lifespan,
)

app.add_middleware(RequestIDMiddleware)

# CORS only matters to browser clients. React Native does not enforce it. The
# middleware is kept so the FastAPI Swagger UI at /docs works during local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

app.include_router(chat_router, prefix="/chat", tags=["Chat"])


# ──────────────────────────────────────────────────────────────────────────────
# Shared validation helpers
# ──────────────────────────────────────────────────────────────────────────────

# Characters we never let into a stored file name. Excludes path separators
# (defence in depth — we don't trust the client name even though the GCS path
# is built server-side from `file_id`), and ASCII control characters.
_INVALID_FILENAME_CHARS = re.compile(r"[\\/:\*\?\"<>\|\x00-\x1f]")


def _sanitize_filename(name: str) -> str:
    """Strip path components, control chars, and unicode lookalikes; cap length."""
    name = os.path.basename(name)
    name = unicodedata.normalize("NFKC", name)
    name = _INVALID_FILENAME_CHARS.sub("", name).strip()
    if not name or name.startswith(".") or name in {".", ".."}:
        raise ValueError("file_name resolves to empty or reserved value")
    return name[:255]


# ──────────────────────────────────────────────────────────────────────────────
# Auth — request / response models
# ──────────────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    """Body for POST /auth/signup. NIST 800-63B password policy: 8 chars min,
    no composition rules. The 128-char cap prevents giant-payload DoS."""

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
    """Client must now sign in via Firebase Auth SDK to obtain an ID token."""

    uid: str
    email: EmailStr
    first_name: str
    last_name: str


# ──────────────────────────────────────────────────────────────────────────────
# Documents — request / response models
# ──────────────────────────────────────────────────────────────────────────────

class CreateDocumentFileRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=512)
    content_type: str
    size_bytes: int = Field(..., gt=0)

    @field_validator("file_name")
    @classmethod
    def _sanitize(cls, value: str) -> str:
        try:
            return _sanitize_filename(value)
        except ValueError as exc:
            raise ValueError(str(exc))

    @field_validator("content_type")
    @classmethod
    def _check_content_type(cls, value: str) -> str:
        if value not in ALLOWED_FILE_CONTENT_TYPES:
            raise ValueError(
                f"unsupported content_type {value!r}; "
                f"allowed: {sorted(ALLOWED_FILE_CONTENT_TYPES)}"
            )
        return value

    @field_validator("size_bytes")
    @classmethod
    def _check_size(cls, value: int) -> int:
        if value > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"size_bytes exceeds per-file limit of {MAX_FILE_SIZE_BYTES} bytes"
            )
        return value


class CreateDocumentRequest(BaseModel):
    domain: str
    title: str | None = Field(default=None, max_length=200)
    files: list[CreateDocumentFileRequest] = Field(..., min_length=1, max_length=MAX_FILES_PER_DOCUMENT)

    @field_validator("domain")
    @classmethod
    def _check_domain(cls, value: str) -> str:
        if value not in SUPPORTED_DOMAINS:
            raise ValueError(
                f"unsupported domain {value!r}; allowed: {sorted(SUPPORTED_DOMAINS)}"
            )
        return value

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class DocumentFileUploadInstruction(BaseModel):
    """Everything the client needs to PUT one file to GCS.

    The signed URL binds method, content type, and size range — the client must
    send these headers exactly or GCS rejects the upload.
    """

    file_id: str
    file_name: str
    content_type: str
    size_bytes: int
    upload_method: str = "PUT"
    upload_url: str
    upload_headers: dict[str, str]
    upload_expires_at: datetime


class CreateDocumentResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    domain: str
    title: str | None
    file_count: int
    total_bytes: int
    files: list[DocumentFileUploadInstruction]
    created_at: datetime


class DocumentFileResponse(BaseModel):
    file_id: str
    file_name: str
    content_type: str
    size_bytes: int
    upload_completed_at: datetime | None
    download_url: str | None
    download_expires_at: datetime | None


class DocumentResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    domain: str
    title: str | None
    file_count: int
    total_bytes: int
    files: list[DocumentFileResponse]
    created_at: datetime
    updated_at: datetime
    finalized_at: datetime | None
    # Worker-written pipeline state. All optional — populated only after the
    # extraction worker has touched the document. Older client builds that
    # don't know about these fields will ignore them.
    #
    # `cypher_gcs_uri` is the raw `gs://` URI; kept for backwards compatibility
    # and tooling that consumes it directly (e.g. backups, debug tooling).
    # `cypher_download_url` is a short-lived v4 signed GET URL the frontend
    # can hit directly to download the .cypher file — mirrors how file
    # downloads work on `DocumentFileResponse`.
    cypher_gcs_uri: str | None = None
    cypher_download_url: str | None = None
    cypher_download_expires_at: datetime | None = None
    # Fine-grained pipeline progress for clients polling during extraction
    # (e.g. "downloading", "ocr", "building_graph"). Free-form today; will
    # be tightened to an enum in a follow-up.
    processing_step: str | None = None
    # Worker error message when `status == failed`. May contain implementation
    # detail (backend names, stack frames). Clients should treat as opaque
    # diagnostic — display a generic failure UI and surface this only to
    # support, alongside the response's `X-Request-ID` header.
    error: str | None = None


class DocumentListItem(BaseModel):
    """List-view summary. No download URLs to keep response size bounded."""

    document_id: str
    status: DocumentStatus
    domain: str
    title: str | None
    file_count: int
    total_bytes: int
    created_at: datetime
    updated_at: datetime
    finalized_at: datetime | None
    thumbnail_url: str | None
    thumbnail_expires_at: datetime | None


class ListDocumentsResponse(BaseModel):
    documents: list[DocumentListItem]
    next_cursor: str | None


class ExtractionResponse(BaseModel):
    """Wire shape for GET /documents/{document_id}/extraction.

    Mirrors the persisted Extraction record minus the internal `uid` field
    (it's enforced by the auth middleware, not surfaced to clients). All
    fields except doc_id/document_type/extracted_at are optional so the
    response loads cleanly for extractions produced by either pipeline:

      - Legacy Document-AI OCR pipeline: populates raw_text, raw_text_chars,
        raw_text_truncated, extracted_fields, confidence_score; LLM fields
        are None.
      - New Gemini-multimodal pipeline: populates document_purpose,
        document_date, episode_body; OCR fields are None.

    Clients should treat both sets as optional and render whichever is
    present. The Extraction model on the persistence side carries the
    same fields, so this transformation is field-for-field.
    """

    doc_id: str
    document_type: str
    # Legacy OCR fields — populated only by the Document-AI pipeline.
    confidence_score: float | None = None
    # `default_factory=dict` — fresh {} per instance. Pydantic v2 deep-copies
    # the bare `= {}` default safely today, but `default_factory` is the
    # documented pattern and avoids surprising future readers. Same shape
    # as the Extraction persistence model.
    extracted_fields: dict = Field(default_factory=dict)
    raw_text: str | None = None
    raw_text_chars: int | None = None
    raw_text_truncated: bool | None = None
    # New LLM fields — populated only by the Gemini-multimodal pipeline.
    # `episode_body` is the rich clinical narrative the LLM produced and is
    # what powers the iOS Document Narrative card; `document_purpose` is a
    # one-sentence role description; `document_date` is YYYY-MM-DD or None.
    document_purpose: str | None = None
    document_date: str | None = None
    episode_body: str | None = None
    extracted_at: datetime


class RefreshUploadURLsResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    files: list[DocumentFileUploadInstruction]


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
)
def signup(payload: SignupRequest) -> SignupResponse:
    """Create a Firebase Auth user and the matching Firestore profile atomically.

    Login itself is NOT a backend endpoint — the mobile client signs in directly
    with the Firebase Auth SDK to obtain an ID token. This endpoint exists only
    to atomically capture the profile fields (first_name, last_name) that
    Firebase Auth does not store.
    """
    display_name = f"{payload.first_name} {payload.last_name}"

    try:
        uid = create_firebase_user(
            email=payload.email,
            password=payload.password,
            display_name=display_name,
        )
    except firebase_auth.EmailAlreadyExistsError:
        raise APIError(
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.EMAIL_ALREADY_EXISTS,
            message="An account with this email already exists.",
        )
    except ValueError as exc:
        _log.warning("firebase_create_user_rejected reason=%s", exc)
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.VALIDATION_FAILED,
            message=str(exc),
        )

    try:
        create_user_profile(
            uid=uid,
            email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
        )
    except Exception as profile_error:
        _log.error("profile_write_failed_compensating uid=%s error=%s", uid, profile_error)
        try:
            delete_firebase_user(uid)
        except Exception as cleanup_error:
            # Orphan Firebase user; reconciliation job picks this up later.
            _log.error("orphan_firebase_user uid=%s cleanup_error=%s", uid, cleanup_error)
        raise APIError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="Signup failed; please retry.",
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
)
def get_me(user: dict = Depends(get_current_user)) -> UserProfile:
    """Return the authenticated user's Firestore profile.

    404 if the profile is missing — typically a user that was created directly
    in Firebase Console without going through /auth/signup.
    """
    profile = get_user_profile(user["uid"])
    if profile is None:
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.USER_PROFILE_NOT_FOUND,
            message="User profile not found. Please complete signup.",
        )
    return profile


# ──────────────────────────────────────────────────────────────────────────────
# Documents — helpers
# ──────────────────────────────────────────────────────────────────────────────

def _upload_headers_for(file: DocumentFile) -> dict[str, str]:
    """Headers the client must send when PUTting to GCS, in addition to the
    body. The signed URL signature includes these — mismatches cause 403."""
    return {
        "Content-Type": file.content_type,
        "x-goog-content-length-range": f"0,{file.size_bytes}",
        "x-goog-if-generation-match": "0",
    }


def _make_upload_instruction(file: DocumentFile) -> DocumentFileUploadInstruction:
    upload_url = gcs.generate_upload_url(
        object_path=file.gcs_object_path,
        content_type=file.content_type,
        max_size_bytes=file.size_bytes,
    )
    return DocumentFileUploadInstruction(
        file_id=file.file_id,
        file_name=file.file_name,
        content_type=file.content_type,
        size_bytes=file.size_bytes,
        upload_url=upload_url,
        upload_headers=_upload_headers_for(file),
        upload_expires_at=datetime.now(timezone.utc) + gcs.DEFAULT_SIGNED_URL_TTL,
    )


def _make_file_response(file: DocumentFile) -> DocumentFileResponse:
    """Build the read-side representation of a file. Download URL only for
    files whose upload completed."""
    download_url: str | None = None
    download_expires_at: datetime | None = None
    if file.upload_completed_at is not None:
        download_url = gcs.generate_download_url(object_path=file.gcs_object_path)
        download_expires_at = datetime.now(timezone.utc) + gcs.DEFAULT_SIGNED_URL_TTL
    return DocumentFileResponse(
        file_id=file.file_id,
        file_name=file.file_name,
        content_type=file.content_type,
        size_bytes=file.size_bytes,
        upload_completed_at=file.upload_completed_at,
        download_url=download_url,
        download_expires_at=download_expires_at,
    )


def _to_document_response(document: Document) -> DocumentResponse:
    # Generate the cypher download URL only when the worker has actually
    # written one — pipelines that failed or never ran won't have a
    # cypher_gcs_uri populated, and we shouldn't fabricate a URL that
    # would 404 on click. The cypher file lives in a different bucket
    # from the documents bucket, so we use the gs:// URI-based signer
    # rather than the documents-bucket-bound one.
    cypher_download_url: str | None = None
    cypher_download_expires_at: datetime | None = None
    if document.cypher_gcs_uri:
        try:
            cypher_download_url = gcs.generate_download_url_for_gs_uri(
                gs_uri=document.cypher_gcs_uri,
                response_content_type="text/plain; charset=utf-8",
                response_disposition=f'attachment; filename="{document.id}_graph.cypher"',
            )
            cypher_download_expires_at = (
                datetime.now(timezone.utc) + gcs.DEFAULT_SIGNED_URL_TTL
            )
        except ValueError:
            # Malformed gs:// URI is a worker bug, not a client problem.
            # Log and serve the response without the signed URL so the
            # rest of the document detail still loads.
            _log.warning(
                "cypher_signed_url_failed document_id=%s gs_uri=%s",
                document.id, document.cypher_gcs_uri,
            )

    return DocumentResponse(
        document_id=document.id,
        status=document.status,
        domain=document.domain,
        title=document.title,
        file_count=document.file_count,
        total_bytes=document.total_bytes,
        files=[_make_file_response(f) for f in document.files],
        created_at=document.created_at,
        updated_at=document.updated_at,
        finalized_at=document.finalized_at,
        cypher_gcs_uri=document.cypher_gcs_uri,
        cypher_download_url=cypher_download_url,
        cypher_download_expires_at=cypher_download_expires_at,
        processing_step=document.processing_step,
        error=document.error,
    )


def _to_list_item(document: Document) -> DocumentListItem:
    """Summary representation. Includes one signed download URL (the first
    completed file) as a thumbnail; full URLs require GET /documents/{id}."""
    first_completed = next((f for f in document.files if f.upload_completed_at), None)
    thumb_url: str | None = None
    thumb_expires: datetime | None = None
    if first_completed is not None:
        thumb_url = gcs.generate_download_url(object_path=first_completed.gcs_object_path)
        thumb_expires = datetime.now(timezone.utc) + gcs.DEFAULT_SIGNED_URL_TTL
    return DocumentListItem(
        document_id=document.id,
        status=document.status,
        domain=document.domain,
        title=document.title,
        file_count=document.file_count,
        total_bytes=document.total_bytes,
        created_at=document.created_at,
        updated_at=document.updated_at,
        finalized_at=document.finalized_at,
        thumbnail_url=thumb_url,
        thumbnail_expires_at=thumb_expires,
    )


def _enforce_total_size(files: list[CreateDocumentFileRequest]) -> None:
    total = sum(f.size_bytes for f in files)
    if total > MAX_TOTAL_SIZE_BYTES:
        raise APIError(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            code=ErrorCode.TOTAL_SIZE_EXCEEDED,
            message=(
                f"declared total of {total} bytes exceeds limit of "
                f"{MAX_TOTAL_SIZE_BYTES} bytes"
            ),
        )


# ──────────────────────────────────────────────────────────────────────────────
# Documents — endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.post(
    "/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateDocumentResponse,
    tags=["Documents"],
    summary="Create a document and obtain upload URLs",
)
def create_document(
    payload: CreateDocumentRequest,
    user: dict = Depends(get_current_user),
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description=(
                "Client-generated unique key. Retries with the same key + same uid "
                "return the original document instead of creating a duplicate. "
                "Stored for 24h."
            ),
            max_length=128,
        ),
    ] = None,
) -> CreateDocumentResponse:
    """Atomically create a Document plus a per-file record for each declared
    file, returning a signed PUT URL for each.

    The client uploads each file directly to GCS using the returned URLs +
    headers, then calls POST /documents/{document_id}/finalize.
    """
    _enforce_total_size(payload.files)

    uid = user["uid"]

    # Idempotency short-circuit: if the same (uid, key) already created a
    # document, return it (with fresh signed URLs for any pending files) rather
    # than creating a duplicate.
    if idempotency_key:
        existing = find_document_by_idempotency_key(uid, idempotency_key)
        if existing is not None:
            return _create_response_from_existing(existing)

    document = create_document_with_files(
        uid=uid,
        domain=payload.domain,
        title=payload.title,
        file_specs=[
            FileCreationSpec(
                file_name=f.file_name,
                content_type=f.content_type,
                size_bytes=f.size_bytes,
            )
            for f in payload.files
        ],
        idempotency_key=idempotency_key,
        # Repository mints the document_id then calls back with it so we can
        # compose the full GCS object path here without knowing the id upfront.
        object_path_builder=lambda *, document_id, file_id, extension: gcs.build_object_path(
            uid=uid,
            document_id=document_id,
            file_id=file_id,
            extension=extension,
        ),
    )

    return CreateDocumentResponse(
        document_id=document.id,
        status=document.status,
        domain=document.domain,
        title=document.title,
        file_count=document.file_count,
        total_bytes=document.total_bytes,
        files=[_make_upload_instruction(f) for f in document.files],
        created_at=document.created_at,
    )


def _create_response_from_existing(document: Document) -> CreateDocumentResponse:
    """For idempotent retries: return the previously-created document with
    fresh signed URLs for any files that have not yet been uploaded."""
    instructions = [
        _make_upload_instruction(f)
        for f in document.files
        if f.upload_completed_at is None
    ]
    return CreateDocumentResponse(
        document_id=document.id,
        status=document.status,
        domain=document.domain,
        title=document.title,
        file_count=document.file_count,
        total_bytes=document.total_bytes,
        files=instructions,
        created_at=document.created_at,
    )


@app.post(
    "/documents/{document_id}/finalize",
    response_model=DocumentResponse,
    tags=["Documents"],
    summary="Finalize a pending document after uploading files to GCS",
)
async def finalize_document(
    document_id: str,
    user: dict = Depends(get_current_user),
) -> DocumentResponse:
    """Verify uploaded files exist in GCS, transition status to `uploaded`, and
    publish a DocumentUploaded event for the worker to pick up."""
    uid = user["uid"]

    document = find_document_for_user(document_id, uid)
    if document is None:
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            message="Document not found.",
        )
    if document.status is not DocumentStatus.PENDING_UPLOAD:
        raise APIError(
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.DOCUMENT_ALREADY_FINALIZED,
            message=f"document is in state {document.status.value}",
        )

    # Verify all files exist in GCS in parallel. Tolerates partial uploads —
    # only the files that actually landed get marked uploaded.
    existence = await asyncio.gather(
        *(gcs.verify_object_exists(f.gcs_object_path) for f in document.files)
    )
    uploaded_ids = [f.file_id for f, ok in zip(document.files, existence) if ok]

    if not uploaded_ids:
        raise APIError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ErrorCode.NO_FILES_UPLOADED,
            message="No files were uploaded to GCS for this document.",
        )

    try:
        document = mark_uploaded(document_id, uid, uploaded_ids)
    except LookupError:
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            message="Document not found.",
        )
    except DocumentStateError as exc:
        raise APIError(
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.DOCUMENT_ALREADY_FINALIZED,
            message=str(exc),
        )

    # Publish AFTER Firestore commit. If publish fails the document is still
    # marked uploaded — a reconciliation job re-publishes stale `uploaded`
    # documents that have no corresponding worker activity within N minutes.
    try:
        pubsub.publish_document_uploaded(document)
    except Exception as exc:
        _log.error(
            "pubsub_publish_failed document_id=%s error=%s",
            document_id, exc,
        )

    return _to_document_response(document)


@app.post(
    "/documents/{document_id}/upload-urls/refresh",
    response_model=RefreshUploadURLsResponse,
    tags=["Documents"],
    summary="Reissue signed URLs for files that have not been uploaded yet",
)
def refresh_upload_urls(
    document_id: str,
    user: dict = Depends(get_current_user),
) -> RefreshUploadURLsResponse:
    """Replace expired signed URLs without losing the document.

    Useful when a long-paused mobile upload outlives the URL TTL. Only files
    without an `upload_completed_at` get fresh URLs; already-uploaded files
    return nothing because they're write-once.
    """
    document = find_document_for_user(document_id, user["uid"])
    if document is None:
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            message="Document not found.",
        )
    if document.status is not DocumentStatus.PENDING_UPLOAD:
        raise APIError(
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.DOCUMENT_ALREADY_FINALIZED,
            message=f"document is in state {document.status.value}",
        )
    return RefreshUploadURLsResponse(
        document_id=document.id,
        status=document.status,
        files=[_make_upload_instruction(f) for f in pending_files(document)],
    )


@app.get(
    "/documents",
    response_model=ListDocumentsResponse,
    tags=["Documents"],
    summary="List the current user's documents (paginated, filterable)",
)
def list_documents(
    user: dict = Depends(get_current_user),
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    domain: str | None = None,
    status_filter: Annotated[DocumentStatus | None, Query(alias="status")] = None,
) -> ListDocumentsResponse:
    """Paginated list of documents newest-first.

    Filters: `domain` (medical, finance, ...), `status` (any DocumentStatus
    value). Cursor is opaque; clients pass back whatever `next_cursor` was
    returned in the previous response.
    """
    if domain is not None and domain not in SUPPORTED_DOMAINS:
        raise APIError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code=ErrorCode.INVALID_DOMAIN,
            message=f"unsupported domain {domain!r}",
        )

    if cursor is not None:
        try:
            decode_cursor(cursor)
        except ValueError:
            raise APIError(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code=ErrorCode.INVALID_PAGINATION_CURSOR,
                message="cursor is malformed",
            )

    documents, next_cursor = list_documents_for_user(
        user["uid"],
        domain=domain,
        status=status_filter,
        limit=limit,
        cursor=cursor,
    )
    return ListDocumentsResponse(
        documents=[_to_list_item(d) for d in documents],
        next_cursor=next_cursor,
    )


@app.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    tags=["Documents"],
    summary="Read a single document, including signed download URLs for files",
)
def get_document(
    document_id: str,
    user: dict = Depends(get_current_user),
) -> DocumentResponse:
    document = find_document_for_user(document_id, user["uid"])
    if document is None:
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            message="Document not found.",
        )
    return _to_document_response(document)


@app.get(
    "/documents/{document_id}/extraction",
    response_model=ExtractionResponse,
    tags=["Documents"],
    summary="Read the OCR extraction record (structured fields + raw text)",
)
def get_document_extraction(
    document_id: str,
    user: dict = Depends(get_current_user),
) -> ExtractionResponse:
    """Return the Extraction record for a document.

    Three failure modes, each with a distinct error code so clients can
    react precisely:

      - 404 DOCUMENT_NOT_FOUND      — document doesn't exist OR isn't owned
                                      by the caller's uid. Same code as the
                                      sibling /documents/{id} endpoint so
                                      enumeration via the extraction route
                                      reveals nothing extra about doc
                                      existence.
      - 409 DOCUMENT_NOT_EXTRACTED  — document exists and is owned by the
                                      caller, but the worker hasn't reached
                                      status=extracted yet. Tells the
                                      client to keep polling /documents/{id}
                                      until status flips.
      - 404 EXTRACTION_NOT_FOUND    — document is marked extracted but no
                                      Extraction record was found. Indicates
                                      a pipeline bug (worker set status
                                      without writing the record); should
                                      page on-call once monitoring exists.
    """
    document = find_document_for_user(document_id, user["uid"])
    if document is None:
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            message="Document not found.",
        )
    if document.status != DocumentStatus.EXTRACTED:
        raise APIError(
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.DOCUMENT_NOT_EXTRACTED,
            message=(
                "Extraction is not yet available for this document. "
                "Poll /documents/{document_id} until status='extracted'."
            ),
        )
    extraction = get_extraction(document_id)
    if extraction is None:
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.EXTRACTION_NOT_FOUND,
            message="No extraction record found for this document.",
        )
    return ExtractionResponse(
        doc_id=extraction.doc_id,
        document_type=extraction.document_type,
        # Legacy OCR fields — pass through as-is. Defaults coerce None when the
        # Extraction came from the new LLM pipeline (which doesn't set them).
        confidence_score=extraction.confidence_score,
        extracted_fields=extraction.extracted_fields,
        raw_text=extraction.raw_text,
        raw_text_chars=extraction.raw_text_chars,
        raw_text_truncated=extraction.raw_text_truncated,
        # New LLM fields — pass through so the iOS Document Narrative card
        # has something to render. Empty for legacy OCR records, populated
        # for documents extracted by the Gemini-multimodal pipeline.
        document_purpose=extraction.document_purpose,
        document_date=extraction.document_date,
        episode_body=extraction.episode_body,
        extracted_at=extraction.extracted_at,
    )


@app.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Documents"],
    summary="Soft-delete a document",
)
def delete_document(
    document_id: str,
    user: dict = Depends(get_current_user),
) -> None:
    """Mark the document as deleted. Refuses if a worker is mid-processing —
    callers should poll until status leaves `processing` before retrying."""
    try:
        soft_delete(document_id, user["uid"])
    except LookupError:
        raise APIError(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            message="Document not found.",
        )
    except DocumentStateError:
        raise APIError(
            status_code=status.HTTP_409_CONFLICT,
            code=ErrorCode.DOCUMENT_IN_PROCESSING,
            message="document is currently being processed; try again shortly",
        )


# ──────────────────────────────────────────────────────────────────────────────
# OpenAPI customisation
# ──────────────────────────────────────────────────────────────────────────────

def custom_openapi():
    """Decorate FastAPI's auto-generated HTTPBearer scheme with description and
    bearer format so Swagger UI's Authorize dialog is useful."""
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
