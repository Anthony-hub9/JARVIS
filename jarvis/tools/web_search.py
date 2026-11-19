from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class WebSearchTool:
    """Free real-time web search using DuckDuckGo (no API key required)."""

    def __init__(self, timeout: int = 8) -> None:
        self.timeout = timeout

    def search(self, query: str, max_results: int = 3) -> list[dict[str, str]]:
        """Search DuckDuckGo and return normalized [{title, snippet, url}] results."""
        clean_query = query.strip()
        if not clean_query or max_results <= 0:
            return []

        try:
            from ddgs import DDGS
        except ImportError:  # pragma: no cover - fallback for older package name
            try:
                from duckduckgo_search import DDGS  # type: ignore[no-redef]
            except ImportError as exc:
                logger.warning("WebSearchTool unavailable: ddgs not installed (%s)", exc)
                return []

        try:
            client = DDGS(timeout=self.timeout)
            raw_results: list[dict[str, Any]] = list(
                client.text(clean_query, max_results=max_results) or []
            )
        except Exception as exc:
            logger.warning("WebSearchTool search failed for %r: %s", clean_query, exc)
            return []

        normalized: list[dict[str, str]] = []
        for item in raw_results[:max_results]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            snippet = str(item.get("body") or item.get("snippet") or "").strip()
            url = str(item.get("href") or item.get("url") or "").strip()
            if title or snippet or url:
                normalized.append({"title": title, "snippet": snippet, "url": url})
        return normalized

    @staticmethod
    def format_spoken_summary(query: str, results: list[dict[str, str]]) -> str:
        """Build a concise fallback spoken summary when LLM summarization is unavailable."""
        if not results:
            return f"No encontré resultados en la web para '{query}'."
        parts = []
        for item in results:
            title = item.get("title", "").strip()
            snippet = item.get("snippet", "").strip()
            if title and snippet:
                parts.append(f"{title}: {snippet}")
            elif title or snippet:
                parts.append(title or snippet)
        return "Resultados web: " + " | ".join(parts)
