"""
Sample agent HTTP server — runs on port 8001.

Emits OTEL traces to SpawnHub ingestion (port 8000) automatically.

Usage:
    # Start SpawnHub first:
    uvicorn spawnhub_ingestion.main:app --port 8000 --reload

    # Then start this:
    python -m sample_agent.main

    # Trigger a research run:
    curl -X POST http://localhost:8001/run \
         -H "Content-Type: application/json" \
         -d '{"topic": "artificial intelligence trends 2026"}'

Environment:
    OPENAI_API_KEY      Required — used by the LangChain agent
    SPAWNHUB_ENDPOINT   OTLP endpoint (default: http://localhost:8000/v1/traces)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

# Load .env from the package directory before anything else
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

# Telemetry MUST be set up before any LangChain imports are resolved
from sample_agent.telemetry import setup as setup_telemetry

setup_telemetry(
    otlp_endpoint=os.getenv("SPAWNHUB_ENDPOINT", "http://localhost:8000/v1/traces")
)

import uvicorn  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from sample_agent.agent import run_research  # noqa: E402
from sample_agent.pipeline import run_pipeline  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SpawnHub Sample Agent",
    description="LangGraph research agent that emits OTEL traces to SpawnHub",
    version="0.1.0",
)


class RunRequest(BaseModel):
    topic: str


class RunResponse(BaseModel):
    topic: str
    answer: str


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "spawnhub_endpoint": os.getenv("SPAWNHUB_ENDPOINT", "http://localhost:8000/v1/traces")}


@app.post("/run", response_model=RunResponse)
async def run(req: RunRequest) -> RunResponse:
    """Single ResearchAgent run (original)."""
    if not req.topic.strip():
        raise HTTPException(status_code=422, detail="topic must not be empty")
    logger.info("POST /run — topic: %s", req.topic)
    answer = await run_research(req.topic)
    return RunResponse(topic=req.topic, answer=answer)


@app.post("/run-pipeline", response_model=RunResponse)
async def run_multi(req: RunRequest) -> RunResponse:
    """
    Multi-agent pipeline: Orchestrator → ResearchAgent → AnalystAgent.
    Spawns 3 avatars in SpawnHub with parent-child relationships.
    """
    if not req.topic.strip():
        raise HTTPException(status_code=422, detail="topic must not be empty")
    logger.info("POST /run-pipeline — topic: %s", req.topic)
    report = await run_pipeline(req.topic)
    return RunResponse(topic=req.topic, answer=report)


if __name__ == "__main__":
    uvicorn.run(
        "sample_agent.main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,  # reload=True breaks OTEL setup (re-runs module-level code)
        log_level="info",
    )
