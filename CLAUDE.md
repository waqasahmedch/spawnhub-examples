# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is this repo

`spawnhub-examples` is the **public developer-facing** sample repository for [SpawnHub](https://github.com/waqasahmedch/spawnhub). It contains ready-to-run AI agent pipelines that stream live telemetry to SpawnHub, allowing developers to evaluate and integrate SpawnHub into their own projects.

This repo is intentionally separate from the main SpawnHub monorepo because:
- It targets external developers, not the SpawnHub platform team
- It needs a clean commit history, beginner-friendly code, and good documentation
- It releases on its own cadence driven by customer feedback and new framework support

## How SpawnHub works (context for all examples)

SpawnHub receives OpenTelemetry (OTEL) spans from AI agent frameworks and maps them to game events, rendering each agent as an animated avatar in a browser-based 3D world.

### OTEL Span → Game Event mapping

| OTEL span | SpawnHub event | Visual result |
|---|---|---|
| `invoke_agent` span start | `agent_spawn` | Avatar appears in the world |
| LLM completion span | `agent_think` | Thinking animation |
| Tool call span | `agent_action` | Action animation |
| Retrieval span | `agent_retrieve` | Walk-to-library animation |
| `invoke_agent` span end | `agent_complete` | Avatar idles / despawns |

Parent-child spans via `parentSpanId` produce parent-child avatar relationships (sub-agents spawning under an orchestrator).

### Two ingestion paths

1. **OTEL (preferred)** — frameworks that emit native OpenTelemetry spans (LangChain, LangGraph, CrewAI, AutoGen, Google ADK) send directly to `POST /v1/traces`. No SpawnHub SDK needed.
2. **Direct events** — frameworks without native OTEL (OpenAI Agents SDK) use a thin adapter (`spawnhub-openai-agents`) that posts `GameEvent` JSON directly to `POST /v1/events`.

### GameEvent schema (canonical data contract)

```python
# All events share these base fields:
session_id    # groups all events from one pipeline run
trace_id      # OTEL trace ID
span_id       # OTEL span ID
agent_id      # avatar identifier (= invoke_agent span_id)
agent_name    # display name shown above avatar
parent_agent_id  # set when spawned by another agent
pattern       # orchestrator | sequential | parallel | conversational | reflection
timestamp
tenant_id     # optional — for multi-tenant SpawnHub deployments
workflow_id   # optional — groups sessions under a named workflow

# AgentSpawnEvent extras:
agent_type    # e.g. "langchain.agent", "openai_agents"
persona:
  name        # "Ibrahim", "Zara"
  gender      # "male" | "female"
  country     # ISO 3166-1 alpha-2 — drives cultural hat + flag label

# AgentThinkEvent extras:
model         # "gpt-4o", "gpt-4o-mini"
prompt_tokens
completion_tokens

# AgentActionEvent extras:
tool_name
tool_input    # dict

# AgentRetrieveEvent extras:
query
source        # vector store name

# AgentCompleteEvent extras:
success       # bool
output_summary
```

## Repository structure

```
spawnhub-examples/
  langchain-langgraph/    — LangGraph ReAct pipeline using native OTEL
  openai-agents/          — OpenAI Agents SDK pipeline via spawnhub-openai-agents adapter
```

Each example is a self-contained Python package with its own `pyproject.toml`.

## Running an example

### Prerequisites

1. SpawnHub ingestion server running at `http://localhost:8000`
   ```bash
   # In the main spawnhub repo:
   make ingestion
   ```
2. SpawnHub renderer running at `http://localhost:5173`
   ```bash
   # In the main spawnhub repo:
   make renderer
   ```
3. OpenAI API key

### langchain-langgraph

```bash
cd langchain-langgraph
cp .env.example .env      # add OPENAI_API_KEY
pip install -e .

python -m sample_agent.main   # starts HTTP server on port 8001

# Single agent
curl -X POST http://localhost:8001/run \
     -H "Content-Type: application/json" \
     -d '{"topic": "AI in healthcare"}'

# Full 3-agent pipeline (Orchestrator → ResearchAgent → AnalystAgent)
curl -X POST http://localhost:8001/run-pipeline \
     -H "Content-Type: application/json" \
     -d '{"topic": "AI in healthcare"}'
```

### openai-agents

```bash
cd openai-agents
cp .env.example .env      # add OPENAI_API_KEY
pip install -e .

python multi_agent_pipeline.py "quantum computing"
```

## Adding a new example

Each new example should follow this pattern:

1. Create a subdirectory named after the framework, e.g. `crewai/`
2. Include `pyproject.toml`, `README.md`, `.env.example`
3. **Prefer native OTEL** — check if the framework emits OTEL before writing an adapter
4. If native OTEL is available: configure `OTLPSpanExporter` pointing to `http://localhost:8000/v1/traces`
5. If no OTEL: use `spawnhub-openai-agents` as a reference for writing an adapter that posts to `/v1/events`
6. Stamp `pipeline.run_id` on all spans in a pipeline run so all agents group into one session
7. Add the example to the root `README.md`

## Key implementation details

### Session grouping (critical)

All spans from a single pipeline run must share the same `session_id` so SpawnHub groups them into one replay. The translator derives `session_id` from `pipeline.run_id` OTEL attribute if present, otherwise falls back to `trace_id`. Always set `pipeline.run_id` as a span attribute on every span in a multi-agent pipeline.

### Force flush after top-level span

Always call `provider.force_flush()` after the top-level `invoke_agent` span closes. This ensures all spans (including the invoke_agent span itself) export in one batch. SpawnHub then sorts by `startTimeUnixNano` so `agent_spawn` always reaches the renderer before `agent_think`/`agent_action`.

### Personas drive avatar styling

Setting `agent.persona.country`, `agent.persona.gender`, and `agent.persona.name` on `invoke_agent` spans controls the avatar appearance in the renderer (cultural hats, flag labels, gender-specific hair).

## Related repos

- **SpawnHub platform** — https://github.com/waqasahmedch/spawnhub (ingestion, renderer, admin-ui)
- **spawnhub-openai-agents** — published as a pip package from `packages/openai-agents-adapter` in the main repo
