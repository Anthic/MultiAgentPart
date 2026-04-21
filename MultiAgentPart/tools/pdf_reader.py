"""
pdf_reader.py
────────────────────────────────────────────────────────────
Reads academic PDFs — especially from arXiv — and extracts clean text.

Supports:
  • arXiv abstract pages  (auto-converts to PDF URL)
  • Direct PDF URLs       (https://.../paper.pdf)
  • Local PDF file paths  (C:/papers/paper.pdf)

Dependencies:
  pip install pypdf httpx
"""

import io
import logging
import os
import re
from typing import Optional

import httpx

log = logging.getLogger(__name__)

_ARXIV_ABS_RE = re.compile(r"arxiv\.org/abs/(\d{4}\.\d+)", re.IGNORECASE)
_ARXIV_PDF_RE = re.compile(r"arxiv\.org/pdf/(\d{4}\.\d+)", re.IGNORECASE)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0; +https://arxiv.org)",
}


def _arxiv_to_pdf_url(url: str) -> str:
    """Convert an arXiv abstract URL to the direct PDF download URL."""
    m = _ARXIV_ABS_RE.search(url)
    if m:
        return f"https://arxiv.org/pdf/{m.group(1)}.pdf"
    return url  # already a pdf url or something else


def read_pdf_from_url(url: str, max_chars: int = 8000) -> str:
    """
    Download and extract text from a PDF at `url`.

    Returns extracted text (up to max_chars), or an error string.
    """
    try:
        from pypdf import PdfReader       # type: ignore
    except ImportError:
        return "ERROR: pypdf not installed. Run: pip install pypdf"

    pdf_url = _arxiv_to_pdf_url(url)
    log.info("PDFReader: fetching %s", pdf_url)

    try:
        response = httpx.get(pdf_url, headers=_HEADERS, timeout=20, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("PDFReader: HTTP error for %s — %s", pdf_url, exc)
        return f"ERROR fetching PDF: {exc}"

    try:
        reader = PdfReader(io.BytesIO(response.content))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages_text.append(text)
        combined = "\n".join(pages_text)
        clean = " ".join(combined.split())   # normalise whitespace
        log.info("PDFReader: extracted %d chars from %s", len(clean), pdf_url)
        return clean[:max_chars]
    except Exception as exc:
        log.exception("PDFReader: failed to parse PDF from %s", pdf_url)
        return f"ERROR parsing PDF: {exc}"


def read_pdf_from_file(path: str, max_chars: int = 8000) -> str:
    """Extract text from a local PDF file."""
    try:
        from pypdf import PdfReader       # type: ignore
    except ImportError:
        return "ERROR: pypdf not installed. Run: pip install pypdf"

    if not os.path.isfile(path):
        return f"ERROR: File not found: {path}"

    try:
        reader = PdfReader(path)
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
        clean = " ".join(text.split())
        log.info("PDFReader: extracted %d chars from %s", len(clean), path)
        return clean[:max_chars]
    except Exception as exc:
        log.exception("PDFReader: failed to parse %s", path)
        return f"ERROR parsing PDF: {exc}"


def smart_pdf_read(source: str, max_chars: int = 8000) -> str:
    """
    Auto-detect whether source is a URL or local path and read accordingly.
    """
    if source.startswith("http://") or source.startswith("https://"):
        return read_pdf_from_url(source, max_chars=max_chars)
    return read_pdf_from_file(source, max_chars=max_chars)


def is_arxiv_url(url: str) -> bool:
    """Check if a URL points to an arXiv paper."""
    return bool(_ARXIV_ABS_RE.search(url) or _ARXIV_PDF_RE.search(url))
