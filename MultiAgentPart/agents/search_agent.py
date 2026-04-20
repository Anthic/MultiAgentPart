import logging
from langgraph.prebuilt import create_react_agent
from tools import tavily_search_tool

log = logging.getLogger(__name__)

def build_search_agent(llm):
    """
    Build search agent that uses Tavily.
    """
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
    """
    Execute search agent and write raw search output to state.
    """
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
        output = result["messages"][-1].content
        log.info("Search complete. chars=%d", len(output))
        return {**state, "search_results": output}
    except Exception as exc:
        log.exception("Search failed")
        return {**state, "search_results": "", "error": f"Search failed: {exc}"}