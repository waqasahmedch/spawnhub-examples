"""
Research agent built with LangGraph's ReAct pattern.

Workflow for a given topic:
  1. invoke_agent span starts  → AgentSpawn in SpawnHub
  2. LLM decides what to search  → AgentThink (via SpawnHubCallbackHandler)
  3. web_search tool called  → AgentAction (via SpawnHubCallbackHandler)
  4. LLM may call get_key_facts  → AgentAction (via SpawnHubCallbackHandler)
  5. LLM synthesizes final answer  → AgentThink (via SpawnHubCallbackHandler)
  6. invoke_agent span ends  → AgentComplete in SpawnHub
"""

from __future__ import annotations

import logging

from opentelemetry import trace

from .otel_callback import SpawnHubCallbackHandler
from .tools import get_key_facts, web_search

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("sample_agent.research")

SYSTEM_PROMPT = """You are a research assistant. When given a topic:
1. Use web_search to find recent information
2. Use get_key_facts to extract structured facts
3. Synthesize a clear, concise research summary (3-5 sentences)

Always use both tools before writing your final answer."""


def _build_agent():
    from langchain_openai import ChatOpenAI
    from langgraph.prebuilt import create_react_agent

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    return create_react_agent(
        llm,
        tools=[web_search, get_key_facts],
        prompt=SYSTEM_PROMPT,
    )


async def run_research(topic: str) -> str:
    """
    Run the research agent on a topic and return the final answer.
    The top-level invoke_agent span is created manually; LLM and tool
    spans are emitted by SpawnHubCallbackHandler.
    """
    agent_name = "ResearchAgent"
    otel_cb = SpawnHubCallbackHandler(agent_name=agent_name)

    with tracer.start_as_current_span("invoke_agent") as span:
        span.set_attribute("gen_ai.operation.name", "invoke_agent")
        span.set_attribute("gen_ai.system", "langgraph")
        span.set_attribute("gen_ai.agent.name", agent_name)
        span.set_attribute("research.topic", topic)

        logger.info("Starting research on: %s", topic)

        try:
            agent = _build_agent()
            result = await agent.ainvoke(
                {"messages": [("human", f"Research this topic thoroughly: {topic}")]},
                config={"callbacks": [otel_cb]},
            )
            answer: str = result["messages"][-1].content
            span.set_attribute("gen_ai.output.length", len(answer))
            logger.info("Research complete (%d chars)", len(answer))
        except Exception as exc:
            span.set_status(trace.StatusCode.ERROR, str(exc))
            logger.error("Agent failed: %s", exc)
            raise

    # Force-flush AFTER the invoke_agent span closes so all spans — including
    # invoke_agent itself — ship in one batch. Ingestion then sorts by
    # startTimeUnixNano so AgentSpawn always reaches the WebSocket first.
    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush(timeout_millis=5000)

    return answer
