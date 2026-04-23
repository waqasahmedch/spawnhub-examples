"""
Google ADK — SpawnHub multi-agent research pipeline.

Architecture
────────────
    Orchestrator  (Yahya  / PK / male)
    ├── ResearchAgent (Ibrahim / SA / male)   — researches the topic using Gemini
    └── WriterAgent   (Leila  / IR / female)  — writes the final report using Gemini

SpawnHub integration
────────────────────
Setting GOOGLE_GENAI_OBSERVABILITY_ENABLED=true and pointing the global OTEL
provider at SpawnHub tells ADK to route all gen_ai.* spans directly to the
renderer. Each agent is also wrapped in an explicit invoke_agent span to ensure
lifecycle events (spawn / complete) always appear.

Requires a Google Gemini API key — get one at https://aistudio.google.com/app/apikey

Run
────────────
    python pipeline.py "quantum computing"
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# Enable ADK OTEL observability before any ADK import
os.environ["GOOGLE_GENAI_OBSERVABILITY_ENABLED"] = "true"

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

# ── SpawnHub / OTEL setup ──────────────────────────────────────────────────────

_endpoint = os.getenv("SPAWNHUB_ENDPOINT", "http://ingest.localhost")
_api_key  = os.getenv("SPAWNHUB_API_KEY", "")

_provider = TracerProvider(
    resource=Resource({"service.name": "spawnhub-google-adk-pipeline"})
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
tracer = trace.get_tracer("google_adk.pipeline")

# ── Google ADK imports ─────────────────────────────────────────────────────────

from google.adk.agents import Agent  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai.types import Content, Part  # noqa: E402

# ── Personas ───────────────────────────────────────────────────────────────────

_PERSONAS: dict = json.loads(
    (Path(__file__).parent.parent / "agent-persona.json").read_text()
)


def _stamp(span: trace.Span, agent_name: str, run_id: str) -> None:
    span.set_attribute("gen_ai.operation.name", "invoke_agent")
    span.set_attribute("gen_ai.system", "google_adk")
    span.set_attribute("gen_ai.agent.name", agent_name)
    span.set_attribute("pipeline.run_id", run_id)
    span.set_attribute("pipeline.pattern", "sequential")
    p = _PERSONAS.get(agent_name, {})
    for key in ("name", "gender", "country"):
        if p.get(key):
            span.set_attribute(f"agent.persona.{key}", p[key])


# ── Mock tools ─────────────────────────────────────────────────────────────────

def web_search(query: str) -> str:
    """Search the web for information about a topic."""
    return (
        f"[Search results for '{query}']\n"
        "• Recent studies show significant progress in this area.\n"
        "• Key players include major research institutions and industry leaders.\n"
        "• The latest developments point to promising real-world applications."
    )


def write_report(topic: str, research_summary: str) -> str:
    """Compile research into a structured report."""
    return (
        f"# Report: {topic}\n\n"
        f"## Executive Summary\n{research_summary}\n\n"
        "## Conclusion\nThis area shows strong momentum and continued investment.\n"
    )


# ── Agent runner helper ────────────────────────────────────────────────────────

async def _run_agent(agent: Agent, message: str, app_name: str) -> str:
    """Run a single ADK agent turn and return the text response."""
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=app_name,
        user_id="pipeline",
        session_id=str(uuid.uuid4()),
    )
    runner = Runner(
        agent=agent,
        app_name=app_name,
        session_service=session_service,
    )
    user_message = Content(parts=[Part(text=message)])
    response_parts: list[str] = []
    async for event in runner.run_async(
        user_id="pipeline",
        session_id=session.id,
        new_message=user_message,
    ):
        if event.is_final_response() and event.content:
            for part in event.content.parts:
                if part.text:
                    response_parts.append(part.text)
    return "\n".join(response_parts)


# ── Pipeline ───────────────────────────────────────────────────────────────────

async def run_pipeline(topic: str) -> str:
    run_id = str(uuid.uuid4())
    print(f"\n[Pipeline] Starting on: {topic!r}  run_id={run_id}\n")

    with tracer.start_as_current_span("invoke_agent") as orch_span:
        _stamp(orch_span, "Orchestrator", run_id)
        print("[Orchestrator] coordinating pipeline")

        # ── ResearchAgent ──────────────────────────────────────────────────────
        research_summary = ""
        with tracer.start_as_current_span("invoke_agent") as res_span:
            _stamp(res_span, "ResearchAgent", run_id)
            researcher = Agent(
                name="ResearchAgent",
                model="gemini-2.0-flash",
                instruction=(
                    "You are a research specialist. Use web_search to find "
                    "information on the given topic and return a concise "
                    "2-3 sentence summary of the key findings."
                ),
                tools=[web_search],
            )
            research_summary = await _run_agent(
                researcher,
                f"Research this topic and give a concise summary: {topic}",
                app_name="research",
            )
            print(f"[ResearchAgent] done ({len(research_summary)} chars)")

        # ── WriterAgent ────────────────────────────────────────────────────────
        report = ""
        with tracer.start_as_current_span("invoke_agent") as write_span:
            _stamp(write_span, "WriterAgent", run_id)
            writer = Agent(
                name="WriterAgent",
                model="gemini-2.0-flash",
                instruction=(
                    "You are a professional report writer. Use write_report "
                    "to produce a clear, structured report from the given "
                    "topic and research summary."
                ),
                tools=[write_report],
            )
            report = await _run_agent(
                writer,
                (
                    f"Topic: {topic}\n\n"
                    f"Research summary:\n{research_summary}\n\n"
                    "Write the final structured report using write_report."
                ),
                app_name="writer",
            )
            print(f"[WriterAgent] done ({len(report)} chars)")

        orch_span.set_attribute("gen_ai.output.length", len(report))

    _provider.force_flush(timeout_millis=10_000)
    return report


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "artificial intelligence in healthcare"

    if not os.getenv("GOOGLE_API_KEY"):
        print("Error: GOOGLE_API_KEY not set.")
        sys.exit(1)

    report = asyncio.run(run_pipeline(topic))
    print("\n" + "=" * 60)
    print(report)
    print("=" * 60)
