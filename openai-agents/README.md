# OpenAI Agents SDK Pipeline — SpawnHub Example

A 3-agent research pipeline using the OpenAI Agents SDK, streamed to SpawnHub via the `spawnhub-openai-agents` adapter.

## Agents

| Agent | Persona | Role |
|---|---|---|
| Orchestrator | Zara (AE) | Coordinates handoffs |
| ResearchAgent | Ibrahim (SA) | Web search |
| WriterAgent | Leila (IR) | Report writing |

## Setup

```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

pip install -e .
```

## Run

```bash
python multi_agent_pipeline.py "quantum computing"
```

## Why an adapter?

The OpenAI Agents SDK uses internal hooks rather than emitting native OpenTelemetry spans. The `spawnhub-openai-agents` adapter bridges this gap — it hooks into the SDK's tracing system and posts `GameEvent`s directly to SpawnHub's `/v1/events` endpoint.
