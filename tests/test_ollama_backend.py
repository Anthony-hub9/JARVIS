from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jarvis.agents.orchestrator import OllamaBackend


@pytest.mark.asyncio
async def test_ollama_backend_generate():
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "Hola desde Ollama"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        backend = OllamaBackend(base_url="http://localhost:11434/")
        result = await backend.generate("qwen2.5:7b", "Hola")

    assert result == "Hola desde Ollama"
    assert backend.timeout == 180.0
    mock_client.post.assert_awaited_once_with(
        "http://localhost:11434/api/generate",
        json={
            "model": "qwen2.5:7b",
            "prompt": "Hola",
            "stream": False,
            "keep_alive": "15m",
            "options": {"num_predict": 512, "num_ctx": 8192, "repeat_penalty": 1.15},
        },
    )


@pytest.mark.asyncio
async def test_ollama_backend_generate_with_images():
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "Enemigo al frente, poca munición."}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        backend = OllamaBackend(base_url="http://localhost:11434")
        result = await backend.generate("moondream", "Analiza el frame", images=["ZmFrZQ=="])

    assert result == "Enemigo al frente, poca munición."
    mock_client.post.assert_awaited_once_with(
        "http://localhost:11434/api/generate",
        json={
            "model": "moondream",
            "prompt": "Analiza el frame",
            "stream": False,
            "keep_alive": "15m",
            "options": {"num_predict": 512, "num_ctx": 8192, "repeat_penalty": 1.15},
            "images": ["ZmFrZQ=="],
        },
    )
