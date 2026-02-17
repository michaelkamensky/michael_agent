from __future__ import annotations

from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


def _validate_url(url: str) -> str:
    if not url or not url.strip():
        raise ValueError("url must be a non-empty string.")
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must be an http or https URL with a host.")
    return parsed.geturl()


def fetch_page_text(url: str, timeout_seconds: int = 20) -> dict:
    """
    Fetch a URL and return extracted text in a JSON-serializable dict.
    """
    safe_url = _validate_url(url)
    headers = {
        "User-Agent": "michael_agent/1.0 (+https://example.local)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    response = requests.get(safe_url, headers=headers, timeout=timeout_seconds)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    # Drop scripts/styles and other non-content elements.
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    return {
        "url": safe_url,
        "status_code": response.status_code,
        "content_type": response.headers.get("Content-Type", ""),
        "text": text,
    }
