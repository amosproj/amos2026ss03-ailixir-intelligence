"""
Request-ID propagation.

Every inbound HTTP request gets a unique id, exposed back to the client via the
`X-Request-ID` response header and stored in a `contextvars.ContextVar` so any
log line emitted while handling the request includes it automatically.

Implemented as a pure ASGI middleware rather than Starlette's
`BaseHTTPMiddleware`. `BaseHTTPMiddleware` runs the downstream app in a
separate `asyncio` task, which breaks `ContextVar` inheritance into FastAPI's
exception-handler scope — the symptom in production was `request_id: null` on
500 responses. Pure ASGI wraps the entire request handling chain in one
coroutine, so the contextvar set here is visible everywhere downstream,
including in exception handlers.
"""

import contextvars
import logging
import uuid

from starlette.types import ASGIApp, Receive, Scope, Send


# Empty default so log records emitted outside a request (startup, scheduled
# tasks) still serialize cleanly instead of raising KeyError.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)


_HEADER_NAME = b"x-request-id"


def _generate_request_id() -> str:
    # 16 hex chars is plenty for human grep-ability without bloating log lines.
    return f"req_{uuid.uuid4().hex[:16]}"


def _read_incoming_header(scope: Scope) -> str:
    """Read a client-supplied X-Request-ID from the ASGI scope headers."""
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.lower() == _HEADER_NAME:
            return raw_value.decode("latin-1", errors="ignore").strip()
    return ""


class RequestIDMiddleware:
    """Pure ASGI middleware that sets a per-request `X-Request-ID`.

    Honors a client-supplied id (capped to 64 chars to prevent log injection
    and pathological lengths), else mints one. The id is written into the
    outgoing response headers and held in a `ContextVar` for the lifetime of
    the request.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        incoming = _read_incoming_header(scope)
        request_id = incoming[:64] if incoming else _generate_request_id()

        # FastAPI routes the bare `Exception` / 500 handler through Starlette's
        # ServerErrorMiddleware, which is the *outermost* middleware — outside
        # this one. When an unhandled exception escapes, our `finally` resets
        # the contextvar before that handler runs, so the contextvar is empty
        # by the time the handler builds the response body. ASGI scope state
        # is the right channel here: it survives the entire request lifecycle
        # regardless of middleware structure, and `request.state` reads from
        # it. Set it before any downstream code runs.
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                # Defensively drop any pre-existing header so ours wins.
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != _HEADER_NAME
                ]
                headers.append((_HEADER_NAME, request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send_with_header)
        finally:
            request_id_var.reset(token)


class RequestIDLogFilter(logging.Filter):
    """Inject the current request id into every log record.

    Configure the root logger with this filter and `%(request_id)s` becomes
    available in any log format string.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get("")
        return True
