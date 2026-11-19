from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from jarvis.agents.orchestrator import DualAgentOrchestrator, OrchestratorResult
from jarvis.hub.server import app
from jarvis.tools.agenda import AgendaStore
from jarvis.tools.app_control import AppController


class FakeBackend:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.calls: list[tuple[str, str, list[str] | None]] = []

    async def generate(self, model: str, prompt: str, images: list[str] | None = None) -> str:
        self.calls.append((model, prompt, images))
        return next(self._responses)


def test_index_serves_web_client() -> None:
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert "WebSocket" in resp.text
    assert "/ws/" in resp.text
    assert "s24-plus" in resp.text


def test_health_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["backend"] == "ollama"
    assert data["executor"] == "qwen2.5:3b"
    assert data["supervisor"] == "qwen2.5:1.5b"
    assert data["vision"] == "moondream"


def test_websocket_chat_agenda_and_game_frame() -> None:
    store = AgendaStore(":memory:")
    try:
        fake_backend = FakeBackend(
            [
                "Hola, todo listo en local.",
                "APPROVED",
                '{"tool": "agenda_add", "title": "Dentista", "when": "2099-05-01T16:00:00"}',
                "APPROVED",
                "Usa cobertura a la derecha.",
                "APPROVED",
                "¡Cuidado, poca munición y enemigo al flanco!",
                "APPROVED",
                "Sin imagen adjunta, dime qué necesitas.",
                "APPROVED",
            ]
        )
        orchestrator = DualAgentOrchestrator(
            backend=fake_backend,
            agenda_store=store,
            app_controller=AppController(discover=False),
        )

        with patch("jarvis.hub.server.get_orchestrator", return_value=orchestrator):
            client = TestClient(app)
            with client.websocket_connect("/ws/pc_game") as ws:
                ws.send_text("Hola JARVIS")
                chat_resp = ws.receive_json()
                assert chat_resp["approved"] is True
                assert chat_resp["response"] == "Hola, todo listo en local."
                assert chat_resp["tool_result"] is None

                ws.send_text("Agéndame dentista")
                agenda_resp = ws.receive_json()
                assert agenda_resp["approved"] is True
                assert agenda_resp["tool_result"]["event"]["title"] == "Dentista"

                ws.send_text(
                    json.dumps(
                        {
                            "type": "pc_game_satellite",
                            "prompt": "¿Cómo paso este jefe?",
                            "image_base64": "ZmFrZQ==",
                        }
                    )
                )
                sat_resp = ws.receive_json()
                assert sat_resp["approved"] is True
                assert sat_resp["response"] == "Usa cobertura a la derecha."

                ws.send_text(
                    json.dumps(
                        {
                            "type": "game_frame",
                            "prompt": "",
                            "image_base64": "Z2FtZV9mcmFtZQ==",
                        }
                    )
                )
                frame_resp = ws.receive_json()
                assert frame_resp["approved"] is True
                assert frame_resp["response"] == "¡Cuidado, poca munición y enemigo al flanco!"
                # Vision call used vision_model ("moondream") with the decoded base64 list
                assert fake_backend.calls[6][0] == "moondream"
                assert fake_backend.calls[6][2] == ["Z2FtZV9mcmFtZQ=="]

                # game_frame without image must not crash and falls back to text executor
                ws.send_text(json.dumps({"type": "game_frame", "prompt": "¿Qué hago?"}))
                no_img_resp = ws.receive_json()
                assert no_img_resp["approved"] is True
                assert fake_backend.calls[8][0] == "qwen2.5:3b"
                assert fake_backend.calls[8][2] is None
    finally:
        store.close()


def test_websocket_handles_orchestrator_exception_without_dropping() -> None:
    mock_orchestrator = MagicMock()
    mock_orchestrator.run = AsyncMock(
        side_effect=[
            RuntimeError("timed out"),
            OrchestratorResult(response="Recuperado", approved=True, attempts=1),
        ]
    )

    with patch("jarvis.hub.server.get_orchestrator", return_value=mock_orchestrator):
        client = TestClient(app)
        with client.websocket_connect("/ws/pc") as ws:
            ws.send_text("Hola")
            err_resp = ws.receive_json()
            assert err_resp == {
                "device_id": "pc",
                "response": "Error al procesar con Ollama: RuntimeError: timed out",
                "approved": False,
                "attempts": 0,
                "circuit_broken": False,
            }

            # Connection remains open for subsequent messages
            ws.send_text("Sigues ahí?")
            ok_resp = ws.receive_json()
            assert ok_resp["approved"] is True
            assert ok_resp["response"] == "Recuperado"
