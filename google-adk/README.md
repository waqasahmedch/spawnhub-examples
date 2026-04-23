# SpawnHub — Google ADK Example

A 3-agent research pipeline built with **Google Agent Development Kit (ADK)** and Gemini models that streams live telemetry to SpawnHub. Watch three avatars (Orchestrator, ResearchAgent, WriterAgent) appear and animate in the SpawnHub renderer as the pipeline runs.

## How it works

```
Orchestrator  (Yahya  / PK)
├── ResearchAgent (Ibrahim / SA)  — researches the topic using Gemini
└── WriterAgent   (Leila  / IR)  — writes the final report using Gemini
```

Setting `GOOGLE_GENAI_OBSERVABILITY_ENABLED=true` tells ADK to route all `gen_ai.*` spans through the global OTEL provider, which is configured to export directly to SpawnHub.

## Prerequisites

- SpawnHub running (`make infra-up` in the SpawnHub repo)
- Python 3.12+
- Google Gemini API key — get one free at https://aistudio.google.com/app/apikey

## Setup

```bash
cd google-adk
uv venv && source .venv/bin/activate
uv pip install -e .
cp .env.example .env
# Edit .env — set GOOGLE_API_KEY and SPAWNHUB_API_KEY
```

## Run

```bash
python pipeline.py "quantum computing"
```

Open **http://app.localhost** to watch the avatars appear in real time.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | yes | Your Google Gemini API key |
| `SPAWNHUB_ENDPOINT` | no | SpawnHub ingestion base URL (default: `http://ingest.localhost`) |
| `SPAWNHUB_API_KEY` | no | Kong API key — required when using the Docker stack |
