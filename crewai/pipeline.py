"""
CrewAI — SpawnHub multi-agent research pipeline.

Architecture
────────────
    Orchestrator  (Yahya  / PK / male)
    ├── ResearchAgent (Ibrahim / SA / male)   — gathers information on the topic
    └── AnalystAgent  (Zainab / TR / female)  — produces the final structured report

SpawnHub integration
────────────────────
The OTEL TracerProvider is configured before CrewAI imports so any native
instrumentation CrewAI emits is automatically routed to SpawnHub. Each agent
is also wrapped in an explicit invoke_agent span to guarantee lifecycle events
(spawn / complete) always appear in the renderer.

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
# Set up before CrewAI imports so the global provider is in place.

_endpoint = os.getenv("SPAWNHUB_ENDPOINT", "http://ingest.localhost")
_api_key  = os.getenv("SPAWNHUB_API_KEY", "")

_provider = TracerProvider(
    resource=Resource({"service.name": "spawnhub-crewai-pipeline"})
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
tracer = trace.get_tracer("crewai.pipeline")

# ── CrewAI imports ─────────────────────────────────────────────────────────────

from crewai import Agent, Crew, Process, Task  # noqa: E402

# ── Personas ───────────────────────────────────────────────────────────────────

_PERSONAS: dict = json.loads(
    (Path(__file__).parent.parent / "agent-persona.json").read_text()
)


def _stamp(span: trace.Span, agent_name: str, run_id: str) -> None:
    span.set_attribute("gen_ai.operation.name", "invoke_agent")
    span.set_attribute("gen_ai.system", "crewai")
    span.set_attribute("gen_ai.agent.name", agent_name)
    span.set_attribute("pipeline.run_id", run_id)
    span.set_attribute("pipeline.pattern", "sequential")
    p = _PERSONAS.get(agent_name, {})
    for key in ("name", "gender", "country"):
        if p.get(key):
            span.set_attribute(f"agent.persona.{key}", p[key])


# ── Pipeline ───────────────────────────────────────────────────────────────────

def run_pipeline(topic: str) -> str:
    run_id = str(uuid.uuid4())
    print(f"\n[Pipeline] Starting on: {topic!r}  run_id={run_id}\n")

    with tracer.start_as_current_span("invoke_agent") as orch_span:
        _stamp(orch_span, "Orchestrator", run_id)
        print("[Orchestrator] coordinating pipeline")

        # ── ResearchAgent — one Crew, one agent, one task ──────────────────────
        research_summary = ""
        with tracer.start_as_current_span("invoke_agent") as res_span:
            _stamp(res_span, "ResearchAgent", run_id)

            researcher = Agent(
                role="Research Specialist",
                goal=f"Gather accurate, recent information about {topic}",
                backstory=(
                    "You are an expert researcher with a talent for finding clear, "
                    "factual information on any subject."
                ),
                llm="gpt-4o-mini",
                verbose=False,
            )
            research_task = Task(
                description=(
                    f"Research the topic '{topic}'. "
                    "Provide a concise 2-3 sentence summary of the most important findings."
                ),
                expected_output="A concise research summary (2-3 sentences).",
                agent=researcher,
            )
            result = Crew(
                agents=[researcher],
                tasks=[research_task],
                process=Process.sequential,
                verbose=False,
            ).kickoff()
            research_summary = str(result)
            print(f"[ResearchAgent] done ({len(research_summary)} chars)")

        # ── AnalystAgent — one Crew, one agent, one task ───────────────────────
        report = ""
        with tracer.start_as_current_span("invoke_agent") as analyst_span:
            _stamp(analyst_span, "AnalystAgent", run_id)

            analyst = Agent(
                role="Data Analyst and Report Writer",
                goal=f"Produce a clear, structured report on {topic}",
                backstory=(
                    "You are a skilled analyst who turns research findings into "
                    "well-structured, actionable reports."
                ),
                llm="gpt-4o-mini",
                verbose=False,
            )
            report_task = Task(
                description=(
                    f"Using this research summary about '{topic}':\n\n"
                    f"{research_summary}\n\n"
                    "Write a structured report with: Executive Summary, "
                    "Key Findings (3-5 bullet points), and Conclusion."
                ),
                expected_output="A structured markdown report.",
                agent=analyst,
            )
            result2 = Crew(
                agents=[analyst],
                tasks=[report_task],
                process=Process.sequential,
                verbose=False,
            ).kickoff()
            report = str(result2)
            print(f"[AnalystAgent] done ({len(report)} chars)")

        orch_span.set_attribute("gen_ai.output.length", len(report))

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
