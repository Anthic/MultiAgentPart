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
log = logging.getLogger(__name__)


class ResearchState(TypedDict):
    topic: str
    search_results: str
    verified_urls: List[str]
    urls: List[str]
    scraped_content: str
    rag_context: str
    report: str
    critique: str
    critique_score: int
    retry_count: int
    max_retries: int
    error: str


def parse_score(critique: str) -> int:
    match = re.search(r"Score:\s*(\d+)\s*/\s*10", critique or "", flags=re.IGNORECASE)
    if not match:
        return 0
    score = int(match.group(1))
    return max(0, min(score, 10))


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


def run_critic_and_score(state: dict, critic_chain) -> dict:
    updated = run_critic(state, critic_chain)
    updated["critique_score"] = parse_score(updated.get("critique", ""))
    return updated


def build_pipeline():
    fast_llm = get_llm("fast")
    smart_llm = get_llm("smart")

    search_agent = build_search_agent(fast_llm)
    reader_agent = build_reader_agent()
    writer_chain = build_writer_chain(smart_llm)
    critic_chain = build_critic_chain(fast_llm)

    graph = StateGraph(ResearchState)

    graph.add_node("search", lambda s: run_search_agent(s, search_agent))
    graph.add_node("reader", lambda s: run_reader_agent(s, reader_agent))
    graph.add_node("rag", lambda s: run_rag_node(s))
    graph.add_node("writer", lambda s: run_writer(s, writer_chain))
    graph.add_node("critic", lambda s: run_critic_and_score(s, critic_chain))
    graph.add_node("prepare_rewrite", bump_retry)

    graph.add_edge(START, "search")
    graph.add_edge("search", "reader")
    graph.add_edge("reader", "rag")
    graph.add_edge("rag", "writer")
    graph.add_edge("writer", "critic")

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