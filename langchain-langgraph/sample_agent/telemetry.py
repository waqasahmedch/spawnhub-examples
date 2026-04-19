"""
OTEL setup for the sample agent.

Call setup() once at startup before any LangChain imports are used.
Uses SimpleSpanProcessor so spans reach SpawnHub immediately (no buffering).

Note: opentelemetry-instrumentation-langchain is not used here — it is
incompatible with langchain >= 1.2. Instead, SpawnHubCallbackHandler
(otel_callback.py) handles LLM and tool spans via LangChain callbacks.
"""

from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_initialized = False


def setup(otlp_endpoint: str = "http://localhost:8000/v1/traces") -> None:
    """Configure OTEL with OTLP exporter. Call once at startup."""
    global _initialized
    if _initialized:
        return

    resource = Resource.create({"service.name": "spawnhub-sample-agent"})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    # schedule_delay_millis=600_000 (10 min) — prevents auto-flush during any
    # realistic pipeline run.  pipeline.py calls force_flush() after the
    # top-level span closes, so ALL spans arrive in one batch.  The ingestion
    # endpoint then sorts by startTimeUnixNano → AgentSpawn is always first.
    provider.add_span_processor(
        BatchSpanProcessor(exporter, schedule_delay_millis=600_000)
    )
    trace.set_tracer_provider(provider)

    _initialized = True
    logger.info("OTEL configured → %s", otlp_endpoint)
