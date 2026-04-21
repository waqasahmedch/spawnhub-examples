"""
OpenAI Agents SDK — SpawnHub multi-agent demo pipeline.

Architecture
────────────
    Orchestrator
    ├── ResearchAgent   — searches for information on a topic
    └── WriterAgent     — drafts a concise report from the research

Run
────────────
    # 1. Start SpawnHub Docker stack (from spawnhub repo)
    make infra-up

    # 2. Open http://app.localhost in browser and choose a theme

    # 3. Copy .env.example -> .env, set OPENAI_API_KEY and SPAWNHUB_API_KEY
    cp .env.example .env

    # 4. Run this pipeline
    python multi_agent_pipeline.py "artificial intelligence in healthcare"

Requirements
────────────
    pip install -e .
    # or: pip install spawnhub[openai]
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from spawnhub import instrument

# Register SpawnHub before any agent/runner imports
processor = instrument(
    endpoint=os.getenv("SPAWNHUB_ENDPOINT", "http://ingest.localhost"),
    api_key=os.getenv("SPAWNHUB_API_KEY", ""),
    pattern="orchestrator",
    personas={
        "Orchestrator":  {"name": "Zara",   "country": "AE", "gender": "female"},
        "ResearchAgent": {"name": "Ibrahim", "country": "SA", "gender": "male"},
        "WriterAgent":   {"name": "Leila",   "country": "IR", "gender": "female"},
    },
)

from agents import Agent, Runner, function_tool  # noqa: E402  (import after instrument)


# ── Tools ──────────────────────────────────────────────────────────────────────

@function_tool
def web_search(query: str) -> str:
    """Search the web for information on a topic."""
    # Stub — replace with a real search API in production
    return (
        f"[Simulated search results for '{query}']\n"
        "• Finding 1: Recent studies show significant progress in this area.\n"
        "• Finding 2: Key players include several major research institutions.\n"
        "• Finding 3: The latest developments point to promising applications."
    )


@function_tool
def write_report(topic: str, research_summary: str) -> str:
    """Compile research into a structured report."""
    return (
        f"# Report: {topic}\n\n"
        f"## Summary\n{research_summary}\n\n"
        "## Conclusion\nBased on the research above, this area shows strong potential.\n"
    )


# ── Agents ─────────────────────────────────────────────────────────────────────

def build_research_agent() -> Agent:
    return Agent(
        name="ResearchAgent",
        instructions=(
            "You are a research specialist. Use web_search to gather information "
            "on the given topic (search at least twice with different angles). "
            "Return a concise 2-3 sentence summary of your findings."
        ),
        tools=[web_search],
    )


def build_writer_agent() -> Agent:
    return Agent(
        name="WriterAgent",
        instructions=(
            "You are a professional report writer. Given a topic and research summary, "
            "use write_report to produce a clear, structured report. "
            "Always call write_report — do not write the report inline."
        ),
        tools=[write_report],
    )


def build_orchestrator(researcher: Agent, writer: Agent) -> Agent:
    return Agent(
        name="Orchestrator",
        instructions=(
            "You are an orchestrator managing a research pipeline. "
            "1. Hand off to ResearchAgent to gather information on the topic. "
            "2. Hand off to WriterAgent to produce the final report. "
            "Return the final report to the user."
        ),
        handoffs=[researcher, writer],
    )


# ── Runner ─────────────────────────────────────────────────────────────────────

async def run_pipeline(topic: str) -> str:
    researcher  = build_research_agent()
    writer      = build_writer_agent()
    orchestrator = build_orchestrator(researcher, writer)

    print(f"\n[Pipeline] Starting research on: {topic!r}\n")
    result = await Runner.run(orchestrator, f"Research and report on: {topic}")

    # Flush remaining events before the process exits
    processor.force_flush()
    return result.final_output


if __name__ == "__main__":
    topic = sys.argv[1] if len(sys.argv) > 1 else "artificial intelligence in healthcare"

    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set.")
        sys.exit(1)

    report = asyncio.run(run_pipeline(topic))
    print("\n" + "=" * 60)
    print(report)
    print("=" * 60)
