# SpawnHub — CrewAI Example

A 3-agent research pipeline built with **CrewAI** that streams live telemetry to SpawnHub. Watch three avatars (Orchestrator, ResearchAgent, AnalystAgent) appear and animate in the SpawnHub renderer as the pipeline runs.

## How it works

```
Orchestrator  (Yahya  / PK)
├── ResearchAgent (Ibrahim / SA)  — gathers information on the topic
└── AnalystAgent  (Zainab / TR)  — produces the final structured report
```

Each agent runs as a single-agent Crew wrapped in an `invoke_agent` OTEL span. The global OTEL TracerProvider is configured before CrewAI imports so any native instrumentation CrewAI emits is automatically routed to SpawnHub.

## Prerequisites

- SpawnHub running (`make infra-up` in the SpawnHub repo)
- Python 3.12+
- OpenAI API key

## Setup

```bash
cd crewai
uv venv && source .venv/bin/activate
uv pip install -e .
cp .env.example .env
# Edit .env — set OPENAI_API_KEY and SPAWNHUB_API_KEY
```

## Run

```bash
python pipeline.py "quantum computing"
```

Open **http://app.localhost** to watch the avatars appear in real time.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | yes | Your OpenAI API key |
| `SPAWNHUB_ENDPOINT` | no | SpawnHub ingestion base URL (default: `http://ingest.localhost`) |
| `SPAWNHUB_API_KEY` | no | Kong API key — required when using the Docker stack |
