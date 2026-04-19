"""
Tools available to the research pipeline agents.

Uses mock implementations so the demo runs without external API keys or
internet access. Swap web_search for a real provider (Tavily, DuckDuckGo)
when you want live results.
"""

from __future__ import annotations

from langchain_core.tools import tool

_MOCK_SEARCH_DB: dict[str, str] = {
    "default": (
        "Recent developments show significant progress across multiple fronts. "
        "Key findings include: (1) improved performance benchmarks, "
        "(2) wider industry adoption, and (3) new open-source contributions. "
        "Experts predict continued growth through 2026 and beyond."
    ),
    "ai": (
        "AI research in 2026 is dominated by multi-modal models, agentic systems, "
        "and efficient inference. Major labs (Anthropic, OpenAI, Google DeepMind) "
        "have released frontier models with extended context windows. "
        "Open-source alternatives (Llama, Mistral, Qwen) are closing the capability gap. "
        "Key challenges remain: alignment, hallucination, and energy consumption."
    ),
    "quantum": (
        "Quantum computing reached a major milestone in 2026 with 1,000+ qubit processors. "
        "IBM and Google are leading commercial deployments. Error correction has improved "
        "dramatically via surface codes. Quantum advantage demonstrated in drug discovery "
        "and cryptography. Post-quantum cryptography standards finalized by NIST."
    ),
    "python": (
        "Python 3.13 introduced significant performance improvements via the 'no-GIL' "
        "experimental mode. The ecosystem continues to dominate data science and AI "
        "tooling. Popular frameworks: FastAPI, Pydantic v2, uv (package manager), "
        "Ruff (linter). WASM compilation is gaining traction for edge deployments."
    ),
    "space": (
        "Space exploration in 2026 includes Artemis lunar base construction, Mars sample "
        "return missions, and commercial LEO stations. SpaceX Starship operational for "
        "cargo. ESA and JAXA expanding deep-space programs. Asteroid mining permits "
        "issued under new international framework."
    ),
    "climate": (
        "Climate data shows 1.4°C warming above pre-industrial levels. Renewable energy "
        "now 42% of global electricity. Carbon capture at scale deployed in 15 countries. "
        "Extreme weather events up 28% vs 2020. Green hydrogen emerging as key "
        "decarbonization vector for heavy industry."
    ),
}


def _mock_search(query: str) -> str:
    query_lower = query.lower()
    for keyword, result in _MOCK_SEARCH_DB.items():
        if keyword in query_lower:
            return f"[Web results for '{query}']\n\n{result}"
    return f"[Web results for '{query}']\n\n{_MOCK_SEARCH_DB['default']}"


@tool
def web_search(query: str) -> str:
    """Search the web for recent news and information about a topic.

    Args:
        query: The search query string.

    Returns:
        A string with relevant search results.
    """
    return _mock_search(query)


@tool
def get_key_facts(topic: str, max_facts: int = 5) -> str:
    """Extract and return the most important facts about a topic from available sources.

    Args:
        topic: The subject to find facts about.
        max_facts: Maximum number of facts to return (default 5).

    Returns:
        A numbered list of key facts.
    """
    base = _mock_search(topic)
    facts = [
        f"Fact 1 about {topic}: Based on recent research, this field is rapidly evolving.",
        f"Fact 2 about {topic}: Multiple peer-reviewed studies confirm core principles.",
        f"Fact 3 about {topic}: Industry adoption has grown 40% year-over-year.",
        f"Fact 4 about {topic}: Leading organizations are investing heavily in this area.",
        f"Fact 5 about {topic}: Open-source contributions are accelerating innovation.",
    ]
    return "\n".join(facts[:max_facts]) + f"\n\nSource context:\n{base[:300]}..."


@tool
def write_report(topic: str, research_summary: str, key_facts: str) -> str:
    """Synthesize research and facts into a structured final report.

    Args:
        topic: The subject of the report.
        research_summary: Narrative research findings from the research phase.
        key_facts: Structured fact list from the analysis phase.

    Returns:
        A formatted report with executive summary, findings, and conclusion.
    """
    return (
        f"# Report: {topic}\n\n"
        f"## Executive Summary\n"
        f"This report synthesizes recent findings on {topic} based on web research "
        f"and structured fact extraction.\n\n"
        f"## Key Findings\n{key_facts}\n\n"
        f"## Research Context\n{research_summary[:400]}...\n\n"
        f"## Conclusion\n"
        f"The analysis confirms that {topic} remains a high-priority area with strong "
        f"momentum. Continued monitoring is recommended."
    )
