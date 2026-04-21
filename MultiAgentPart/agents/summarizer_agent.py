"""
summarizer_agent.py
────────────────────────────────────────────────────────────
Condenses long scraped content into focused bullet-point key facts
before it enters the writer chain.

Why it matters
──────────────
Raw scraped pages can be thousands of tokens of boilerplate (nav bars,
ads, repeated headers). Summarising first:
  • Reduces writer prompt size → cheaper & faster
  • Focuses the LLM on signal, not noise
  • Improves citation accuracy
"""

import logging
from typing import Dict

log = logging.getLogger(__name__)

_SUMMARIZE_PROMPT = """\
You are a research extraction specialist.

Given raw web content scraped from multiple sources, extract and organise \
the most relevant facts for the topic provided.

Rules:
- Focus ONLY on information relevant to the topic
- Extract specific data points: numbers, dates, names, statistics
- Group by source URL where possible
- Be concise — bullet points only (max 15 bullets total)
- Discard boilerplate, navigation text, and ads

Topic: {topic}

Raw Content:
{raw_content}

Output format:
### Key Facts
- [Source: <url or "unknown">] <fact>
- ...
"""


def run_summarizer_node(state: Dict, llm) -> Dict:
    """
    LangGraph node: summarises scraped_content into condensed bullet points.

    Adds / updates state:
        summarized_content — condensed key facts (replaces scraped in writer)
    """
    raw: str = state.get("scraped_content", "").strip()
    topic: str = state.get("topic", "").strip()

    if not raw:
        log.warning("Summarizer: no scraped content, skipping")
        return {**state, "summarized_content": ""}

    # Skip summarisation if content is already short enough
    if len(raw) < 1200:
        log.info("Summarizer: content already short (%d chars), skipping", len(raw))
        return {**state, "summarized_content": raw}

    try:
        prompt = _SUMMARIZE_PROMPT.format(
            topic=topic,
            raw_content=raw[:6000],   # cap input to avoid token overflow
        )
        summary: str = llm.invoke(prompt).content.strip()
        log.info("Summarizer: %d chars → %d chars", len(raw), len(summary))
        return {**state, "summarized_content": summary}

    except Exception as exc:
        log.exception("Summarizer failed")
        return {**state, "summarized_content": raw, "error": f"Summarizer failed: {exc}"}
