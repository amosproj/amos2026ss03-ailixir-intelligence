"""
Vertex AI Gemini rate-limit pacer for Graphiti.

Graphiti's add_episode bursts many Gemini calls in short windows:
  - one extract-nodes call
  - one resolve-with-llm call per candidate entity (the firehose)
  - one extract-edges call
  - one resolve call per candidate edge
  - one reranker call per candidate edge

For a content-rich German MRT report that's 30–50 calls in 10–15 seconds.
The Vertex AI per-project Gemini "Generate Content Requests per minute"
quota for gemini-2.5-flash-lite (us-central1) is in the low hundreds, so
the burst overruns quota and Graphiti raises RateLimitError, marking
the document FAILED.

This module exposes paced wrappers around Graphiti's GeminiClient and
GeminiRerankerClient. The pacer state is module-global because the LLM
and the reranker share one Vertex project-region quota — pacing them
independently would double the effective rate. The pacer admits at
most one underlying call per _MIN_INTERVAL_S; bursts get serialised
into a steady stream that stays under quota.

Wall-time cost: ~15–25s extra per document on a typical clinical report.
Pub/Sub ack deadline (600s default on push subscriptions) absorbs this
without retry storms.

The proper structural fix is configuring add_episode with an
`entity_types` Pydantic schema (Patient, Examination, Finding, etc.)
which constrains extraction to a defined set rather than free-form
candidates, dramatically cutting the resolve call count. That work
lives in ai-playground/pipeline_refinement/ and should land in
Backend/workers/ in a follow-up sprint. Until then, pacing keeps the
demo path working without truncating OCR content.
"""

from __future__ import annotations

import asyncio
import logging
import os

from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
from graphiti_core.llm_client.gemini_client import GeminiClient

_log = logging.getLogger(__name__)

# 0.50s → 120 RPM ceiling. Comfortable headroom under the 200 RPM default
# Vertex quota even allowing for concurrent test runs and other workers
# sharing the project. Override via env if Vertex quota is later raised.
_MIN_INTERVAL_S = float(os.environ.get("GEMINI_PACER_MIN_INTERVAL_S", "0.5"))

# A single asyncio.Lock + last-call timestamp shared by ALL paced callers
# in this worker process. One lock = one serialised admission queue.
_pacer_lock = asyncio.Lock()
_last_call_at: float = 0.0


async def _admit() -> None:
    """Block until the next Vertex call is allowed under the rate cap.

    Holds the global pacer lock only for the wait/timestamp update, not
    for the actual Vertex round-trip — concurrent callers can have their
    requests in flight simultaneously, only their admission is serialised.
    """
    global _last_call_at
    async with _pacer_lock:
        loop = asyncio.get_running_loop()
        elapsed = loop.time() - _last_call_at
        wait = _MIN_INTERVAL_S - elapsed
        if wait > 0:
            await asyncio.sleep(wait)
        _last_call_at = asyncio.get_running_loop().time()


async def pace_gemini_call() -> None:
    """Public admission hook for callers outside Graphiti's client surface.

    The new LLM document-analysis step (workers/pipeline/llm/extractor.py)
    invokes Vertex Gemini directly via `client.aio.models.generate_content`
    — not through Graphiti's GeminiClient — so it would otherwise bypass
    this pacer. Calling `await pace_gemini_call()` before each direct
    Vertex invocation keeps every Gemini call in the worker — Graphiti
    internal AND top-level analyzer — going through the same shared
    admission queue. One queue per worker process, one Vertex quota
    bucket per project: keeping them aligned is what prevents the
    `RateLimitError` we burned half a day on.
    """
    await _admit()


class PacedGeminiClient(GeminiClient):
    """GeminiClient that admits at most one call per _MIN_INTERVAL_S.

    Wraps both the public generate_response entry point and the small-
    model variant Graphiti reaches for during cheaper extraction steps.
    """

    async def generate_response(self, *args, **kwargs):
        await _admit()
        return await super().generate_response(*args, **kwargs)


class PacedGeminiRerankerClient(GeminiRerankerClient):
    """GeminiRerankerClient that shares the same admission queue as the LLM.

    The reranker calls hit the same Vertex Gemini quota, so excluding
    them from pacing would defeat the purpose.
    """

    async def rank(self, *args, **kwargs):
        await _admit()
        return await super().rank(*args, **kwargs)
