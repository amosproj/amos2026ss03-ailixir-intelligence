from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from auth import get_current_user

app = FastAPI(title="My API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """
    Upload a document.  Only accessible with a valid Firebase ID token.

    `user` is injected automatically and contains:
        user["uid"]   → Firebase user ID  (use as DB key, storage path, etc.)
        user["email"] → e.g. "alice@example.com"
    """
    uid = user["uid"]
    email = user["email"]

    # ── Basic file validation ─────────────────────────────────────────────────
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

    # ── TODO: Logic for uploading Task to pub sub

    return {
        "message": "Document uploaded successfully.",
        "filename": file.filename,
        "size_bytes": len(contents),
        "uploaded_by": {"uid": uid, "email": email},
        "job_id": "12345",
    }


# ── Example: a second protected endpoint showing user info ───────────────────
@app.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    """Returns the authenticated user's profile from the token."""
    return user
