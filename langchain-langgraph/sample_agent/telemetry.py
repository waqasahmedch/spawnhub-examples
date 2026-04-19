"""
OTEL setup for the sample agent.

Delegates to the spawnhub SDK so configuration is consistent with all
other SpawnHub-instrumented agents.

Note: opentelemetry-instrumentation-langchain is not used here — it is
incompatible with langchain >= 1.2. SpawnHubCallbackHandler (otel_callback.py)
handles LLM and tool spans via LangChain callbacks instead.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_result = None


def setup(endpoint: str = "http://localhost:8000", api_key: str = "") -> None:
    """Configure OTEL via the spawnhub SDK. Call once at startup."""
    global _result
    if _result is not None:
        return

    from spawnhub import instrument
    _result = instrument(
        api_key=api_key,
        endpoint=endpoint,
        service_name="spawnhub-sample-agent",
    )
    logger.info("[SpawnHub] configured -> %s", endpoint)


def get_result():
    """Return the InstrumentResult for force_flush() calls."""
    return _result
