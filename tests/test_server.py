from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from jarvis.agents.orchestrator import DualAgentOrchestrator, OrchestratorResult
from jarvis.hub.server import ConnectionManager, app, check_and_dispatch_reminders
from jarvis.tools.agenda import AgendaStore
from jarvis.tools.app_control import AppController
from jarvis.voice.tts import TTSError


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
    assert data["executor"] == "qwen2.5:1.5b"
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
                assert fake_backend.calls[8][0] == "qwen2.5:1.5b"
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


def test_index_contains_hud_and_api_hooks() -> None:
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "#050a12" in resp.text
    assert "#00d4ff" in resp.text
    assert "/api/tts" in resp.text
    assert "/api/agenda" in resp.text
    assert "/api/apps" in resp.text
    assert 'id="voiceProfileSelect"' in resp.text
    assert "jarvis_voice_profile" in resp.text


def test_tts_endpoint_success_and_errors() -> None:
    mock_engine = MagicMock()
    mock_engine.synthesize_audio = AsyncMock(
        return_value=(b"ID3\x03\x00\x00\x00", "audio/mpeg")
    )

    with patch("jarvis.hub.server.get_tts_engine", return_value=mock_engine):
        client = TestClient(app)
        resp = client.post("/api/tts", json={"text": "Hola señor"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "audio/mpeg"
        assert resp.content.startswith(b"ID3")
        mock_engine.synthesize_audio.assert_awaited_with("Hola señor", profile="jarvis")

        resp_albedo = client.post(
            "/api/tts", json={"text": "A sus órdenes", "voice": "albedo"}
        )
        assert resp_albedo.status_code == 200
        assert resp_albedo.headers["content-type"] == "audio/mpeg"
        mock_engine.synthesize_audio.assert_awaited_with(
            "A sus órdenes", profile="albedo"
        )

    mock_engine.synthesize_audio = AsyncMock(side_effect=ValueError("Texto vacío"))
    with patch("jarvis.hub.server.get_tts_engine", return_value=mock_engine):
        client = TestClient(app)
        resp = client.post("/api/tts", json={"text": ""})
        assert resp.status_code == 400

    mock_engine.synthesize_audio = AsyncMock(side_effect=TTSError("Sin voz"))
    with patch("jarvis.hub.server.get_tts_engine", return_value=mock_engine):
        client = TestClient(app)
        resp = client.post("/api/tts", json={"text": "Hola"})
        assert resp.status_code == 503
        assert "Sin voz" in resp.json()["detail"]


def test_agenda_endpoints() -> None:
    store = AgendaStore(":memory:")
    try:
        store.add_event("Pasado", "2000-01-01T10:00:00", "viejo")
        store.add_event("Futuro", "2099-01-01T10:00:00", "nuevo")

        with patch("jarvis.hub.server.get_agenda_store", return_value=store):
            client = TestClient(app)

            all_resp = client.get("/api/agenda")
            assert all_resp.status_code == 200
            titles = [e["title"] for e in all_resp.json()["events"]]
            assert titles == ["Pasado", "Futuro"]

            up_resp = client.get("/api/agenda?upcoming=true")
            assert up_resp.status_code == 200
            up_titles = [e["title"] for e in up_resp.json()["events"]]
            assert up_titles == ["Futuro"]

            create_resp = client.post(
                "/api/agenda",
                json={"title": "Revisión", "when": "2099-06-01T09:00:00", "notes": "HUD"},
            )
            assert create_resp.status_code == 201
            assert create_resp.json()["event"]["title"] == "Revisión"
    finally:
        store.close()


def test_apps_endpoints() -> None:
    controller = AppController(discover=False)
    mock_proc = MagicMock()
    mock_proc.pid = 4321

    with patch("jarvis.hub.server.get_app_controller", return_value=controller):
        client = TestClient(app)

        list_resp = client.get("/api/apps")
        assert list_resp.status_code == 200
        assert "notepad" in list_resp.json()["apps"]

        with patch.object(controller, "launch_app", return_value=mock_proc) as launch_mock:
            open_resp = client.post("/api/apps/open", json={"app_name": "notepad"})
            assert open_resp.status_code == 200
            assert open_resp.json()["status"] == "opened"
            assert open_resp.json()["pid"] == 4321
            launch_mock.assert_called_once_with("notepad")

        with patch.object(
            controller,
            "close_app",
            return_value={"process": "notepad.exe", "returncode": 0, "stdout": "", "stderr": ""},
        ) as close_mock:
            close_resp = client.post("/api/apps/close", json={"app_name": "notepad"})
            assert close_resp.status_code == 200
            assert close_resp.json()["status"] == "closed"
            assert close_resp.json()["process"] == "notepad.exe"
            close_mock.assert_called_once_with("notepad")


def test_index_contains_wake_word_hooks() -> None:
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'id="wakeWordToggle"' in resp.text
    assert "Escucha continua: Jarvis" in resp.text
    assert "WAKE_WORD_REGEX" in resp.text
    assert "scheduleWakeRestart" in resp.text
    assert "recognition.continuous = true" in resp.text
    assert "recognition.interimResults = false" in resp.text


def test_index_contains_mobile_intent_launch_button() -> None:
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "intent-launch-btn" in resp.text
    assert "intent_url" in resp.text
    assert "reminder_alert" in resp.text


@pytest.mark.asyncio
async def test_check_and_dispatch_reminders_broadcasts_and_posts_ntfy() -> None:
    store = AgendaStore(":memory:")
    conn_manager = ConnectionManager()
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()

    await conn_manager.connect(ws)
    try:
        ev = store.add_event("Revisar el horno", "2026-11-23T10:00:00")
        store.add_event("Evento futuro", "2099-01-01T10:00:00")

        mock_client = MagicMock()
        mock_client.post = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("jarvis.hub.server.httpx.AsyncClient", return_value=mock_client):
            dispatched = await check_and_dispatch_reminders(
                store=store,
                conn_manager=conn_manager,
                ntfy_topic="jarvis-test-topic",
                now="2026-11-23T10:01:00",
            )

        assert [item.id for item in dispatched] == [ev.id]
        ws.send_json.assert_awaited_once()
        payload = ws.send_json.await_args.args[0]
        assert payload["type"] == "reminder_alert"
        assert payload["device_id"] == "hub"
        assert payload["response"] == "Recordatorio: Revisar el horno"
        assert payload["approved"] is True
        assert payload["event"]["id"] == ev.id

        mock_client.post.assert_awaited_once()
        assert mock_client.post.await_args.args[0] == "https://ntfy.sh/jarvis-test-topic"

        # Second check should not re-dispatch already notified event
        second = await check_and_dispatch_reminders(
            store=store,
            conn_manager=conn_manager,
            ntfy_topic="jarvis-test-topic",
            now="2026-11-23T10:02:00",
        )
        assert second == []
    finally:
        conn_manager.disconnect(ws)
        store.close()


