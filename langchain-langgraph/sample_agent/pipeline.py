"""
Multi-agent research pipeline.

Three agents run sequentially under an Orchestrator:

  Orchestrator
  ├── ResearchAgent   — web_search to gather raw information
  └── AnalystAgent    — get_key_facts + write_report to produce the final output

Each agent gets its own invoke_agent OTEL span.

To ensure all events are grouped into ONE replay session and avatars animate
correctly, every span carries two explicit attributes:
  - pipeline.run_id         → shared UUID, used as session_id by the translator
  - pipeline.parent_span_id → each agent's own invoke_agent span_id, stamped on
                               its LLM/tool child spans so the renderer updates
                               the correct avatar

Persona attributes (agent.persona.*) drive avatar styling in the renderer:
country flags, gender-specific hair, and cultural hats.
"""

from __future__ import annotations

import logging
import uuid

from opentelemetry import trace

from .otel_callback import SpawnHubCallbackHandler
from .tools import get_key_facts, web_search, write_report

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("sample_agent.pipeline")

# ── Agent personas ─────────────────────────────────────────────────────────────
# Each agent has a display name, gender, and home country.
# These drive cultural hats, gender-specific hair, and country flag labels
# in the renderer.  Framework is auto-detected from gen_ai.system.

_PERSONAS = {
    "Orchestrator":  {"name": "Yahya",   "gender": "male",   "country": "PK"},
    "ResearchAgent": {"name": "Ibrahim", "gender": "male",   "country": "SA"},
    "AnalystAgent":  {"name": "Zainab",  "gender": "female", "country": "TR"},
}

# ── Prompts ────────────────────────────────────────────────────────────────────

_RESEARCH_PROMPT = """You are a research specialist. Given a topic:
1. Use web_search to find recent, relevant information (search at least twice with different angles)
2. Summarize your findings in 2-3 concise sentences

Always call web_search before writing your summary."""

_ANALYST_PROMPT = """You are a data analyst and report writer. Given a topic and research summary:
1. Use get_key_facts to extract structured facts
2. Use write_report to produce the final structured report

Always call both tools. Pass the research summary into write_report."""


# ── Sub-agent runners ──────────────────────────────────────────────────────────

def _build_research_agent():
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent
    return create_react_agent(
        ChatOpenAI(model="gpt-4o-mini", temperature=0),
        tools=[web_search],
        prompt=_RESEARCH_PROMPT,
    )


def _build_analyst_agent():
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent
    return create_react_agent(
        ChatOpenAI(model="gpt-4o-mini", temperature=0),
        tools=[get_key_facts, write_report],
        prompt=_ANALYST_PROMPT,
    )


def _hex_span_id(span: trace.Span) -> str:
    """Return the span's span_id as a 16-char hex string (OTLP wire format)."""
    return format(span.get_span_context().span_id, "016x")


def _stamp_persona(span: trace.Span, agent_name: str) -> None:
    """Attach persona attributes to an invoke_agent span."""
    p = _PERSONAS.get(agent_name, {})
    if p.get("name"):
        span.set_attribute("agent.persona.name",    p["name"])
    if p.get("gender"):
        span.set_attribute("agent.persona.gender",  p["gender"])
    if p.get("country"):
        span.set_attribute("agent.persona.country", p["country"])


async def _run_research_agent(topic: str, run_id: str) -> str:
    """Run ResearchAgent. Its own span_id is passed to the callback handler so
    LLM/tool child spans know which avatar to update."""
    agent_name = "ResearchAgent"

    with tracer.start_as_current_span("invoke_agent") as span:
        span.set_attribute("gen_ai.operation.name", "invoke_agent")
        span.set_attribute("gen_ai.system", "langgraph")
        span.set_attribute("gen_ai.agent.name", agent_name)
        span.set_attribute("research.topic", topic)
        span.set_attribute("pipeline.run_id", run_id)
        span.set_attribute("pipeline.pattern", "orchestrator")
        _stamp_persona(span, agent_name)

        # Pass this span's own id as parent_span_id so child LLM/tool spans
        # update this avatar in the renderer.
        otel_cb = SpawnHubCallbackHandler(
            agent_name=agent_name,
            run_id=run_id,
            parent_span_id=_hex_span_id(span),
            pattern="orchestrator",
        )

        logger.info("[ResearchAgent] starting on: %s", topic)
        agent = _build_research_agent()
        result = await agent.ainvoke(
            {"messages": [("human", f"Research this topic thoroughly: {topic}")]},
            config={"callbacks": [otel_cb]},
        )
        summary: str = result["messages"][-1].content
        span.set_attribute("gen_ai.output.length", len(summary))
        logger.info("[ResearchAgent] done (%d chars)", len(summary))

    return summary


async def _run_analyst_agent(topic: str, research_summary: str, run_id: str) -> str:
    """Run AnalystAgent. Same pattern — own span_id passed to callback."""
    agent_name = "AnalystAgent"

    with tracer.start_as_current_span("invoke_agent") as span:
        span.set_attribute("gen_ai.operation.name", "invoke_agent")
        span.set_attribute("gen_ai.system", "langgraph")
        span.set_attribute("gen_ai.agent.name", agent_name)
        span.set_attribute("research.topic", topic)
        span.set_attribute("pipeline.run_id", run_id)
        span.set_attribute("pipeline.pattern", "orchestrator")
        _stamp_persona(span, agent_name)

        otel_cb = SpawnHubCallbackHandler(
            agent_name=agent_name,
            run_id=run_id,
            parent_span_id=_hex_span_id(span),
            pattern="orchestrator",
        )

        logger.info("[AnalystAgent] starting on: %s", topic)
        agent = _build_analyst_agent()
        result = await agent.ainvoke(
            {
                "messages": [
                    (
                        "human",
                        f"Topic: {topic}\n\nResearch summary:\n{research_summary}\n\n"
                        f"Extract facts and write the final report.",
                    )
                ]
            },
            config={"callbacks": [otel_cb]},
        )
        report: str = result["messages"][-1].content
        span.set_attribute("gen_ai.output.length", len(report))
        logger.info("[AnalystAgent] done (%d chars)", len(report))

    return report


# ── Orchestrator ───────────────────────────────────────────────────────────────

async def run_pipeline(topic: str) -> str:
    """
    Run the full 3-agent pipeline and return the final report.

    OTEL span hierarchy:
        invoke_agent (Orchestrator)
        ├── invoke_agent (ResearchAgent)
        └── invoke_agent (AnalystAgent)

    All spans share pipeline.run_id → one session in SpawnHub replay.
    """
    agent_name = "Orchestrator"
    run_id = str(uuid.uuid4())

    with tracer.start_as_current_span("invoke_agent") as span:
        span.set_attribute("gen_ai.operation.name", "invoke_agent")
        span.set_attribute("gen_ai.system", "langgraph")
        span.set_attribute("gen_ai.agent.name", agent_name)
        span.set_attribute("research.topic", topic)
        span.set_attribute("pipeline.run_id", run_id)
        span.set_attribute("pipeline.pattern", "orchestrator")
        _stamp_persona(span, agent_name)

        logger.info("[Orchestrator] pipeline starting — topic: %s  run_id: %s", topic, run_id)

        try:
            research_summary = await _run_research_agent(topic, run_id)
            report = await _run_analyst_agent(topic, research_summary, run_id)

            span.set_attribute("gen_ai.output.length", len(report))
            logger.info("[Orchestrator] pipeline complete (%d chars)", len(report))

        except Exception as exc:
            span.set_status(trace.StatusCode.ERROR, str(exc))
            logger.error("[Orchestrator] pipeline failed: %s", exc)
            raise

    # Force-flush after the top-level span closes so all spans export together
    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush(timeout_millis=10_000)

    return report
