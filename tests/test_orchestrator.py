from unittest.mock import MagicMock, patch

import pytest

import jarvis.agents.orchestrator as orchestrator_mod
from jarvis.agents.orchestrator import DualAgentOrchestrator, OllamaBackend
from jarvis.config import Settings
from jarvis.tools.agenda import AgendaStore


class MockBackend:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)

    async def generate(self, model: str, prompt: str) -> str:
        return next(self._responses)


@pytest.mark.asyncio
async def test_orchestrator_approves_on_first_try() -> None:
    backend = MockBackend(["Hola, soy JARVIS.", "APPROVED"])
    orch = DualAgentOrchestrator(backend=backend, max_retries=2)

    result = await orch.run("Hola JARVIS", device_id="laptop")

    assert result.approved is True
    assert result.circuit_broken is False
    assert result.attempts == 1
    assert result.response == "Hola, soy JARVIS."


@pytest.mark.asyncio
async def test_orchestrator_retries_and_approves() -> None:
    backend = MockBackend(
        [
            "Borrando archivos...",
            "REJECTED: Acción peligrosa sin confirmación",
            "¿Confirmas que deseas continuar?",
            "APPROVED",
        ]
    )
    orch = DualAgentOrchestrator(backend=backend, max_retries=2)

    result = await orch.run("Limpia descargas", device_id="s24")

    assert result.approved is True
    assert result.circuit_broken is False
    assert result.attempts == 2
    assert result.response == "¿Confirmas que deseas continuar?"


@pytest.mark.asyncio
async def test_orchestrator_trips_circuit_breaker_after_max_retries() -> None:
    backend = MockBackend(
        [
            "Intento 1",
            "REJECTED: Falla 1",
            "Intento 2",
            "REJECTED: Falla 2",
            "Intento 3",
            "REJECTED: Falla 3",
        ]
    )
    orch = DualAgentOrchestrator(backend=backend, max_retries=2)

    result = await orch.run("Comando inválido", device_id="watch7")

    assert result.approved is False
    assert result.circuit_broken is True
    assert result.attempts == 3
    assert "Circuit Breaker" in result.response


def test_settings_and_orchestrator_use_ollama_only() -> None:
    cfg = Settings(_env_file=None)
    assert cfg.executor_model == "qwen2.5:3b"
    assert cfg.supervisor_model == "qwen2.5:1.5b"
    assert cfg.vision_model == "moondream"
    assert cfg.ollama_base_url == "http://localhost:11434"
    assert not hasattr(cfg, "gemini_api_key")
    assert not hasattr(orchestrator_mod, "GeminiBackend")

    orch = DualAgentOrchestrator()
    assert isinstance(orch.backend, OllamaBackend)


@pytest.mark.asyncio
async def test_orchestrator_executes_agenda_tools_after_approval() -> None:
    store = AgendaStore(":memory:")
    try:
        backend = MockBackend(
            [
                '{"tool": "agenda_add", "title": "Reunión", "when": "2099-01-01T10:00:00", "notes": "Sync"}',
                "APPROVED",
                '{"tool": "agenda_list"}',
                "APPROVED",
                '{"tool": "agenda_upcoming", "now": "2099-01-01T09:00:00"}',
                "APPROVED",
            ]
        )
        orch = DualAgentOrchestrator(backend=backend, agenda_store=store)

        add_res = await orch.run("Agenda reunión", device_id="pc")
        assert add_res.approved is True
        assert add_res.tool_result is not None
        assert add_res.tool_result["event"]["title"] == "Reunión"

        list_res = await orch.run("Lista mi agenda", device_id="laptop")
        assert list_res.approved is True
        assert list_res.tool_result is not None
        assert len(list_res.tool_result["events"]) == 1

        up_res = await orch.run("Qué tengo próximo", device_id="s24_plus")
        assert up_res.approved is True
        assert up_res.tool_result is not None
        assert up_res.tool_result["events"][0]["title"] == "Reunión"
    finally:
        store.close()


@pytest.mark.asyncio
async def test_orchestrator_launches_app_on_pc_and_builds_intent_on_s24() -> None:
    backend = MockBackend(
        [
            '```json\n{"tool": "app_launch", "app_name": "notepad"}\n```',
            "APPROVED",
            '{"tool": "app_launch", "app_name": "spotify"}',
            "APPROVED",
        ]
    )
    orch = DualAgentOrchestrator(backend=backend)

    with patch("jarvis.tools.app_control.subprocess.Popen", return_value=MagicMock()) as popen_mock:
        pc_res = await orch.run("Abre el bloc de notas", device_id="pc")

    popen_mock.assert_called_once_with(["notepad.exe"])
    assert pc_res.approved is True
    assert pc_res.tool_result == {"tool": "app_launch", "app_name": "notepad", "device": "pc"}

    mobile_res = await orch.run("Abre Spotify", device_id="s24_plus")
    assert mobile_res.approved is True
    assert mobile_res.tool_result is not None
    assert mobile_res.tool_result["intent"]["package"] == "com.spotify.music"


@pytest.mark.asyncio
async def test_orchestrator_does_not_execute_rejected_tool_call() -> None:
    store = AgendaStore(":memory:")
    try:
        backend = MockBackend(
            [
                '{"tool": "agenda_add", "title": "Borrar todo", "when": "2099-01-01T10:00:00"}',
                "REJECTED: No autorizado",
                '{"tool": "agenda_add", "title": "Borrar todo", "when": "2099-01-01T10:00:00"}',
                "REJECTED: No autorizado",
            ]
        )
        orch = DualAgentOrchestrator(backend=backend, max_retries=1, agenda_store=store)
        res = await orch.run("Haz algo peligroso", device_id="pc")

        assert res.approved is False
        assert res.circuit_broken is True
        assert store.list_events() == []
    finally:
        store.close()


@pytest.mark.asyncio
async def test_orchestrator_closes_app_and_blocks_protected_process() -> None:
    backend = MockBackend(
        [
            '{"tool": "app_close", "app_name": "notepad"}',
            "APPROVED",
            '{"tool": "app_close", "app_name": "explorer.exe"}',
            "APPROVED",
        ]
    )
    orch = DualAgentOrchestrator(backend=backend)

    fake_done = MagicMock(returncode=0, stdout="SUCCESS", stderr="")
    with patch("jarvis.tools.app_control.subprocess.run", return_value=fake_done) as run_mock:
        ok_res = await orch.run("Cierra el bloc de notas", device_id="pc_game")

    run_mock.assert_called_once()
    assert ok_res.approved is True
    assert ok_res.tool_result is not None
    assert ok_res.tool_result["tool"] == "app_close"
    assert ok_res.tool_result["process"] == "notepad.exe"

    with patch("jarvis.tools.app_control.subprocess.run") as run_mock_blocked:
        blocked_res = await orch.run("Cierra explorer", device_id="pc_game")

    run_mock_blocked.assert_not_called()
    assert blocked_res.approved is True
    assert blocked_res.tool_result is not None
    assert "protected system process" in blocked_res.tool_result["error"]


class VisionMockBackend:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.calls: list[tuple[str, str, list[str] | None]] = []

    async def generate(self, model: str, prompt: str, images: list[str] | None = None) -> str:
        self.calls.append((model, prompt, images))
        return next(self._responses)


@pytest.mark.asyncio
async def test_orchestrator_routes_images_to_vision_model() -> None:
    backend = VisionMockBackend(["Poca munición, recarga.", "APPROVED"])
    orch = DualAgentOrchestrator(backend=backend, vision_model="moondream", supervisor_model="qwen2.5:1.5b")

    res = await orch.run("", device_id="pc_game", images=["ZmFrZV9mcmFtZQ=="])

    assert res.approved is True
    assert res.response == "Poca munición, recarga."
    assert backend.calls[0][0] == "moondream"
    assert backend.calls[0][2] == ["ZmFrZV9mcmFtZQ=="]
    assert backend.calls[1][0] == "qwen2.5:1.5b"
    assert backend.calls[1][2] is None
