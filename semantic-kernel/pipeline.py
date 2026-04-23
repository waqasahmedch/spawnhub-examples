"""
Semantic Kernel — SpawnHub multi-agent research pipeline.

Architecture
────────────
    Orchestrator  (Yahya  / PK / male)
    ├── ResearchAgent (Ibrahim / SA / male)   — researches the topic
    └── WriterAgent   (Leila  / IR / female)  — writes the final report

SpawnHub integration
────────────────────
The OTEL TracerProvider is registered globally before Semantic Kernel loads.
Setting SEMANTICKERNEL_EXPERIMENTAL_GENAI_ENABLE_OTEL_DIAGNOSTICS=true tells
SK to emit gen_ai.* spans for every LLM call — these map to agent_think events
in SpawnHub. Each ChatCompletionAgent is also wrapped in an explicit
invoke_agent span so lifecycle events always appear in the renderer.

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

# Enable SK OTEL diagnostics before any SK import
os.environ["SEMANTICKERNEL_EXPERIMENTAL_GENAI_ENABLE_OTEL_DIAGNOSTICS"] = "true"

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

# ── SpawnHub / OTEL setup ──────────────────────────────────────────────────────

_endpoint = os.getenv("SPAWNHUB_ENDPOINT", "http://ingest.localhost")
_api_key  = os.getenv("SPAWNHUB_API_KEY", "")

_provider = TracerProvider(
    resource=Resource({"service.name": "spawnhub-semantic-kernel-pipeline"})
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
tracer = trace.get_tracer("semantic_kernel.pipeline")

# ── Semantic Kernel imports ────────────────────────────────────────────────────

import semantic_kernel as sk  # noqa: E402
from semantic_kernel.agents import ChatCompletionAgent  # noqa: E402
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion  # noqa: E402
from semantic_kernel.contents import ChatHistory  # noqa: E402

# ── Personas ───────────────────────────────────────────────────────────────────

_PERSONAS: dict = json.loads(
    (Path(__file__).parent.parent / "agent-persona.json").read_text()
)


def _stamp(span: trace.Span, agent_name: str, run_id: str) -> None:
    span.set_attribute("gen_ai.operation.name", "invoke_agent")
    span.set_attribute("gen_ai.system", "semantic_kernel")
    span.set_attribute("gen_ai.agent.name", agent_name)
    span.set_attribute("pipeline.run_id", run_id)
    span.set_attribute("pipeline.pattern", "sequential")
    p = _PERSONAS.get(agent_name, {})
    for key in ("name", "gender", "country"):
        if p.get(key):
            span.set_attribute(f"agent.persona.{key}", p[key])


def _build_kernel() -> sk.Kernel:
    """Create a fresh kernel with the OpenAI chat service attached."""
    kernel = sk.Kernel()
    kernel.add_service(
        OpenAIChatCompletion(
            service_id="default",
            ai_model_id="gpt-4o-mini",
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    )
    return kernel


# ── Pipeline ───────────────────────────────────────────────────────────────────

async def _invoke_agent(agent: ChatCompletionAgent, message: str) -> str:
    """Send one message to a ChatCompletionAgent and return the response."""
    history = ChatHistory()
    history.add_user_message(message)
    response_parts: list[str] = []
    async for msg in agent.invoke(history):
        if msg.content:
            response_parts.append(str(msg.content))
    return "\n".join(response_parts)


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
            researcher = ChatCompletionAgent(
                service_id="default",
                kernel=_build_kernel(),
                name="ResearchAgent",
                instructions=(
                    "You are a research specialist. When given a topic, provide "
                    "a concise 2-3 sentence summary of the most important findings. "
                    "Keep your response factual and brief."
                ),
            )
            research_summary = await _invoke_agent(
                researcher,
                f"Research this topic and give a concise summary: {topic}",
            )
            print(f"[ResearchAgent] done ({len(research_summary)} chars)")

        # ── WriterAgent ────────────────────────────────────────────────────────
        report = ""
        with tracer.start_as_current_span("invoke_agent") as write_span:
            _stamp(write_span, "WriterAgent", run_id)
            writer = ChatCompletionAgent(
                service_id="default",
                kernel=_build_kernel(),
                name="WriterAgent",
                instructions=(
                    "You are a professional report writer. Given a topic and research "
                    "summary, write a structured report with: Executive Summary, "
                    "Key Findings (3-5 bullet points), and Conclusion."
                ),
            )
            report = await _invoke_agent(
                writer,
                (
                    f"Topic: {topic}\n\n"
                    f"Research summary:\n{research_summary}\n\n"
                    "Write the final structured report."
                ),
            )
            print(f"[WriterAgent] done ({len(report)} chars)")

        orch_span.set_attribute("gen_ai.output.length", len(report))

    _provider.force_flush(timeout_millis=10_000)
    return report


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "artificial intelligence in healthcare"

    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not set.")
        sys.exit(1)

    report = asyncio.run(run_pipeline(topic))
    print("\n" + "=" * 60)
    print(report)
    print("=" * 60)
