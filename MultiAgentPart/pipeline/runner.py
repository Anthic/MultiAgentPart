"""
pipeline/runner.py
────────────────────────────────────────────────────────────
Full upgraded pipeline with new nodes:

  START
    → query_rewrite   ← expands raw topic into targeted queries
    → search          ← Tavily search (uses best rewritten query)
    → reader          ← parallel scrape verified URLs
    → summarize       ← condense noisy scraped content
    → rag             ← Chroma vector similarity retrieval
    → fact_check      ← verify report claims vs. sources  (post-writer)
    → writer          ← write grounded report
    → fact_check      ← verify claims in report
    → critic          ← score & feedback loop
    → END  (or rewrite loop)
"""

import logging
import re
from typing import TypedDict, List

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END

from agents import (
    build_search_agent,
    run_search_agent,
    build_reader_agent,
    run_reader_agent,
    run_query_rewrite_node,
    run_summarizer_node,
    run_fact_check_node,
)
from pipeline.model import get_llm
from pipeline.rag import run_rag_node
from pipeline.chains import (
    build_writer_chain,
    run_writer,
    build_critic_chain,
    run_critic,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.WARNING)
log = logging.getLogger(__name__)


# ── State ─────────────────────────────────────────────────────────────────────

class ResearchState(TypedDict):
    # Input
    topic: str
    # Query rewrite
    rewritten_queries: List[str]
    search_topic: str           # best rewritten query used for search
    # Search
    search_results: str
    verified_urls: List[str]
    urls: List[str]
    # Scrape + summarise
    scraped_content: str
    summarized_content: str     # condensed scraped content
    # RAG
    rag_context: str
    # Writer / critic loop
    report: str
    critique: str
    critique_score: int
    retry_count: int
    max_retries: int
    # Fact-check
    fact_check_result: str
    fact_check_score: float
    # Meta
    error: str


# ── Score parser ──────────────────────────────────────────────────────────────

def parse_score(critique: str) -> int:
    match = re.search(
        r"score\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*/\s*10",
        critique or "",
        flags=re.IGNORECASE,
    )
    if not match:
        return 0
    return max(0, min(10, round(float(match.group(1)))))


# ── Router ────────────────────────────────────────────────────────────────────

def route_after_critic(state: ResearchState) -> str:
    score = state.get("critique_score", 0)
    retries = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 1)

    if score >= 8:
        return "end"
    if retries < max_retries:
        return "rewrite"
    return "end"


def bump_retry(state: ResearchState) -> ResearchState:
    return {
        **state,
        "retry_count": state.get("retry_count", 0) + 1,
    }


# ── Node wrappers ─────────────────────────────────────────────────────────────

def run_critic_and_score(state: dict, critic_chain) -> dict:
    truncated_state = {**state, "report": state.get("report", "")[:3000]}
    updated = run_critic(truncated_state, critic_chain)
    updated["critique_score"] = parse_score(updated.get("critique", ""))
    return updated


def run_search_with_rewritten(state: dict, search_agent) -> dict:
    """Use search_topic (rewritten) instead of raw topic if available."""
    effective_topic = state.get("search_topic") or state.get("topic", "")
    patched_state = {**state, "topic": effective_topic}
    result = run_search_agent(patched_state, search_agent)
    # Restore original topic so downstream nodes still see it
    return {**result, "topic": state.get("topic", effective_topic)}


# ── Pipeline builder ──────────────────────────────────────────────────────────

def build_pipeline():
    fast_llm = get_llm("fast")
    smart_llm = get_llm("smart")

    search_agent = build_search_agent(fast_llm)
    reader_agent = build_reader_agent()
    writer_chain = build_writer_chain(smart_llm)
    critic_chain = build_critic_chain(fast_llm)

    graph = StateGraph(ResearchState)

    # ── Nodes ──────────────────────────────────────────────────────────────
    graph.add_node("query_rewrite", lambda s: run_query_rewrite_node(s, fast_llm))
    graph.add_node("search",        lambda s: run_search_with_rewritten(s, search_agent))
    graph.add_node("reader",        lambda s: run_reader_agent(s, reader_agent))
    graph.add_node("summarize",     lambda s: run_summarizer_node(s, fast_llm))
    graph.add_node("rag",           lambda s: run_rag_node(s))
    graph.add_node("writer",        lambda s: run_writer(s, writer_chain))
    graph.add_node("fact_check",    lambda s: run_fact_check_node(s, fast_llm))
    graph.add_node("critic",        lambda s: run_critic_and_score(s, critic_chain))
    graph.add_node("prepare_rewrite", bump_retry)

    # ── Edges ───────────────────────────────────────────────────────────────
    graph.add_edge(START,             "query_rewrite")
    graph.add_edge("query_rewrite",   "search")
    graph.add_edge("search",          "reader")
    graph.add_edge("reader",          "summarize")
    graph.add_edge("summarize",       "rag")
    graph.add_edge("rag",             "writer")
    graph.add_edge("writer",          "fact_check")
    graph.add_edge("fact_check",      "critic")

    graph.add_conditional_edges(
        "critic",
        route_after_critic,
        {
            "rewrite": "prepare_rewrite",
            "end": END,
        },
    )
    graph.add_edge("prepare_rewrite", "writer")

    return graph.compile()