# LangGraph Multi-Agent Pipeline — SpawnHub Example

A 3-agent research pipeline built with LangGraph's ReAct pattern that streams live telemetry to SpawnHub via native OpenTelemetry.

## Agents

| Agent | Persona | Role |
|---|---|---|
| Orchestrator | Yahya (PK) | Coordinates the pipeline |
| ResearchAgent | Ibrahim (SA) | Web search + information gathering |
| AnalystAgent | Zainab (TR) | Fact extraction + report writing |

## Setup

```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY

pip install -e .
```

## Run

```bash
# Start the agent server (port 8001)
python -m sample_agent.main

# Single agent run
curl -X POST http://localhost:8001/run \
     -H "Content-Type: application/json" \
     -d '{"topic": "AI in healthcare"}'

# Full 3-agent pipeline
curl -X POST http://localhost:8001/run-pipeline \
     -H "Content-Type: application/json" \
     -d '{"topic": "AI in healthcare"}'
```

## How OTEL is wired

- `telemetry.py` — configures the OTLP exporter pointing at SpawnHub
- `otel_callback.py` — LangChain callback handler that emits LLM + tool spans
- `agent.py` / `pipeline.py` — manually start `invoke_agent` spans; callbacks handle child spans

No SpawnHub SDK is needed — standard OTEL spans with GenAI semantic conventions are all SpawnHub requires.
