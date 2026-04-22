import json
import logging
from langgraph.prebuilt import create_react_agent
from tools import tavily_search_tool, extract_urls_from_search_output

log = logging.getLogger(__name__)

def build_search_agent(llm):
    return create_react_agent(
        model=llm,
        tools=[tavily_search_tool],
        prompt=(
            "You are a research search specialist. "
            "Given a topic, find recent and high-quality sources. "
            "Return raw results with title, URL, and snippet."
        ),
    )

def run_search_agent(state: dict, agent) -> dict:
    topic = state.get("topic", "").strip()
    if not topic:
        return {**state, "error": "Topic is empty."}

    try:
        result = agent.invoke(
            {
                "messages": [
                    {"role": "user", "content": f"Search for topic: {topic}"}
                ]
            }
        )

     
        verified_urls = []
        for msg in result["messages"]:
          
            if hasattr(msg, "tool_calls") or msg.__class__.__name__ == "ToolMessage":
                raw = getattr(msg, "content", "")
                try:
                    tool_data = json.loads(raw)
              
                    if isinstance(tool_data, list):
                        for item in tool_data:
                            if isinstance(item, dict) and "url" in item:
                                verified_urls.append(item["url"])
                except (json.JSONDecodeError, TypeError):
                    pass  

      
        messages = result.get("messages", [])
        if not messages:
            log.warning("No messages returned from search agent")
            return {**state, "search_results": "", "verified_urls": [], "error": "No messages returned"}

        output = messages[-1].content or ""
        if not verified_urls:
            log.warning("Raw tool URLs not found, falling back to extract_urls_from_search_output")
            verified_urls = extract_urls_from_search_output(output, top_k=5)

        verified_urls = list(dict.fromkeys(verified_urls))[:5]

        log.info("Search complete. chars=%d, urls=%d", len(output), len(verified_urls))
        return {**state, "search_results": output, "verified_urls": verified_urls}

    except Exception as exc:
        log.exception("Search failed")
        return {
            **state,
            "search_results": "",
            "verified_urls": [],
            "error": f"Search failed: {exc}",
        }