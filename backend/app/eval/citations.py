import json
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit


URL_PATTERN = re.compile(r"https?://[^\s<>\[\]{}\"']+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,;:!?)]}，。；：！？）】》"


def extract_urls(value: Any) -> list[str]:
    """Extract unique HTTP(S) URLs from tool output or an agent answer."""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, default=str)
    found: list[str] = []
    for match in URL_PATTERN.findall(value):
        url = match.rstrip(TRAILING_PUNCTUATION)
        if url and url not in found:
            found.append(url)
    return found


def normalize_url(url: str) -> str | None:
    """Return a stable URL identity, or None when it is not a valid web URL."""
    try:
        parts = urlsplit(url)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return None
        if any(char.isspace() for char in url):
            return None
        netloc = parts.hostname.lower()
        if parts.port:
            netloc = f"{netloc}:{parts.port}"
        path = parts.path.rstrip("/") or "/"
        return urlunsplit((parts.scheme.lower(), netloc, path, parts.query, ""))
    except ValueError:
        return None


def citation_report(answer: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    cited_urls = extract_urls(answer)
    source_urls = list(dict.fromkeys(
        url
        for event in events
        for url in event.get("urls", [])
        if isinstance(url, str)
    ))
    normalized_sources = {
        normalized
        for url in source_urls
        if (normalized := normalize_url(url)) is not None
    }
    valid_urls: list[str] = []
    invalid_urls: list[str] = []
    grounded_urls: list[str] = []
    ungrounded_urls: list[str] = []
    for url in cited_urls:
        normalized = normalize_url(url)
        if normalized is None:
            invalid_urls.append(url)
            continue
        valid_urls.append(url)
        if normalized in normalized_sources:
            grounded_urls.append(url)
        else:
            ungrounded_urls.append(url)
    return {
        "cited_urls": cited_urls,
        "source_urls": source_urls,
        "valid_urls": valid_urls,
        "invalid_urls": invalid_urls,
        "grounded_urls": grounded_urls,
        "ungrounded_urls": ungrounded_urls,
        "citation_count": len(cited_urls),
        "valid_ratio": round(len(valid_urls) / max(len(cited_urls), 1), 4),
        "grounded_ratio": round(len(grounded_urls) / max(len(cited_urls), 1), 4),
    }
