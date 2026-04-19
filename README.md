# SpawnHub Examples

Sample agents that stream live telemetry to [SpawnHub](https://spawnhub.ai) — visualize your AI agent workflows as animated avatars in real time.

## Prerequisites

1. A running SpawnHub ingestion server (see [SpawnHub repo](https://github.com/waqasahmedch/spawnhub))
2. An OpenAI API key

## Examples

### `langchain-langgraph/` — LangGraph multi-agent research pipeline

A 3-agent orchestrator pipeline (Orchestrator → ResearchAgent → AnalystAgent) built with LangGraph's ReAct pattern. Uses native OTEL instrumentation — no SpawnHub SDK needed.

```bash
cd langchain-langgraph
cp .env.example .env          # add your OPENAI_API_KEY
pip install -e .
python -m sample_agent.main   # starts on port 8001

# Trigger a run
curl -X POST http://localhost:8001/run-pipeline \
     -H "Content-Type: application/json" \
     -d '{"topic": "AI in healthcare"}'
```

### `openai-agents/` — OpenAI Agents SDK multi-agent pipeline

A 3-agent pipeline (Orchestrator → ResearchAgent → WriterAgent) using the OpenAI Agents SDK. Uses the `spawnhub-openai-agents` adapter since the SDK does not yet emit native OTEL.

```bash
cd openai-agents
cp .env.example .env          # add your OPENAI_API_KEY
pip install -e .
python multi_agent_pipeline.py "quantum computing"
```

## How it works

Each agent run streams [OpenTelemetry](https://opentelemetry.io/) spans to SpawnHub's ingestion endpoint. SpawnHub maps spans to game events and renders them as animated avatars in the browser in real time.

| OTEL span | SpawnHub event | What you see |
|---|---|---|
| `invoke_agent` | Agent spawns | Avatar appears in the world |
| LLM completion | Agent thinks | Thinking animation |
| Tool call | Agent acts | Action animation |
| Span end | Agent completes | Avatar idles / despawns |
