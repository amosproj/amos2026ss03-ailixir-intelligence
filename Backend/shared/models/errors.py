"""
Structured error responses for the API.

Every HTTP error the API returns carries a stable `code` (suitable for client
switch statements), a human-readable `message`, and the originating `request_id`
so support requests can be traced back to exact log lines.
"""

from enum import Enum

from pydantic import BaseModel


class ErrorCode(str, Enum):
    # Generic
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    VALIDATION_FAILED = "VALIDATION_FAILED"

    # Auth
    UNAUTHENTICATED = "UNAUTHENTICATED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_REVOKED = "TOKEN_REVOKED"
    INVALID_TOKEN = "INVALID_TOKEN"
    USER_DISABLED = "USER_DISABLED"

    # Users
    USER_PROFILE_NOT_FOUND = "USER_PROFILE_NOT_FOUND"
    EMAIL_ALREADY_EXISTS = "EMAIL_ALREADY_EXISTS"

    # Documents
    DOCUMENT_NOT_FOUND = "DOCUMENT_NOT_FOUND"
    DOCUMENT_ALREADY_FINALIZED = "DOCUMENT_ALREADY_FINALIZED"
    DOCUMENT_IN_PROCESSING = "DOCUMENT_IN_PROCESSING"
    DOCUMENT_NOT_EXTRACTED = "DOCUMENT_NOT_EXTRACTED"
    EXTRACTION_NOT_FOUND = "EXTRACTION_NOT_FOUND"
    NO_FILES_UPLOADED = "NO_FILES_UPLOADED"
    INVALID_DOMAIN = "INVALID_DOMAIN"
    INVALID_FILE_TYPE = "INVALID_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    TOTAL_SIZE_EXCEEDED = "TOTAL_SIZE_EXCEEDED"
    TOO_MANY_FILES = "TOO_MANY_FILES"
    INVALID_FILE_NAME = "INVALID_FILE_NAME"
    IDEMPOTENCY_KEY_REQUIRED = "IDEMPOTENCY_KEY_REQUIRED"
    INVALID_PAGINATION_CURSOR = "INVALID_PAGINATION_CURSOR"


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
