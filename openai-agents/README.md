# OpenAI Agents SDK Pipeline — SpawnHub Example

A 3-agent research pipeline using the OpenAI Agents SDK, streamed to SpawnHub via the `spawnhub-openai-agents` adapter.

## Agents

| Agent | Persona | Role |
|---|---|---|
| Orchestrator | Zara (AE) | Coordinates handoffs |
| ResearchAgent | Ibrahim (SA) | Web search |
| WriterAgent | Leila (IR) | Report writing |

## Prerequisites

SpawnHub Docker stack running:
```bash
# In the spawnhub repo:
make infra-up
# Open http://app.localhost in browser
```

## Setup

```bash
cp .env.example .env
# Edit .env — set OPENAI_API_KEY and SPAWNHUB_API_KEY
# SPAWNHUB_API_KEY for local dev: spwnhub_dev_key_replace_me (see infra/kong/kong.yml)

uv pip install -e .
```

## Run

```bash
python multi_agent_pipeline.py "quantum computing"
```

Watch the avatars appear in real time at **http://app.localhost**.

## Why an adapter?

The OpenAI Agents SDK uses internal hooks rather than emitting native OpenTelemetry spans. The `spawnhub-openai-agents` adapter bridges this gap — it hooks into the SDK's tracing system and posts `GameEvent`s directly to SpawnHub's `/v1/events` endpoint.

The adapter reads `SPAWNHUB_ENDPOINT` and `SPAWNHUB_API_KEY` from the environment, which are passed through `instrument()` in `multi_agent_pipeline.py`.
