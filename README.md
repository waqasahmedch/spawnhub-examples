# SpawnHub Examples

Sample agents that stream live telemetry to [SpawnHub](https://spawnhub.ai) — visualize your AI agent workflows as animated avatars in real time.

## Prerequisites

1. SpawnHub Docker stack running (from the [spawnhub repo](https://github.com/waqasahmedch/spawnhub)):
   ```bash
   make infra-up
   ```
2. Open **http://app.localhost** in your browser and pick a theme
3. An OpenAI API key (or Google API key for the ADK example)
4. A SpawnHub API key — for local dev use `spwnhub_dev_key_replace_me` (defined in `infra/kong/kong.yml`)

## Examples

### `langchain-langgraph/` — LangGraph multi-agent research pipeline

A 3-agent orchestrator pipeline (Orchestrator → ResearchAgent → AnalystAgent) built with LangGraph's ReAct pattern. Uses native OTEL — no SpawnHub SDK needed.

```bash
cd langchain-langgraph
cp .env.example .env          # add your OPENAI_API_KEY + SPAWNHUB_API_KEY
uv venv && source .venv/bin/activate
uv pip install -e .
python pipeline.py "quantum computing"
```

### `openai-agents/` — OpenAI Agents SDK multi-agent pipeline

A 3-agent pipeline (Orchestrator → ResearchAgent → WriterAgent) using the OpenAI Agents SDK. Uses the `spawnhub-openai-agents` adapter since the SDK does not yet emit native OTEL.

```bash
cd openai-agents
cp .env.example .env          # add your OPENAI_API_KEY + SPAWNHUB_API_KEY
uv venv && source .venv/bin/activate
uv pip install -e .
python multi_agent_pipeline.py "quantum computing"
```

### `crewai/` — CrewAI multi-agent research pipeline

A 3-agent pipeline (Orchestrator → ResearchAgent → AnalystAgent) using CrewAI. Uses native OTEL — no SpawnHub SDK needed.

```bash
cd crewai
cp .env.example .env
uv venv && source .venv/bin/activate
uv pip install -e .
python pipeline.py "quantum computing"
```

### `autogen/` — AutoGen multi-agent research pipeline

A 3-agent pipeline (Orchestrator → ResearchAgent → WriterAgent) using Microsoft AutoGen. Uses native OTEL — no SpawnHub SDK needed.

```bash
cd autogen
cp .env.example .env
uv venv && source .venv/bin/activate
uv pip install -e .
python pipeline.py "quantum computing"
```

### `google-adk/` — Google ADK multi-agent research pipeline

A 3-agent pipeline (Orchestrator → ResearchAgent → WriterAgent) using Google's Agent Development Kit with Gemini. Uses native OTEL via `GOOGLE_GENAI_OBSERVABILITY_ENABLED=true`.

```bash
cd google-adk
cp .env.example .env          # add your GOOGLE_API_KEY + SPAWNHUB_API_KEY
uv venv && source .venv/bin/activate
uv pip install -e .
python pipeline.py "quantum computing"
```

### `semantic-kernel/` — Semantic Kernel multi-agent research pipeline

A 3-agent pipeline (Orchestrator → ResearchAgent → WriterAgent) using Microsoft Semantic Kernel. Uses native OTEL via `SEMANTICKERNEL_EXPERIMENTAL_GENAI_ENABLE_OTEL_DIAGNOSTICS=true`.

```bash
cd semantic-kernel
cp .env.example .env
uv venv && source .venv/bin/activate
uv pip install -e .
python pipeline.py "quantum computing"
```

## Ingestion endpoints (Docker stack)

| Path | Auth | Used by |
|---|---|---|
| `POST http://ingest.localhost/v1/traces` | `X-SpawnHub-Key` header | LangGraph, CrewAI, AutoGen, Google ADK, Semantic Kernel |
| `POST http://ingest.localhost/v1/events` | `X-SpawnHub-Key` header | OpenAI Agents SDK adapter |
| `ws://ingest.localhost/ws` | none | Renderer (read-only live stream) |

## How it works

Each agent run streams [OpenTelemetry](https://opentelemetry.io/) spans to SpawnHub's ingestion endpoint. SpawnHub maps spans to game events and renders them as animated avatars in the browser in real time.

| OTEL span | SpawnHub event | What you see |
|---|---|---|
| `invoke_agent` | Agent spawns | Avatar appears in the world |
| LLM completion | Agent thinks | Thinking animation |
| Tool call | Agent acts | Action animation |
| Span end | Agent completes | Avatar idles / despawns |
