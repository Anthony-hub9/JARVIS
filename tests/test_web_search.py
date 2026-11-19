from __future__ import annotations

from unittest.mock import MagicMock, patch

from jarvis.tools.web_search import WebSearchTool


def test_web_search_returns_normalized_results() -> None:
    fake_client = MagicMock()
    fake_client.text.return_value = [
        {
            "title": "Python 3.12 Release",
            "body": "Python 3.12 brings performance improvements.",
            "href": "https://python.org/3.12",
        },
        {
            "title": "FastAPI Docs",
            "body": "Modern web framework for Python.",
            "href": "https://fastapi.tiangolo.com",
        },
        {
            "title": "Extra Result",
            "body": "Should be sliced out if > max_results.",
            "href": "https://example.com",
        },
    ]

    with patch("ddgs.DDGS", return_value=fake_client) as ddgs_cls:
        tool = WebSearchTool(timeout=5)
        results = tool.search("python 3.12", max_results=2)

    ddgs_cls.assert_called_once_with(timeout=5)
    fake_client.text.assert_called_once_with("python 3.12", max_results=2)
    assert results == [
        {
            "title": "Python 3.12 Release",
            "snippet": "Python 3.12 brings performance improvements.",
            "url": "https://python.org/3.12",
        },
        {
            "title": "FastAPI Docs",
            "snippet": "Modern web framework for Python.",
            "url": "https://fastapi.tiangolo.com",
        },
    ]


def test_web_search_handles_empty_query_and_errors() -> None:
    tool = WebSearchTool()
    assert tool.search("   ") == []
    assert tool.search("python", max_results=0) == []

    failing_client = MagicMock()
    failing_client.text.side_effect = TimeoutError("DuckDuckGo timeout")
    with patch("ddgs.DDGS", return_value=failing_client):
        assert tool.search("clima cdmx") == []


def test_web_search_format_spoken_summary() -> None:
    assert "No encontré resultados" in WebSearchTool.format_spoken_summary("x", [])
    summary = WebSearchTool.format_spoken_summary(
        "clima",
        [{"title": "CDMX", "snippet": "22°C soleado", "url": "https://example.com"}],
    )
    assert "CDMX: 22°C soleado" in summary
