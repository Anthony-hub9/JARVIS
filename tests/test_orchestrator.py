from unittest.mock import MagicMock, patch

import pytest

import jarvis.agents.orchestrator as orchestrator_mod
from jarvis.agents.orchestrator import DualAgentOrchestrator, OllamaBackend
from jarvis.config import Settings
from jarvis.tools.agenda import AgendaStore
from jarvis.tools.memory import MemoryStore
from jarvis.tools.web_search import WebSearchTool


class MockBackend:
    def __init__(self, responses: list[str]) -> None:
        self._responses = iter(responses)
        self.calls: list[tuple[str, str]] = []

    async def generate(self, model: str, prompt: str) -> str:
        self.calls.append((model, prompt))
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
    assert cfg.executor_model == "qwen2.5:1.5b"
    assert cfg.supervisor_model == "qwen2.5:1.5b"
    assert cfg.fast_supervisor is True
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


@pytest.mark.asyncio
async def test_fast_supervisor_approves_plain_chat_and_safe_tools_in_one_call() -> None:
    store = AgendaStore(":memory:")
    try:
        backend = MockBackend(
            [
                "Hola, ¿en qué puedo ayudarte?",
                '{"tool": "app_launch", "app_name": "notepad"}',
                '{"tool": "agenda_add", "title": "Cita", "when": "2099-01-01T10:00:00"}',
            ]
        )
        orch = DualAgentOrchestrator(backend=backend, agenda_store=store, fast_supervisor=True)

        chat_res = await orch.run("Hola", device_id="pc")
        assert chat_res.approved is True
        assert chat_res.attempts == 1
        assert chat_res.response == "Hola, ¿en qué puedo ayudarte?"
        assert len(backend.calls) == 1

        with patch("jarvis.tools.app_control.subprocess.Popen", return_value=MagicMock()):
            launch_res = await orch.run("Por favor ejecuta notepad", device_id="pc")
        assert launch_res.approved is True
        assert launch_res.tool_result == {"tool": "app_launch", "app_name": "notepad", "device": "pc"}
        assert len(backend.calls) == 2

        agenda_res = await orch.run("Agenda cita", device_id="pc")
        assert agenda_res.approved is True
        assert agenda_res.tool_result is not None
        assert agenda_res.tool_result["event"]["title"] == "Cita"
        assert len(backend.calls) == 3
    finally:
        store.close()


@pytest.mark.asyncio
async def test_fast_supervisor_still_invokes_supervisor_for_app_close() -> None:
    backend = MockBackend(
        [
            '{"tool": "app_close", "app_name": "notepad"}',
            "APPROVED",
        ]
    )
    orch = DualAgentOrchestrator(
        backend=backend,
        executor_model="qwen2.5:1.5b",
        supervisor_model="qwen2.5:1.5b",
        fast_supervisor=True,
    )

    fake_done = MagicMock(returncode=0, stdout="SUCCESS", stderr="")
    with patch("jarvis.tools.app_control.subprocess.run", return_value=fake_done):
        res = await orch.run("Por favor cierra notepad", device_id="pc")

    assert res.approved is True
    assert res.tool_result is not None
    assert res.tool_result["tool"] == "app_close"
    assert len(backend.calls) == 2


@pytest.mark.asyncio
async def test_orchestrator_shared_memory_injection_and_turn_recording() -> None:
    memory = MemoryStore(":memory:")
    try:
        backend = MockBackend(
            [
                "Entendido, recordaré tu laptop.",
                "Listo desde tu S24+.",
                "Bloqueado",
                "REJECTED: No autorizado",
            ]
        )
        orch = DualAgentOrchestrator(
            backend=backend,
            memory_store=memory,
            max_retries=0,
            fast_supervisor=True,
        )

        res1 = await orch.run("Estoy en mi laptop", device_id="laptop")
        assert res1.approved is True

        res2 = await orch.run("¿Qué dije antes?", device_id="s24_plus")
        assert res2.approved is True
        # Second prompt must include the shared turns from laptop
        second_prompt = backend.calls[1][1]
        assert "[laptop] user: Estoy en mi laptop" in second_prompt
        assert "[laptop] assistant: Entendido, recordaré tu laptop." in second_prompt

        # Rejected/circuit-broken run must NOT be recorded in memory
        orch.fast_supervisor = False
        res3 = await orch.run("Comando peligroso", device_id="s24_plus")
        assert res3.approved is False
        assert len(memory.recent_turns(limit=10)) == 4
    finally:
        memory.close()


@pytest.mark.asyncio
async def test_orchestrator_executes_memory_save_and_search_tools() -> None:
    memory = MemoryStore(":memory:")
    try:
        backend = MockBackend(
            [
                '{"tool": "memory_save", "key": "cafe_favorito", "value": "Americano sin azúcar"}',
                '{"tool": "memory_search", "query": "cafe"}',
            ]
        )
        orch = DualAgentOrchestrator(
            backend=backend,
            memory_store=memory,
            fast_supervisor=True,
        )

        save_res = await orch.run("Recuerda que mi café favorito es americano sin azúcar", device_id="laptop")
        assert save_res.approved is True
        assert save_res.tool_result is not None
        assert save_res.tool_result["tool"] == "memory_save"
        assert save_res.tool_result["fact"]["key"] == "cafe_favorito"

        search_res = await orch.run("¿Cómo tomo el café?", device_id="s24_plus")
        assert search_res.approved is True
        assert search_res.tool_result is not None
        assert search_res.tool_result["tool"] == "memory_search"
        assert len(search_res.tool_result["facts"]) == 1
        assert search_res.tool_result["facts"][0]["value"] == "Americano sin azúcar"
        assert len(backend.calls) == 2
    finally:
        memory.close()


@pytest.mark.asyncio
async def test_orchestrator_executes_web_search_with_summary_and_fallback() -> None:
    fake_results = [
        {
            "title": "Clima CDMX",
            "snippet": "22°C mayormente soleado.",
            "url": "https://example.com/clima",
        }
    ]
    web_tool = MagicMock(spec=WebSearchTool)
    web_tool.search.return_value = fake_results

    backend = MockBackend(
        [
            '{"tool": "web_search", "query": "clima cdmx"}',
            "En Ciudad de México hay 22 grados y cielo soleado.",
        ]
    )
    orch = DualAgentOrchestrator(
        backend=backend,
        web_search=web_tool,
        fast_supervisor=True,
    )

    res = await orch.run("¿Cómo está el clima en CDMX?", device_id="s24_plus")
    assert res.approved is True
    assert res.response == "En Ciudad de México hay 22 grados y cielo soleado."
    assert res.tool_result == {
        "tool": "web_search",
        "query": "clima cdmx",
        "results": fake_results,
    }
    web_tool.search.assert_called_once_with("clima cdmx", max_results=3)

    # Fallback when backend.generate fails during summarization
    class FailingSummaryBackend:
        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, model: str, prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                return '{"tool": "web_search", "query": "clima cdmx"}'
            raise RuntimeError("Ollama timeout")

    orch_fallback = DualAgentOrchestrator(
        backend=FailingSummaryBackend(),
        web_search=web_tool,
        fast_supervisor=True,
    )
    fb_res = await orch_fallback.run("Clima CDMX", device_id="laptop")
    assert fb_res.approved is True
    assert "Clima CDMX: 22°C mayormente soleado." in fb_res.response
    assert fb_res.tool_result == {
        "tool": "web_search",
        "query": "clima cdmx",
        "results": fake_results,
    }


@pytest.mark.asyncio
async def test_fast_command_router_launches_apps_without_llm_json() -> None:
    memory = MemoryStore(":memory:")
    backend = MockBackend([])
    app_controller = MagicMock()
    try:
        orch = DualAgentOrchestrator(
            backend=backend,
            app_controller=app_controller,
            memory_store=memory,
            fast_supervisor=True,
        )

        calc_res = await orch.run("abre la calculadora", device_id="pc")
        assert calc_res.approved is True
        assert calc_res.attempts == 1
        assert calc_res.tool_result == {"tool": "app_launch", "app_name": "calculadora", "device": "pc"}
        app_controller.launch_app.assert_called_with("calculadora")

        riot_res = await orch.run("Jarvis abre el cliente de riot", device_id="pc")
        assert riot_res.approved is True
        assert riot_res.attempts == 1
        assert riot_res.tool_result == {"tool": "app_launch", "app_name": "cliente de riot", "device": "pc"}
        app_controller.launch_app.assert_called_with("cliente de riot")

        assert len(backend.calls) == 0
        assert len(memory.recent_turns(limit=10)) == 4
    finally:
        memory.close()


@pytest.mark.asyncio
async def test_fast_command_router_app_close_still_validates_with_supervisor() -> None:
    backend = MockBackend(["APPROVED"])
    orch = DualAgentOrchestrator(
        backend=backend,
        executor_model="qwen2.5:1.5b",
        supervisor_model="qwen2.5:1.5b",
        fast_supervisor=True,
    )

    fake_done = MagicMock(returncode=0, stdout="SUCCESS", stderr="")
    with patch("jarvis.tools.app_control.subprocess.run", return_value=fake_done) as run_mock:
        res = await orch.run("cierra discord", device_id="pc")

    run_mock.assert_called_once()
    assert res.approved is True
    assert res.attempts == 1
    assert res.tool_result is not None
    assert res.tool_result["tool"] == "app_close"
    assert res.tool_result["app_name"] == "discord"
    assert len(backend.calls) == 1
    assert '"tool": "app_close"' in backend.calls[0][1]


@pytest.mark.asyncio
async def test_fast_command_router_agenda_list_without_llm() -> None:
    store = AgendaStore(":memory:")
    try:
        store.add_event(title="Standup", when="2099-01-01T09:00:00")
        backend = MockBackend([])
        orch = DualAgentOrchestrator(
            backend=backend,
            agenda_store=store,
            fast_supervisor=True,
        )

        res = await orch.run("ver mi agenda", device_id="pc")
        assert res.approved is True
        assert res.attempts == 1
        assert res.tool_result is not None
        assert res.tool_result["tool"] == "agenda_list"
        assert len(res.tool_result["events"]) == 1
        assert res.tool_result["events"][0]["title"] == "Standup"
        assert len(backend.calls) == 0
    finally:
        store.close()
