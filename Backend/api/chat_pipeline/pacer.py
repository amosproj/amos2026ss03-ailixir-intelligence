"""
Vertex AI Gemini admission queue for the chat pipeline.

The deployed API process and the deployed worker process are separate Cloud
Run services. Each has its own admission queue at runtime — they cannot
share a Python-level lock across processes. They do share the project-wide
Vertex AI RPM quota, so each process must independently pace its callers
to avoid exhausting that quota under concurrent load.

Why pace at all
---------------
Each chat query makes ~3 Vertex Gemini calls:
  1. Contextualize the query (always 1 call when history is non-empty)
  2. Graphiti's internal embedding call(s) during retrieval (~1)
  3. Generate the final answer (1 call)

At 10 concurrent users that's ~30 calls in ~5 seconds = ~360 RPM, just
about the Vertex flash quota ceiling. At 20+ concurrent users we'd start
overrunning. Without pacing the failure mode is a `RateLimitError`
surfaced to the iOS app as a 503; with pacing the requests queue cleanly
and complete in slightly higher wall time but always succeed.

How the admission queue works
-----------------------------
`pace_gemini_call` blocks until the next call slot opens, then releases.
The lock is held only for the wait calculation and timestamp update — not
for the actual Vertex round-trip. Concurrent callers can have their
requests in flight simultaneously; only the *moment of admission* is
serialised. Under burst load this turns a thundering herd into a steady
stream that fits inside Vertex's RPM budget.

Configuration
-------------
`CHAT_GEMINI_PACER_MIN_INTERVAL_S` (env var, float) controls the floor on
seconds between admissions. Default 0.30 — that's ~200 RPM ceiling per
process. Lower than the worker's 0.5s default because:
  - Chat queries are user-initiated and latency-sensitive
  - Chat makes fewer calls per request (3 vs ~50 for worker ingestion)
  - We want the user to get a fast response when traffic is light

If chat traffic concentrates and starts tripping 429s, raise this value
(0.5s → 120 RPM, 1.0s → 60 RPM) via env var without a code change.
"""
from __future__ import annotations

import asyncio
import logging
import os

_log = logging.getLogger(__name__)

# 0.30s → 200 RPM ceiling per process. Chat is user-facing and latency-
# sensitive, so we pace less aggressively than the worker (0.50s default).
# Both still leave headroom under the Vertex flash quota.
_MIN_INTERVAL_S = float(os.environ.get("CHAT_GEMINI_PACER_MIN_INTERVAL_S", "0.30"))

# Single admission lock per process. asyncio.Lock is process-scoped — a
# separate Cloud Run instance gets its own queue, which is correct: each
# instance manages its own slice of the project quota.
_lock = asyncio.Lock()
_last_call_at: float = 0.0


async def pace_gemini_call() -> None:
    """Block until the next Vertex Gemini call is admissible under the rate cap.

    Call this **before** every Vertex generate_content invocation in the
    chat pipeline. Holding the lock only during the wait calculation lets
    multiple in-flight Vertex calls run truly concurrently; only the
    admission moment is serialised.

    Thread/task safety: this uses `asyncio.Lock`, which is safe across
    concurrent tasks on the same event loop. It is NOT safe across
    threads — but FastAPI runs each request handler in the main event
    loop, so threading isn't a concern.
    """
    global _last_call_at
    async with _lock:
        loop = asyncio.get_running_loop()
        elapsed = loop.time() - _last_call_at
        wait = _MIN_INTERVAL_S - elapsed
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call_at = asyncio.get_running_loop().time()
