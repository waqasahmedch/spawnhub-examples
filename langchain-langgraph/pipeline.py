"""
LangGraph — SpawnHub multi-agent research pipeline.

Architecture
────────────
    Orchestrator  (configured in ../agent-persona.json)
    ├── ResearchAgent — web_search to gather raw information
    └── AnalystAgent  — get_key_facts + write_report to produce the final output

SpawnHub integration
────────────────────
Each agent is wrapped in an invoke_agent OTEL span. SpawnHubCallbackHandler
emits child spans for every LLM call (agent_think) and tool call (agent_action)
so the corresponding avatars animate throughout the run.

All spans share pipeline.run_id so SpawnHub groups them into one replay session.

Run
────────────
    python pipeline.py "quantum computing"
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID as _UUID

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import Span, StatusCode

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)

# ── SpawnHub / OTEL setup ──────────────────────────────────────────────────────
# Must happen before any LangChain imports.

_endpoint = os.getenv("SPAWNHUB_ENDPOINT", "http://ingest.localhost")
_api_key  = os.getenv("SPAWNHUB_API_KEY", "")

_provider = TracerProvider(
    resource=Resource({"service.name": "spawnhub-langgraph-pipeline"})
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
tracer = trace.get_tracer("langgraph.pipeline")

# ── Personas — loaded from shared agent-persona.json ──────────────────────────

_PERSONAS: dict = json.loads(
    (Path(__file__).parent.parent / "agent-persona.json").read_text()
)

# ── LangChain imports (after OTEL setup) ──────────────────────────────────────

from langchain_core.callbacks.base import AsyncCallbackHandler  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from langgraph.prebuilt import create_react_agent  # noqa: E402

# ── SpawnHub callback handler ──────────────────────────────────────────────────
# Emits child OTEL spans for every LLM call and tool call so SpawnHub can
# animate the correct avatar with think / action events.

class SpawnHubCallbackHandler(AsyncCallbackHandler):
    def __init__(self, agent_name: str, run_id: str, parent_span_id: str, pattern: str = "orchestrator") -> None:
        self.agent_name    = agent_name
        self.run_id        = run_id
        self.parent_span_id = parent_span_id
        self.pattern       = pattern
        self._tracer       = trace.get_tracer("spawnhub.langchain")
        self._spans: dict[str, Span] = {}

    def _stamp(self, span: Span) -> None:
        span.set_attribute("gen_ai.agent.name",        self.agent_name)
        span.set_attribute("pipeline.run_id",           self.run_id)
        span.set_attribute("pipeline.pattern",          self.pattern)
        span.set_attribute("pipeline.parent_span_id",   self.parent_span_id)

    async def on_chat_model_start(self, serialized: dict[str, Any], messages: list, *, run_id: _UUID, **kwargs: Any) -> None:
        kw    = serialized.get("kwargs", {})
        model = kw.get("model_name") or kw.get("model") or "unknown"
        span  = self._tracer.start_span("openai.chat")
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.request.model",  model)
        span.set_attribute("gen_ai.system",          "openai")
        self._stamp(span)
        self._spans[str(run_id)] = span

    async def on_llm_end(self, response: Any, *, run_id: _UUID, **kwargs: Any) -> None:
        span = self._spans.pop(str(run_id), None)
        if span is None:
            return
        if response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            span.set_attribute("gen_ai.usage.input_tokens",  usage.get("prompt_tokens", 0))
            span.set_attribute("gen_ai.usage.output_tokens", usage.get("completion_tokens", 0))
        span.end()

    async def on_llm_error(self, error: BaseException, *, run_id: _UUID, **kwargs: Any) -> None:
        span = self._spans.pop(str(run_id), None)
        if span:
            span.set_status(StatusCode.ERROR, str(error))
            span.end()

    async def on_tool_start(self, serialized: dict[str, Any], input_str: str, *, run_id: _UUID, **kwargs: Any) -> None:
        tool_name = serialized.get("name", "unknown")
        span = self._tracer.start_span(f"langchain.tool.{tool_name}")
        span.set_attribute("gen_ai.operation.name", "execute_tool")
        span.set_attribute("gen_ai.tool.name",      tool_name)
        self._stamp(span)
        self._spans[str(run_id)] = span

    async def on_tool_end(self, output: Any, *, run_id: _UUID, **kwargs: Any) -> None:
        span = self._spans.pop(str(run_id), None)
        if span:
            span.end()

    async def on_tool_error(self, error: BaseException, *, run_id: _UUID, **kwargs: Any) -> None:
        span = self._spans.pop(str(run_id), None)
        if span:
            span.set_status(StatusCode.ERROR, str(error))
            span.end()


# ── Mock tools ─────────────────────────────────────────────────────────────────

_MOCK_RESULTS = {
    "ai":      "AI research in 2026 is dominated by multi-modal models and agentic systems. Major labs have released frontier models with extended context windows. Open-source alternatives are closing the capability gap.",
    "quantum": "Quantum computing reached 1,000+ qubit processors in 2026. IBM and Google lead commercial deployments. Error correction improved via surface codes. Quantum advantage demonstrated in drug discovery.",
    "climate": "Climate data shows 1.4°C warming above pre-industrial levels. Renewables now 42% of global electricity. Carbon capture deployed in 15 countries. Green hydrogen emerging for heavy industry.",
    "default": "Recent developments show significant progress across multiple fronts. Key findings include improved performance, wider industry adoption, and new open-source contributions.",
}

def _mock_search(query: str) -> str:
    for keyword, result in _MOCK_RESULTS.items():
        if keyword in query.lower():
            return f"[Web results for '{query}']\n\n{result}"
    return f"[Web results for '{query}']\n\n{_MOCK_RESULTS['default']}"

@tool
def web_search(query: str) -> str:
    """Search the web for recent news and information about a topic."""
    return _mock_search(query)

@tool
def get_key_facts(topic: str, max_facts: int = 5) -> str:
    """Extract the most important facts about a topic."""
    return "\n".join([
        f"Fact {i+1} about {topic}: {line}"
        for i, line in enumerate([
            "Based on recent research, this field is rapidly evolving.",
            "Multiple peer-reviewed studies confirm core principles.",
            "Industry adoption has grown 40% year-over-year.",
            "Leading organizations are investing heavily in this area.",
            "Open-source contributions are accelerating innovation.",
        ][:max_facts])
    ])

@tool
def write_report(topic: str, research_summary: str, key_facts: str) -> str:
    """Synthesize research and facts into a structured final report."""
    return (
        f"# Report: {topic}\n\n"
        f"## Executive Summary\n"
        f"This report synthesizes recent findings on {topic}.\n\n"
        f"## Key Findings\n{key_facts}\n\n"
        f"## Research Context\n{research_summary[:400]}\n\n"
        f"## Conclusion\n"
        f"The analysis confirms that {topic} remains a high-priority area with strong momentum."
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _hex_span_id(span: Span) -> str:
    return format(span.get_span_context().span_id, "016x")

def _stamp_agent_span(span: Span, agent_name: str, run_id: str) -> None:
    """Stamp required SpawnHub attributes on an invoke_agent span."""
    span.set_attribute("gen_ai.operation.name", "invoke_agent")
    span.set_attribute("gen_ai.system",          "langgraph")
    span.set_attribute("gen_ai.agent.name",      agent_name)
    span.set_attribute("pipeline.run_id",         run_id)
    span.set_attribute("pipeline.pattern",        "orchestrator")
    p = _PERSONAS.get(agent_name, {})
    for key in ("name", "gender", "country"):
        if p.get(key):
            span.set_attribute(f"agent.persona.{key}", p[key])


# ── Sub-agent runners ──────────────────────────────────────────────────────────

async def _run_research_agent(topic: str, run_id: str) -> str:
    agent_name = "ResearchAgent"
    with tracer.start_as_current_span("invoke_agent") as span:
        _stamp_agent_span(span, agent_name, run_id)
        otel_cb = SpawnHubCallbackHandler(
            agent_name=agent_name,
            run_id=run_id,
            parent_span_id=_hex_span_id(span),
        )
        agent = create_react_agent(
            ChatOpenAI(model="gpt-4o-mini", temperature=0),
            tools=[web_search],
            prompt="You are a research specialist. Use web_search to find information and return a concise 2-3 sentence summary. Always call web_search before writing your answer.",
        )
        result = await agent.ainvoke(
            {"messages": [("human", f"Research this topic thoroughly: {topic}")]},
            config={"callbacks": [otel_cb]},
        )
        summary: str = result["messages"][-1].content
        span.set_attribute("gen_ai.output.length", len(summary))
        logger.info("[ResearchAgent] done (%d chars)", len(summary))
    return summary


async def _run_analyst_agent(topic: str, research_summary: str, run_id: str) -> str:
    agent_name = "AnalystAgent"
    with tracer.start_as_current_span("invoke_agent") as span:
        _stamp_agent_span(span, agent_name, run_id)
        otel_cb = SpawnHubCallbackHandler(
            agent_name=agent_name,
            run_id=run_id,
            parent_span_id=_hex_span_id(span),
        )
        agent = create_react_agent(
            ChatOpenAI(model="gpt-4o-mini", temperature=0),
            tools=[get_key_facts, write_report],
            prompt="You are a data analyst and report writer. Use get_key_facts then write_report. Always call both tools.",
        )
        result = await agent.ainvoke(
            {"messages": [("human", f"Topic: {topic}\n\nResearch summary:\n{research_summary}\n\nExtract facts and write the final report.")]},
            config={"callbacks": [otel_cb]},
        )
        report: str = result["messages"][-1].content
        span.set_attribute("gen_ai.output.length", len(report))
        logger.info("[AnalystAgent] done (%d chars)", len(report))
    return report


# ── Pipeline ───────────────────────────────────────────────────────────────────

async def run_pipeline(topic: str) -> str:
    run_id = str(uuid.uuid4())
    print(f"\n[Pipeline] Starting on: {topic!r}  run_id={run_id}\n")

    with tracer.start_as_current_span("invoke_agent") as orch_span:
        _stamp_agent_span(orch_span, "Orchestrator", run_id)
        logger.info("[Orchestrator] pipeline starting — topic: %s", topic)

        try:
            research_summary = await _run_research_agent(topic, run_id)
            report = await _run_analyst_agent(topic, research_summary, run_id)
            orch_span.set_attribute("gen_ai.output.length", len(report))
        except Exception as exc:
            orch_span.set_status(StatusCode.ERROR, str(exc))
            logger.error("[Orchestrator] pipeline failed: %s", exc)
            raise

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
