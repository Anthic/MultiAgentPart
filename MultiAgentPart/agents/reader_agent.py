import logging
from tools import extract_urls_from_search_output, parallel_scraper_tool

log = logging.getLogger(__name__)

def build_reader_agent():
    """
    Reader does deterministic parsing + parallel scraper tool call.
    Kept as a builder for interface consistency.
    """
    return {"name": "deterministic_reader"}

def run_reader_agent(state: dict, _reader) -> dict:
    """
    Extract top URLs from search output and scrape them in parallel.
    """
    if state.get("error"):
        return {**state, "scraped_content": ""}

    search_text = state.get("search_results", "")
    urls = extract_urls_from_search_output(search_text, top_k=3)

    if not urls:
        return {
            **state,
            "urls": [],
            "scraped_content": "",
            "error": state.get("error") or "No URLs found in search output.",
        }

    try:
        combined = parallel_scraper_tool.invoke({"urls": urls})
        log.info("Reader scraped %d urls", len(urls))
        return {**state, "urls": urls, "scraped_content": combined}
    except Exception as exc:
        log.exception("Reader failed")
        return {
            **state,
            "urls": urls,
            "scraped_content": "",
            "error": f"Reader failed: {exc}",
        }