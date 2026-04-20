import re
from typing import List
from dotenv import load_dotenv
from langchain_community.tools.tavily_search import TavilySearchResults

load_dotenv()

# exsiting tavily tools
tavily_search_tool = TavilySearchResults(k=5)
_URL_PATTERN = re.compile(r"https?://[^\s\]\)\}\>,\"']+")

def extract_urls_from_search_output(search_text : str, top_K : int =3) -> List[str]:
    """
    Extract URLs from raw tool output text and keep only unique top_k links.
    """
    if not search_text:
        return []
    found =  _URL_PATTERN.findall(search_text)
    unique = []
    seen = set()
    
    for url in found :
        normalized = url.strip().rstrip(".,);")  
        if normalized not in seen :
            seen.add(normalized)
            unique.append(normalized)
        if len(unique) >= top_K:
            break
    return unique