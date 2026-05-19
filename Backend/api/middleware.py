"""
Request-ID propagation.

Every inbound request gets a unique id, exposed back to the client via the
`X-Request-ID` response header and stored in a `contextvars.ContextVar` so any
log line emitted while handling the request includes it automatically.

This is the seam that turns a user complaint ("upload failed at 14:23") into
exact log lines: client gets the request id in the response, sends it to
support, support greps the logs for it.
"""

import contextvars
import logging
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


# Empty default so log records emitted outside a request (startup, scheduled
# tasks) still serialize cleanly instead of raising KeyError.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)


_HEADER = "X-Request-ID"


def _generate_request_id() -> str:
    # 16 hex chars is plenty for human grep-ability without bloating log lines.
    return f"req_{uuid.uuid4().hex[:16]}"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Honor a client-supplied request id when present, else mint a new one.

    A client sending its own id lets the mobile app correlate a network call
    on its side with the matching server-side trace.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(_HEADER, "").strip()
        # Cap user-supplied ids to avoid log injection / pathological lengths.
        request_id = incoming[:64] if incoming else _generate_request_id()

        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)

        response.headers[_HEADER] = request_id
        return response


class RequestIDLogFilter(logging.Filter):
    """Inject the current request id into every log record.

    Configure the root logger with this filter and `%(request_id)s` becomes
    available in any log format string.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("")
        return True
