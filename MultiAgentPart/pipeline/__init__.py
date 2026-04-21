"""
pipeline/__init__.py
────────────────────────────────────────────────────────────
Singleton pipeline cache + public run_research() entrypoint.
Auto-saves every completed result to research history.
"""

import time
from .runner import build_pipeline

_compiled_pipeline = None


def run_research(topic: str) -> dict:
    global _compiled_pipeline
    if _compiled_pipeline is None:
        _compiled_pipeline = build_pipeline()

    initial_state = {
        "topic": topic,
        # Query rewrite
        "rewritten_queries": [],
        "search_topic": "",
        # Search
        "search_results": "",
        "verified_urls": [],
        "urls": [],
        # Scrape + summarise
        "scraped_content": "",
        "summarized_content": "",
        # RAG
        "rag_context": "",
        # Writer / critic
        "report": "",
        "critique": "",
        "critique_score": 0,
        "retry_count": 0,
        "max_retries": 1,
        # Fact-check
        "fact_check_result": "",
        "fact_check_score": 0.0,
        # Meta
        "error": "",
    }

    start = time.time()
    final_state = _compiled_pipeline.invoke(initial_state)
    elapsed = round(time.time() - start, 2)

    result = {
        "topic": final_state.get("topic", topic),
        "report": final_state.get("report", ""),
        "critique": final_state.get("critique", ""),
        "critique_score": final_state.get("critique_score", 0),
        "fact_check_score": final_state.get("fact_check_score", 0.0),
        "fact_check_result": final_state.get("fact_check_result", ""),
        "rewritten_queries": final_state.get("rewritten_queries", []),
        "verified_urls": final_state.get("verified_urls", []),
        "error": final_state.get("error", ""),
        "time_sec": elapsed,
    }

    # Persist to history (best-effort — never crash main flow)
    try:
        from memory import save_research
        save_research(result)
    except Exception:
        pass

    return result


__all__ = ["build_pipeline", "run_research"]