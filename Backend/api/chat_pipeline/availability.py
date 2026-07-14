"""
Source availability — graceful degradation for the two retrieval arms.

The chat pipeline reads from two independent stores:

  - Neo4j, via Graphiti — the patient's knowledge graph   (retriever.py)
  - AstraDB             — the research-paper vector store (paper_retriever.py)

Either can be ABSENT (env vars never configured — a fresh dev checkout, a
staging deploy with only one store provisioned) or DOWN (outage, rotated
credentials, network partition). Neither may fail the user's request. The
pipeline answers from whichever sources are reachable and states, in the
answer itself, which ones were not — a user who asks about their lab results
during a Neo4j outage must be told "I couldn't reach your records", never
shown a bare 503 and never told "you have no lab results".

Two mechanisms make that cheap:

`missing_env_vars` — "does this store even exist?"
    Unset env vars are a permanent condition that costs a dict lookup to
    detect. Checking up front beats letting `os.environ[...]` raise a KeyError
    from inside a client constructor: an unconfigured store then costs nothing
    instead of a connect timeout, and "never configured" stays distinguishable
    from "configured but unreachable" in the logs.

`CircuitBreaker` — "is this store currently down?"
    Once a store fails, every subsequent request would pay the same connect
    timeout (up to `CHAT_RETRIEVE_TIMEOUT_S`, 15s, for Neo4j). Instead the arm
    is latched out for `_COOLDOWN_S` and skipped outright, then re-probed once
    the cooldown lapses. Recovery is automatic and needs no half-open state or
    success threshold: one successful search is proof the store is back, and
    the cost of an occasional wasted probe is one request's retrieval latency,
    not correctness.

The breakers are per-process, in-memory, and deliberately not shared across
Cloud Run instances. A cross-instance breaker would need a coordination store
(itself a dependency that can be down) to save, at most, one probe per instance
per cooldown window.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Sequence

_log = logging.getLogger(__name__)

# How long an arm stays latched out after a failure before it is re-probed.
# 60s trades a little staleness (a store that recovers is ignored for up to a
# minute) for not hammering a dead dependency on every request.
_COOLDOWN_S = float(os.environ.get("CHAT_UNAVAILABLE_COOLDOWN_S", "60.0"))


class CircuitBreaker:
    """Per-store "we know it's down, skip it" latch with an automatic re-probe.

    Not thread-safe by design — the pipeline is single-event-loop async, and a
    torn read here costs one redundant probe, which is exactly what the breaker
    is allowed to cost anyway.
    """

    def __init__(self, name: str, cooldown_s: float = _COOLDOWN_S) -> None:
        self._name = name
        self._cooldown_s = cooldown_s
        self._open_until = 0.0
        self._reason = f"{name} is unavailable"

    @property
    def reason(self) -> str:
        """Why the store was last considered unavailable. User-safe (see `failure_reason`)."""
        return self._reason

    def is_open(self) -> bool:
        """True while the store is latched out. Closes itself when the cooldown lapses."""
        return time.monotonic() < self._open_until

    def trip(self, reason: str) -> None:
        """Latch the store out for the cooldown window."""
        self._reason = reason
        self._open_until = time.monotonic() + self._cooldown_s
        _log.warning(
            "circuit_open source=%s cooldown_s=%.0f reason=%s",
            self._name, self._cooldown_s, reason,
        )

    def reset(self) -> None:
        """Mark the store healthy again. Called after any successful read."""
        if self._open_until:
            _log.info("circuit_closed source=%s", self._name)
        self._open_until = 0.0


def missing_env_vars(required: Sequence[str]) -> list[str]:
    """Names of the required env vars that are unset or empty.

    An empty string counts as missing: a Cloud Run service with an env var
    declared but bound to an empty secret is not configured, and letting `""`
    through just moves the failure to a confusing connect error later.
    """
    return [name for name in required if not os.environ.get(name)]


# ── Failure classification ────────────────────────────────────────────────────
#
# Two questions are asked of every failure, and they have DIFFERENT answers:
#
#   "What do we tell the user?"  -> failure_reason()
#   "Do we latch the arm out?"   -> should_trip()
#
# Conflating them was a real bug. The breaker used to latch on *any* exception,
# so a single user's Vertex 429 on the query embedding took the knowledge graph
# away from EVERY user for a full minute — even though a 429 means the store is
# healthy and busy, and the very next request would likely have succeeded.
#
# The breaker exists for one purpose: to stop us re-paying an EXPENSIVE timeout
# against a store that is genuinely down. So it latches only on evidence the
# store itself is unusable. A rate limit or a one-off bug fails fast and cheap;
# retrying it costs a few milliseconds, while latching it out costs every user
# their records for 60 seconds. Cheap-and-wrong beats expensive-and-wrong here.

_RATE_LIMIT_NAMES = frozenset({"ResourceExhausted", "RateLimitError", "TooManyRequests"})
_AUTH_NAMES = frozenset({
    "AuthError", "Unauthorized", "AuthenticationException",
    "PermissionDenied", "Forbidden", "Unauthenticated",
})
_UNREACHABLE_NAMES = frozenset({
    "ServiceUnavailable", "SessionExpired", "ConnectionError",
    "ConnectionRefusedError", "ConnectionResetError", "DatabaseError",
    "TransientError", "Neo4jError", "ServerError", "OSError", "gaierror",
})
_CONFIG_NAMES = frozenset({
    "ConfigurationError", "KeyError", "InvalidArgument", "NotFound",
})


def _status_code(exc: BaseException) -> int | None:
    """HTTP/gRPC status carried by the exception, if it has one.

    Vertex's `google.genai.ClientError` is a GENERIC 4xx wrapper — a 429, a 403
    and a 400 all arrive under that one class name. Matching on the name alone
    would file a rate limit under "unreachable" and trip the breaker, which is
    exactly the bug this classification exists to prevent. So the code wins over
    the name wherever one is present.
    """
    for attr in ("code", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None


# OpenAI slugs that mean "the account is out of money", not "you are going too
# fast". Both arrive as an HTTP 429 / RateLimitError, which is why they need
# catching BEFORE the status-code check: a transient 429 must not latch the
# breaker, but an exhausted quota must — it will never recover on its own, and
# re-attempting it costs a multi-second OpenAI round-trip on EVERY request
# (measured: 3.6s, then 2.1s, against a real out-of-credit key).
_QUOTA_SLUGS = frozenset({"insufficient_quota", "billing_hard_limit_reached"})


def classify(exc: BaseException) -> str:
    """Bucket a failure.

    Returns one of: timeout | rate_limited | quota_exhausted | auth |
    unreachable | config | unknown.
    """
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "timeout"

    # OpenAI carries a machine-readable slug in `.code` (a str — distinct from
    # the int HTTP status, which `_status_code` reads).
    slug = getattr(exc, "code", None)
    if isinstance(slug, str) and slug in _QUOTA_SLUGS:
        return "quota_exhausted"

    code = _status_code(exc)
    if code == 429:
        return "rate_limited"
    if code in (401, 403):
        return "auth"
    if code in (400, 404):
        return "config"
    if code is not None and 500 <= code < 600:
        return "unreachable"

    name = type(exc).__name__
    if name in _RATE_LIMIT_NAMES:
        return "rate_limited"
    if name in _AUTH_NAMES:
        return "auth"
    if name in _UNREACHABLE_NAMES:
        return "unreachable"
    if name in _CONFIG_NAMES:
        return "config"
    return "unknown"


_REASONS = {
    "timeout":         "the database did not respond in time",
    "rate_limited":    "the service is temporarily rate-limited",
    # Deliberately does NOT say "try again" — retrying will not help until
    # somebody tops up the account. Says enough for on-call to act, without
    # leaking billing detail to a patient.
    "quota_exhausted": "the service's API quota has been used up",
    "auth":            "the database rejected the service's credentials",
    "unreachable":     "the database could not be reached",
    "config":          "the database is not configured correctly for this environment",
}


def failure_reason(exc: BaseException) -> str:
    """A short, user-safe explanation of why a store call failed.

    Deliberately does NOT interpolate `str(exc)`. Neo4j and AstraDB embed the
    connection URI in their error messages (and auth failures sometimes the
    username), and this string is written into the LLM prompt, from which it
    can reach the user's screen. Exception class names are safe; their messages
    are not.
    """
    kind = classify(exc)
    if kind == "unknown":
        return f"the database failed with an unexpected error ({type(exc).__name__})"
    return _REASONS[kind]


def should_trip(exc: BaseException) -> bool:
    """True if this failure is evidence the STORE is down, not just this request.

    `rate_limited` and `unknown` are deliberately excluded — see the block
    comment above. A 429 means the store is alive; an unexpected exception is
    more likely our bug than the database's, and both fail fast enough that
    re-attempting them next request is cheaper than denying every user for a
    cooldown window.

    `quota_exhausted` IS included, even though it arrives as a 429. An account
    with no credit left does not recover by being retried — every attempt just
    burns a multi-second round-trip before failing identically. Latching it out
    keeps the rest of the request fast, and the cooldown still re-probes, so
    the arm comes back on its own the moment the account is topped up.
    """
    return classify(exc) in (
        "timeout", "auth", "unreachable", "config", "quota_exhausted",
    )
