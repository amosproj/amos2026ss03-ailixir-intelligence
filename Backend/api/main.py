from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from auth import get_current_user

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/health",
    tags=["System"],
    summary="Health Check",
    response_description="API is running",
)
def health():
    return {"status": "ok"}


@app.post(
    "/documents/upload",
    status_code=status.HTTP_201_CREATED,
    tags=["Documents"],
    summary="Upload a document",
    response_description="Upload confirmation with job ID",
    responses={
        201: {"description": "Document uploaded and queued successfully"},
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
):
    """
    Upload a document for processing.

    - Validates file type and size
    - Queues a processing job in Pub/Sub (TODO)
    - Returns a job ID to poll for results

    **Requires:** `Authorization: Bearer <firebase_id_token>`
    """
    uid = user["uid"]
    email = user["email"]

    ALLOWED_TYPES = {"application/pdf", "image/jpeg", "image/png", "text/plain"}
    MAX_SIZE_MB = 10

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{file.content_type}' is not allowed.",
        )

    contents = await file.read()
    if len(contents) > MAX_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_SIZE_MB} MB limit.",
        )

    # TODO: publish to Pub/Sub

    return {
        "message": "Document uploaded successfully.",
        "filename": file.filename,
        "size_bytes": len(contents),
        "uploaded_by": {"uid": uid, "email": email},
        "job_id": "12345",
    }


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
def get_me(user: dict = Depends(get_current_user)):
    """
    Returns the authenticated user's profile decoded from their Firebase token.

    Useful for verifying auth is working end-to-end.

    **Requires:** `Authorization: Bearer <firebase_id_token>`
    """
    return user


# FastAPI auto-generates a schema, but we patch it here to inject the
# HTTP Bearer security scheme so Swagger UI shows the Authorize button.
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Teach Swagger UI that this API uses Bearer tokens
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Paste your Firebase ID token (without the 'Bearer ' prefix)",
        }
    }

    # Apply globally — every endpoint gets the lock icon
    schema["security"] = [{"BearerAuth": []}]

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi
