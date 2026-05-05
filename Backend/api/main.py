"""
Ailixir Documents API.

Sync HTTP entrypoint for the mobile client. The endpoints here are tuned for low
latency: heavy work (OCR, LLM extraction, embedding) lives in the worker services
and is reached asynchronously via Pub/Sub.

Run from the `Backend/` directory:
    uvicorn api.main:app --reload
"""

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

from api.auth import get_current_user
from shared.models.document import DocumentStatus
from shared.repositories.documents import create_document

app = FastAPI(
    title="Document Processing API",
    version="1.0.0",
    description="""
## API end points for ALIXIR Intelligence
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


class UploadDocumentResponse(BaseModel):
    document_id: str
    status: DocumentStatus
    file_name: str
    size_bytes: int


_ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png", "text/plain"}
_MAX_SIZE_BYTES = 10 * 1024 * 1024


@app.get(
    "/health",
    tags=["System"],
    summary="Health Check",
    response_description="API is running",
)
def health() -> dict:
    return {"status": "ok"}


@app.get(
    "/me",
    tags=["Auth"],
    summary="Get current user",
    response_description="Decoded Firebase token claims",
    responses={
        200: {"description": "User profile from Firebase token"},
        401: {"description": "Missing or invalid Firebase token"},
    },
)
def get_me(user: dict = Depends(get_current_user)) -> dict:
    """Return the authenticated user's profile derived from their Firebase token.

    Useful for verifying auth is working end-to-end.
    """
    return user


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


# FastAPI auto-generates an OpenAPI schema. We patch it here to inject the HTTP
# Bearer security scheme so the Swagger UI at /docs shows an "Authorize" button.
# Without this, devs have to paste tokens into curl manually for every request.
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Paste your Firebase ID token (without the 'Bearer ' prefix)",
        }
    }
    schema["security"] = [{"BearerAuth": []}]

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi
