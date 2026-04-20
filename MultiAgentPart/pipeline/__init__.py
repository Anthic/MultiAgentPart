import time

from .runner import build_pipeline


def run_research(topic: str) -> dict:
	app = build_pipeline()
	initial_state = {
		"topic": topic,
		"search_results": "",
		"verified_urls": [],
		"urls": [],
		"scraped_content": "",
		"rag_context": "",
		"report": "",
		"critique": "",
		"critique_score": 0,
		"retry_count": 0,
		"max_retries": 1,
		"error": "",
	}

	start = time.time()
	final_state = app.invoke(initial_state)
	elapsed = round(time.time() - start, 2)

	return {
		"topic": final_state.get("topic", topic),
		"report": final_state.get("report", ""),
		"critique": final_state.get("critique", ""),
		"error": final_state.get("error", ""),
		"time_sec": elapsed,
	}


__all__ = ["build_pipeline", "run_research"]