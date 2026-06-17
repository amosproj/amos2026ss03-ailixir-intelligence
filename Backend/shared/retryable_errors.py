"""
Single source of truth: which exceptions represent transient remote failures.

`RETRYABLE_PIPELINE_ERRORS` is consumed wherever code needs to decide
"should we retry / let Pub/Sub redeliver / return 503 instead of 500":

  - `workers.main.pubsub_push`            — return 503 → Pub/Sub backoff
  - `workers.pipeline.document_pipeline`  — rollback document to UPLOADED
                                            so the redelivery sees a clean state
  - `api.chat`                            — return 503 so the iOS client can
                                            retry the chat query gracefully
                                            without surfacing a hard error

Keep the tuple narrow. Anything that doesn't represent a transient remote
condition belongs in the terminal path — if we accidentally classify a
genuine logic bug as retryable, the system silently retry-loops forever
and the operator never sees the underlying failure.

Importing this module is cheap and side-effect-free. Optional dependencies
(`google-api-core`, `graphiti-core`) are guarded so the module loads even
in test environments that don't install them.
"""
from __future__ import annotations

# ── Neo4j ─────────────────────────────────────────────────────────────────────
# Aura / self-hosted both expose these. DNS failures, mid-rotation auth,
# pool-stale sessions all recover cleanly on a retry.
from neo4j.exceptions import (
    AuthError as Neo4jAuthError,
    ServiceUnavailable as Neo4jServiceUnavailable,
    SessionExpired as Neo4jSessionExpired,
)

# ── google-api-core ───────────────────────────────────────────────────────────
# Vertex AI (Gemini), GCS, and Firestore all surface their gRPC errors through
# `google.api_core.exceptions`. The four below are the "remote service is
# temporarily unhappy" wrapper types — distinct from permanent errors
# (InvalidArgument, NotFound, PermissionDenied) which must NOT auto-retry.
try:
    from google.api_core.exceptions import (
        DeadlineExceeded,
        InternalServerError as GoogleInternalServerError,
        ResourceExhausted,
        ServiceUnavailable as GoogleServiceUnavailable,
    )
except ImportError:  # pragma: no cover — google-api-core ships with google-cloud-*

    class _GoogleApiCoreUnraisable(BaseException):
        """Placeholder that can never be raised. Catching it is a no-op.

        Used as a fallback when google-api-core isn't installed (test envs
        without GCP deps). Ensures the module loads cleanly and the
        `RETRYABLE_PIPELINE_ERRORS` tuple is still typed correctly.
        """

    DeadlineExceeded = GoogleInternalServerError = ResourceExhausted = GoogleServiceUnavailable = (  # type: ignore[misc, assignment]
        _GoogleApiCoreUnraisable
    )

# ── Graphiti's Gemini wrapper ─────────────────────────────────────────────────
# Graphiti translates Vertex 429s into its own `RateLimitError`. We catch the
# wrapper so rate-limit events fired from inside `add_episode` or `search_`
# stay on the retry path rather than falling through to "FAILED".
try:
    from graphiti_core.llm_client.errors import RateLimitError as GraphitiRateLimitError
except ImportError:  # pragma: no cover

    class _GraphitiUnraisable(BaseException):
        """See _GoogleApiCoreUnraisable. Same pattern for graphiti-core."""

    GraphitiRateLimitError = _GraphitiUnraisable  # type: ignore[misc, assignment]


RETRYABLE_PIPELINE_ERRORS: tuple[type[BaseException], ...] = (
    # ── Neo4j ──────────────────────────────────────────────────────────────
    Neo4jServiceUnavailable,
    Neo4jSessionExpired,
    Neo4jAuthError,
    # ── Generic transport ──────────────────────────────────────────────────
    ConnectionError,            # raw socket-level failures
    TimeoutError,               # asyncio.wait_for timeouts (treat as retryable)
    # ── Vertex AI via google-api-core ──────────────────────────────────────
    ResourceExhausted,          # 429 — quota / rate-limit / concurrency cap
    GoogleServiceUnavailable,   # 503 — upstream blip
    DeadlineExceeded,           # 504 — server-side timeout
    GoogleInternalServerError,  # 500 — Vertex hiccup
    # ── Graphiti's wrappers ────────────────────────────────────────────────
    GraphitiRateLimitError,
)


def is_retryable(exc: BaseException) -> bool:
    """Return True if `exc` is in the retryable-errors set.

    Convenience wrapper for code paths that need a boolean check rather
    than an `except (...)` clause. Mirrors the `except RETRYABLE_PIPELINE_ERRORS`
    semantics so call sites and except clauses always classify consistently.
    """
    return isinstance(exc, RETRYABLE_PIPELINE_ERRORS)
