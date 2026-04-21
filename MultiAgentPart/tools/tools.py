import re
from typing import List
from dotenv import load_dotenv
from langchain_tavily import TavilySearch

load_dotenv()

# Use TavilySearch (updated) — max_results replaces deprecated k param
tavily_search_tool = TavilySearch(max_results=5)
_URL_PATTERN = re.compile(r"https?://[^\s\]\)\}\>,\"']+")

def extract_urls_from_search_output(
    search_text: str,
    top_k: int = 3,
    top_K: int | None = None,
) -> List[str]:
    """
    Extract URLs from raw tool output text and keep only unique top-k links.

    Supports both top_k and legacy top_K for compatibility.
    """
    if not search_text:
        return []

    limit = top_K if top_K is not None else top_k

    found =  _URL_PATTERN.findall(search_text)
    unique = []
    seen = set()
    
    for url in found :
        normalized = url.strip().rstrip(".,);")  
        if normalized not in seen :
            seen.add(normalized)
            unique.append(normalized)
        if len(unique) >= limit:
            break
    return unique