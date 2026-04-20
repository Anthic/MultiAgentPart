import logging
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

log = logging.getLogger(__name__)

_writer_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            (
                "You are an expert research writer. "
                "Write a factual, well-structured report and cite source URLs inline. "
                "Never invent or alter URLs."
            ),
        ),
        (
            "human",
            """Topic:
{topic}

Raw Search Results:
{search_results}

Scraped Content:
{scraped_content}

RAG Context:
{rag_context}

If critique_feedback is present, improve the report using it:
{critique_feedback}

Only use these verified URLs in citations and in the Sources section.
Do not generate any new URL and do not modify these URLs:
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

_critic_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a strict but constructive critic for research reports.",
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


def build_writer_chain(llm):
    return _writer_prompt | llm | StrOutputParser()


def build_critic_chain(llm):
    return _critic_prompt | llm | StrOutputParser()


def run_writer(state: dict, chain) -> dict:
    if state.get("error") and not state.get("scraped_content"):
        return {**state, "report": "", "critique": ""}

    try:
        verified_urls = state.get("verified_urls", [])
        verified_url_text = "\n".join(f"- {url}" for url in verified_urls)

        report = chain.invoke(
            {
                "topic": state.get("topic", ""),
                "search_results": state.get("search_results", ""),
                "scraped_content": state.get("scraped_content", ""),
                "rag_context": state.get("rag_context", ""),
                "critique_feedback": state.get("critique", ""),
                "verified_urls": verified_url_text or "- None",
            }
        )
        return {**state, "report": report}
    except Exception as exc:
        log.exception("Writer failed")
        return {**state, "report": "", "error": f"Writer failed: {exc}"}


def run_critic(state: dict, chain) -> dict:
    report = state.get("report", "")
    if not report:
        return {**state, "critique": "No report to critique.", "critique_score": 0}

    try:
        critique = chain.invoke({"report": report})
        return {**state, "critique": critique}
    except Exception as exc:
        log.exception("Critic failed")
        return {**state, "critique": "", "critique_score": 0, "error": f"Critic failed: {exc}"}