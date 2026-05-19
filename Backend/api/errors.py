"""
Exception types and handlers that emit structured error responses.

Every error response carries a stable `code` so mobile clients can switch on
it without parsing message strings, plus the `request_id` so support can
trace a complaint to exact log lines.
"""

import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.middleware import request_id_var
from shared.models.errors import ErrorCode, ErrorDetail, ErrorResponse

_log = logging.getLogger(__name__)


class APIError(HTTPException):
    """Domain-specific HTTP error carrying a stable `ErrorCode`."""

    def __init__(self, status_code: int, code: ErrorCode, message: str):
        super().__init__(status_code=status_code, detail=message)
        self.code = code


def _envelope(code: ErrorCode, message: str) -> dict:
    """Build the structured error body. Reads the request id from the
    contextvar — the pure-ASGI middleware in `api/middleware.py` guarantees
    propagation through the exception-handler scope."""
    return ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            request_id=request_id_var.get("") or None,
        )
    ).model_dump()


async def api_error_handler(_: Request, exc: APIError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=_envelope(exc.code, exc.detail))


async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Wrap FastAPI/Starlette's built-in HTTPExceptions into our envelope.

    Covers things like the 403 emitted by `HTTPBearer` when the Authorization
    header is missing entirely. Domain errors flow through `APIError` and its
    dedicated handler, so the mapping here is intentionally narrow.
    """
    code = {
        401: ErrorCode.UNAUTHENTICATED,
        403: ErrorCode.UNAUTHENTICATED,
    }.get(exc.status_code, ErrorCode.INTERNAL_SERVER_ERROR)
    message = exc.detail if isinstance(exc.detail, str) else "request failed"
    return JSONResponse(status_code=exc.status_code, content=_envelope(code, message))


async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Flatten Pydantic's structured errors into a single human-readable message.

    Surfaces up to three field errors — enough for the client to fix one
    request without dumping a wall of text on the user.
    """
    parts = []
    for err in exc.errors()[:3]:
        loc = ".".join(str(x) for x in err.get("loc", ()) if x != "body")
        parts.append(f"{loc}: {err['msg']}" if loc else err["msg"])
    message = "; ".join(parts) or "validation failed"
    return JSONResponse(status_code=422, content=_envelope(ErrorCode.VALIDATION_FAILED, message))


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler. Logs the full stack server-side; client gets only
    the generic code plus the request id for tracing."""
    _log.exception("unhandled_exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content=_envelope(ErrorCode.INTERNAL_SERVER_ERROR, "An internal error occurred."),
    )
