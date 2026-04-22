"""
pipeline/chains.py
────────────────────────────────────────────────────────────
Writer and Critic LangChain chains with:
  • Stronger grounding prompt (uses summarized_content when available)
  • Streaming-ready (chain.stream() works out of the box via LCEL)
"""

import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

log = logging.getLogger(__name__)

# ── Writer ────────────────────────────────────────────────────────────────────

_writer_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are an expert research writer. Your output will be \
fact-checked, so precision is critical.

STRICT RULES:
1. ONLY use facts from the provided sources below. Never invent data.
2. If a fact is not in the provided context, write "Not found in sources."
3. ONLY cite URLs from the verified_urls list — never modify or create URLs.
4. Every claim must have a [Source N] citation.
5. If sources conflict, mention both and prefer the most recent one.
6. Use clear, professional language. Avoid filler phrases.""",
        ),
        (
            "human",
            """Topic:
{topic}

Key Facts (Summarised):
{summarized_content}

Raw Search Results:
{search_results}

RAG Context:
{rag_context}

{critique_section}

Only use these verified URLs in citations and in the Sources section.
Do NOT generate or modify any URL:
{verified_urls}

Output format:
## Introduction
## Key Findings
### Finding 1
### Finding 2
### Finding 3
## Conclusion
## Sources
""",
        ),
    ]
)

# ── Critic ────────────────────────────────────────────────────────────────────

_critic_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a strict but constructive critic for research reports. "
            "Be precise — your score drives the rewrite loop.",
        ),
        (
            "human",
            """Review the report below and score it.

Report:
{report}

Return exactly:
Score: X/10

Strengths:
- ...

Areas to Improve:
- ...

One line verdict:
...
""",
        ),
    ]
)


# ── Build ─────────────────────────────────────────────────────────────────────

def build_writer_chain(llm):
    """Returns a streaming-compatible LCEL chain."""
    return _writer_prompt | llm | StrOutputParser()


def build_critic_chain(llm):
    """Returns a streaming-compatible LCEL chain."""
    return _critic_prompt | llm | StrOutputParser()


# ── Node runners ──────────────────────────────────────────────────────────────

def run_writer(state: dict, chain) -> dict:
    if state.get("error") and not state.get("scraped_content"):
        return {**state, "report": "", "critique": ""}

    try:
        verified_urls = state.get("verified_urls", [])
        verified_url_text = "\n".join(f"- {url}" for url in verified_urls)

        # Prefer summarized_content if available (better signal-to-noise)
        summarized = state.get("summarized_content", "").strip()
        search_results = state.get("search_results", "")[:2000]
        rag_context = state.get("rag_context", "")[:1500]

        # Build critique feedback section
        critique_feedback = state.get("critique", "")
        critique_section = (
            f"Previous critique — improve based on this feedback:\n{critique_feedback}"
            if critique_feedback else ""
        )

        report = chain.invoke(
            {
                "topic": state.get("topic", ""),
                "summarized_content": summarized or state.get("scraped_content", "")[:4000],
                "search_results": search_results,
                "rag_context": rag_context,
                "critique_section": critique_section,
                "verified_urls": verified_url_text or "- None",
            }
        )
        log.info("Writer: report generated (%d chars)", len(report))
        return {**state, "report": report}

    except Exception as exc:
        log.exception("Writer failed")
        return {**state, "report": "", "error": f"Writer failed: {exc}"}


def run_writer_streaming(state: dict, chain, result_holder: dict = None):
    """
    Generator version of run_writer — yields chunks for CLI streaming.
    Usage:
        result = {}
        for chunk in run_writer_streaming(state, chain, result): 
            print(chunk, end="")
        full_report = result.get("report", "")
    """
    verified_urls = state.get("verified_urls", [])
    verified_url_text = "\n".join(f"- {url}" for url in verified_urls)
    summarized = state.get("summarized_content", "").strip()
    critique_feedback = state.get("critique", "")
    critique_section = (
        f"Previous critique — improve based on this feedback:\n{critique_feedback}"
        if critique_feedback else ""
    )

    inputs = {
        "topic": state.get("topic", ""),
        "summarized_content": summarized or state.get("scraped_content", "")[:4000],
        "search_results": state.get("search_results", "")[:2000],
        "rag_context": state.get("rag_context", "")[:1500],
        "critique_section": critique_section,
        "verified_urls": verified_url_text or "- None",
    }

    full_report = ""
    for chunk in chain.stream(inputs):
        full_report += chunk
        yield chunk

    if result_holder is not None:
        result_holder["report"] = full_report


def run_critic(state: dict, chain) -> dict:
    report = state.get("report", "")
    if not report:
        return {**state, "critique": "No report to critique.", "critique_score": 0}

    try:
        critique = chain.invoke({"report": report})
        log.info("Critic: critique generated (%d chars)", len(critique))
        return {**state, "critique": critique}
    except Exception as exc:
        log.exception("Critic failed")
        return {**state, "critique": "", "critique_score": 0, "error": f"Critic failed: {exc}"}