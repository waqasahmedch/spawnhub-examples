"""
AutoGen — SpawnHub multi-agent research pipeline.

Architecture
────────────
    Orchestrator  (Yahya  / PK / male)
    ├── ResearchAgent (Ibrahim / SA / male)   — researches the topic
    └── WriterAgent   (Leila  / IR / female)  — writes the final report

SpawnHub integration
────────────────────
Each agent is wrapped in an invoke_agent OTEL span stamped with persona
attributes (name, gender, country) and a shared pipeline.run_id so all
three avatars appear together in the same SpawnHub replay session.

Run
────────────
    python pipeline.py "quantum computing"
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

# ── SpawnHub / OTEL setup ──────────────────────────────────────────────────────
# Must happen before any AutoGen imports so the global tracer provider is set.

_endpoint = os.getenv("SPAWNHUB_ENDPOINT", "http://ingest.localhost")
_api_key  = os.getenv("SPAWNHUB_API_KEY", "")

_provider = TracerProvider(
    resource=Resource({"service.name": "spawnhub-autogen-pipeline"})
)
_provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(
            endpoint=f"{_endpoint}/v1/traces",
            headers={"X-SpawnHub-Key": _api_key} if _api_key else {},
        )
    )
)
trace.set_tracer_provider(_provider)
tracer = trace.get_tracer("autogen.pipeline")

# ── AutoGen imports ────────────────────────────────────────────────────────────

from autogen import AssistantAgent, UserProxyAgent  # noqa: E402

# ── Personas ───────────────────────────────────────────────────────────────────
# These drive avatar styling in the renderer:
# - country  → flag badge on the avatar
# - gender   → hair / body proportions
# - name     → display name shown above the avatar

_PERSONAS: dict = json.loads(
    (Path(__file__).parent.parent / "agent-persona.json").read_text()
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _stamp(span: trace.Span, agent_name: str, run_id: str) -> None:
    """Stamp the required SpawnHub attributes on an invoke_agent span."""
    span.set_attribute("gen_ai.operation.name", "invoke_agent")
    span.set_attribute("gen_ai.system", "autogen")
    span.set_attribute("gen_ai.agent.name", agent_name)
    span.set_attribute("pipeline.run_id", run_id)
    span.set_attribute("pipeline.pattern", "orchestrator")
    p = _PERSONAS.get(agent_name, {})
    for key in ("name", "gender", "country"):
        if p.get(key):
            span.set_attribute(f"agent.persona.{key}", p[key])


def _llm_config() -> dict:
    return {"model": "gpt-4o-mini", "api_key": os.getenv("OPENAI_API_KEY")}


def _proxy() -> UserProxyAgent:
    """A silent proxy that triggers one agent reply and stops."""
    return UserProxyAgent(
        name="UserProxy",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=1,
        code_execution_config=False,
    )


# ── Agents ─────────────────────────────────────────────────────────────────────

def _build_researcher() -> AssistantAgent:
    return AssistantAgent(
        name="ResearchAgent",
        llm_config=_llm_config(),
        system_message=(
            "You are a research specialist. When given a topic, find relevant "
            "information and return a concise 2-3 sentence summary. "
            "Keep your response factual and brief."
        ),
    )


def _build_writer() -> AssistantAgent:
    return AssistantAgent(
        name="WriterAgent",
        llm_config=_llm_config(),
        system_message=(
            "You are a professional report writer. Given a topic and research "
            "summary, write a structured report with: Executive Summary, "
            "Key Findings (3-5 bullet points), and Conclusion. Keep it concise."
        ),
    )


# ── Pipeline ───────────────────────────────────────────────────────────────────

def run_pipeline(topic: str) -> str:
    run_id = str(uuid.uuid4())
    print(f"\n[Pipeline] Starting on: {topic!r}  run_id={run_id}\n")

    # Orchestrator span — top-level avatar that delegates to the two sub-agents
    with tracer.start_as_current_span("invoke_agent") as orch_span:
        _stamp(orch_span, "Orchestrator", run_id)
        print("[Orchestrator] coordinating pipeline")

        # ── ResearchAgent ──────────────────────────────────────────────────────
        research_summary = ""
        with tracer.start_as_current_span("invoke_agent") as res_span:
            _stamp(res_span, "ResearchAgent", run_id)
            result = _proxy().initiate_chat(
                _build_researcher(),
                message=f"Research this topic and give a concise summary: {topic}",
            )
            research_summary = result.summary or ""
            print(f"[ResearchAgent] done ({len(research_summary)} chars)")

        # ── WriterAgent ────────────────────────────────────────────────────────
        report = ""
        with tracer.start_as_current_span("invoke_agent") as write_span:
            _stamp(write_span, "WriterAgent", run_id)
            result2 = _proxy().initiate_chat(
                _build_writer(),
                message=(
                    f"Topic: {topic}\n\n"
                    f"Research summary:\n{research_summary}\n\n"
                    "Write the final structured report."
                ),
            )
            report = result2.summary or ""
            print(f"[WriterAgent] done ({len(report)} chars)")

        orch_span.set_attribute("gen_ai.output.length", len(report))

    # Force-flush so all spans export before the process exits
    _provider.force_flush(timeout_millis=10_000)
    return report


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "artificial intelligence in healthcare"

    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set.")
        sys.exit(1)

    report = run_pipeline(topic)
    print("\n" + "=" * 60)
    print(report)
    print("=" * 60)
