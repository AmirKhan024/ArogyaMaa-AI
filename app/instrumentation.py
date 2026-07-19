"""
Lightweight per-stage timing instrumentation.

Used by the assessment pipeline (web route + LangGraph node wrapper) to produce
a per-request latency breakdown. Log lines are ASCII-only (Windows cp1252).
"""

import logging
import os
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def perf_debug_enabled() -> bool:
    """When PERF_DEBUG=true, responses include a _timings breakdown."""
    return os.getenv("PERF_DEBUG", "false").strip().lower() == "true"


@contextmanager
def stage(name, sink=None):
    """Time a pipeline stage; log it and optionally append to a sink list."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - t0) * 1000
        logger.info("[PERF] stage=%s ms=%.1f", name, ms)
        if sink is not None:
            sink.append({"stage": name, "ms": round(ms, 1)})
