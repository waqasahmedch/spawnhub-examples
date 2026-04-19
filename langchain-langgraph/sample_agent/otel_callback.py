"""
LangChain callback handler that emits OTEL spans for LLM calls and tool calls.

Each callback pair (start/end) produces one OTEL span stamped with:
  - gen_ai.agent.name       — avatar name in the renderer
  - pipeline.run_id         — groups all spans from one pipeline run into one session
  - pipeline.parent_span_id — explicit parent link (fallback if OTEL context lost)
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core.callbacks.base import AsyncCallbackHandler
from opentelemetry import trace
from opentelemetry.trace import Span, StatusCode

logger = logging.getLogger(__name__)


class SpawnHubCallbackHandler(AsyncCallbackHandler):
    """Emits OTEL spans for LLM completions and tool calls.

    Args:
        agent_name:       Name of the owning agent — shown as avatar name.
        run_id:           Pipeline run ID — groups all pipeline spans into one session.
        parent_span_id:   Hex span_id of the owning invoke_agent span — links think/action
                          events back to the correct avatar in the renderer.
    """

    def __init__(
        self,
        agent_name: str = "Agent",
        run_id: str | None = None,
        parent_span_id: str | None = None,
        pattern: str = "orchestrator",
    ) -> None:
        self.agent_name = agent_name
        self.run_id = run_id
        self.parent_span_id = parent_span_id
        self.pattern = pattern
        self.tracer = trace.get_tracer("spawnhub.langchain")
        self._spans: dict[str, Span] = {}

    def _stamp(self, span: Span) -> None:
        """Stamp common attributes on every span we create."""
        span.set_attribute("gen_ai.agent.name", self.agent_name)
        span.set_attribute("pipeline.pattern", self.pattern)
        if self.run_id:
            span.set_attribute("pipeline.run_id", self.run_id)
        if self.parent_span_id:
            span.set_attribute("pipeline.parent_span_id", self.parent_span_id)

    # ------------------------------------------------------------------
    # LLM / Chat model
    # ------------------------------------------------------------------

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        kw = serialized.get("kwargs", {})
        model = kw.get("model_name") or kw.get("model") or "unknown"
        span = self.tracer.start_span("openai.chat")
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.request.model", model)
        span.set_attribute("gen_ai.system", "openai")
        self._stamp(span)
        self._spans[str(run_id)] = span

    async def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        span = self._spans.pop(str(run_id), None)
        if span is None:
            return
        if response.llm_output:
            usage = response.llm_output.get("token_usage", {})
            span.set_attribute("gen_ai.usage.input_tokens", usage.get("prompt_tokens", 0))
            span.set_attribute("gen_ai.usage.output_tokens", usage.get("completion_tokens", 0))
        span.end()

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        span = self._spans.pop(str(run_id), None)
        if span:
            span.set_status(StatusCode.ERROR, str(error))
            span.end()

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown")
        span = self.tracer.start_span(f"langchain.tool.{tool_name}")
        span.set_attribute("gen_ai.operation.name", "execute_tool")
        span.set_attribute("gen_ai.tool.name", tool_name)
        self._stamp(span)
        self._spans[str(run_id)] = span

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        span = self._spans.pop(str(run_id), None)
        if span:
            span.end()

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        span = self._spans.pop(str(run_id), None)
        if span:
            span.set_status(StatusCode.ERROR, str(error))
            span.end()
