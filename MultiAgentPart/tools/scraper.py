from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

import requests
import threading
import ipaddress
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from langchain_core.tools import tool

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}
_thread_local = threading.local()

def _get_session() -> requests.Session:
    """Lazy-init a thread-local requests Session for thread safety."""
    if not hasattr(_thread_local, "session"):
        _thread_local.session = requests.Session()
        _thread_local.session.headers.update(DEFAULT_HEADERS)
    return _thread_local.session

def _is_url_safe(url: str) -> bool:
    """Basic SSRF protection: block private IPs and non-HTTP schemes."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        
        # Block obvious dangerous hosts
        if hostname.lower() in ("localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254"):
            return False
            
        # Try to detect private IPs
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
        except ValueError:
            pass  # hostname is not an IP, DNS resolution needed for full check
            
        return True
    except Exception:
        return False
def scrape_one(url : str, timeout: int = 8,max_chars: int =3000)-> str:
    """
    Scrape and clean one URL.
    """
    if not _is_url_safe(url):
        raise ValueError(f"URL blocked for security reasons: {url}")
    
    response = _get_session().get(url, timeout=timeout)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, "lxml")    
    for tag in soup(["script", "style", "header", "footer", "nav", "noscript"]):
        tag.extract()
    text = soup.get_text(separator = " ")
    clean_text= " ".join(text.split())
    return clean_text[:max_chars]



def scrape_many_parallel(urls: List[str], max_workers: int = 6) -> Dict[str, str]:
    """
    Parallel scrape URLs using ThreadPoolExecutor.
    Results are returned by URL key. Completion order is handled with as_completed.
    """
    if not urls:
        return {}

    results: Dict[str, str] = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(scrape_one, url): url
            for url in urls
        }

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                results[url] = future.result()
            except Exception as exc:
                results[url] = f"ERROR scraping {url}: {exc}"

    return results

@tool
def parallel_scraper_tool(urls: List[str]) -> str:
    """
    Tool wrapper for parallel scraping.
    Returns labeled content by URL in one combined text blob.
    """
    data = scrape_many_parallel(urls=urls, max_workers=min(8, max(1, len(urls))))

    blocks = []
    for url, content in data.items():
        blocks.append(f"Source: {url}\n{content}")

    return "\n\n".join(blocks)