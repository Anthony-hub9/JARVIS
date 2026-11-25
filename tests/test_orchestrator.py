import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import jarvis.agents.orchestrator as orchestrator_mod
from jarvis.agents.orchestrator import DualAgentOrchestrator, OllamaBackend, _clean_assistant_response
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

    popen_mock.assert_called_once_with(
        ["notepad.exe"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
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
    backend = VisionMockBackend(["Low ammo warning on HUD.", "Poca munición, recarga.", "APPROVED"])
    orch = DualAgentOrchestrator(
        backend=backend,
        executor_model="qwen2.5:1.5b",
        vision_model="moondream",
        supervisor_model="qwen2.5:1.5b",
    )

    res = await orch.run("[Modo Juego] Analiza", device_id="pc_game", images=["ZmFrZV9mcmFtZQ=="])

    assert res.approved is True
    assert res.response == "Poca munición, recarga."
    assert backend.calls[0][0] == "moondream"
    assert "English" in backend.calls[0][1]
    assert backend.calls[0][2] == ["ZmFrZV9mcmFtZQ=="]
    assert backend.calls[1][0] == "qwen2.5:1.5b"
    assert "Low ammo warning on HUD." in backend.calls[1][1]
    assert "munición baja" in backend.calls[1][1]
    assert backend.calls[1][2] is None
    assert backend.calls[2][0] == "qwen2.5:1.5b"
    assert backend.calls[2][2] is None


@pytest.mark.asyncio
async def test_describe_image_in_spanish_sanitizes_thai_and_repetition() -> None:
    backend = VisionMockBackend(["A laptop screen showing Python code. รามารามารามารามา", "Veo una laptop con código Python."])
    orch = DualAgentOrchestrator(backend=backend, executor_model="qwen2.5:1.5b", vision_model="moondream")

    answer = await orch._describe_image_in_spanish("Describe esta foto", ["IMG_B64"])
    assert answer == "Veo una laptop con código Python."
    assert "ราม" not in backend.calls[1][1]
    assert "A laptop screen showing Python code." in backend.calls[1][1]

    gibberish_backend = VisionMockBackend(["รามารามารามารามา"])
    gibberish_orch = DualAgentOrchestrator(backend=gibberish_backend, executor_model="qwen2.5:1.5b", vision_model="moondream")
    fallback = await gibberish_orch._describe_image_in_spanish("Describe esta foto", ["IMG_B64"])
    assert fallback == "No pude obtener una descripción clara de la imagen."
    assert len(gibberish_backend.calls) == 1


@pytest.mark.asyncio
async def test_ollama_backend_includes_repeat_penalty() -> None:
    captured_payload: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"response": "ok"}

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, _url: str, json: dict[str, object]) -> FakeResponse:
            captured_payload.update(json)
            return FakeResponse()

    with patch("httpx.AsyncClient", FakeClient):
        result = await OllamaBackend().generate("moondream", "Describe", images=["IMG"])

    assert result == "ok"
    assert captured_payload["options"] == {"num_predict": 512, "num_ctx": 8192, "repeat_penalty": 1.15}


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
        # Second prompt must include the shared turns from laptop without device tag
        second_prompt = backend.calls[1][1]
        assert "- Tú: Estoy en mi laptop" in second_prompt
        assert "- JARVIS: Entendido, recordaré tu laptop." in second_prompt
        assert "[laptop]" not in second_prompt
        assert "[Dispositivo:" not in second_prompt

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

        save_res = await orch.run("Mi café favorito es americano sin azúcar", device_id="laptop")
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


@pytest.mark.asyncio
async def test_fast_command_router_s24_plus_builds_mobile_intent_without_laptop_launch() -> None:
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

        res = await orch.run("abre la calculadora", device_id="s24-plus")
        assert res.approved is True
        assert res.attempts == 1
        assert res.tool_result is not None
        assert res.tool_result["tool"] == "app_launch"
        assert res.tool_result["intent"]["package"] == "com.sec.android.app.popupcalculator"
        assert "intent_url" in res.tool_result["intent"]
        assert res.tool_result["intent"]["intent_url"] == ""
        assert res.tool_result["intent"]["requires_native_bridge"] is True
        app_controller.launch_app.assert_not_called()
        assert len(backend.calls) == 0
    finally:
        memory.close()


@pytest.mark.asyncio
async def test_fast_command_router_web_search_and_records_turns() -> None:
    memory = MemoryStore(":memory:")
    fake_results = [
        {
            "title": "Clima CDMX",
            "url": "https://example.com/clima",
            "snippet": "22°C mayormente soleado.",
        }
    ]
    web_tool = MagicMock(spec=WebSearchTool)
    web_tool.search.return_value = fake_results
    backend = MockBackend(["Hoy en CDMX hay 22°C y cielo mayormente soleado."])
    try:
        orch = DualAgentOrchestrator(
            backend=backend,
            memory_store=memory,
            web_search=web_tool,
            fast_supervisor=True,
        )

        res = await orch.run("busca clima cdmx hoy", device_id="pc")
        assert res.approved is True
        assert res.attempts == 1
        assert res.response == "Hoy en CDMX hay 22°C y cielo mayormente soleado."
        assert res.tool_result == {
            "tool": "web_search",
            "query": "clima cdmx hoy",
            "results": fake_results,
        }
        web_tool.search.assert_called_once_with("clima cdmx hoy", max_results=3)
        assert len(backend.calls) == 1
        assert "Resume de forma breve" in backend.calls[0][1]

        turns = memory.recent_turns(limit=10)
        assert len(turns) == 2
        assert turns[0].role == "user"
        assert turns[0].content == "busca clima cdmx hoy"
        assert turns[1].role == "assistant"
        assert turns[1].content == "Hoy en CDMX hay 22°C y cielo mayormente soleado."
    finally:
        memory.close()


@pytest.mark.asyncio
async def test_fast_command_router_memory_save_and_search() -> None:
    memory = MemoryStore(":memory:")
    backend = MockBackend([])
    try:
        orch = DualAgentOrchestrator(
            backend=backend,
            memory_store=memory,
            fast_supervisor=True,
        )

        save_res = await orch.run("recuerda que mi campeón favorito es Yasuo", device_id="pc")
        assert save_res.approved is True
        assert save_res.attempts == 1
        assert save_res.tool_result is not None
        assert save_res.tool_result["tool"] == "memory_save"
        assert save_res.tool_result["fact"]["key"] == "mi campeón favorito es"
        assert save_res.tool_result["fact"]["value"] == "mi campeón favorito es Yasuo"

        search_res = await orch.run("qué recuerdas de Yasuo", device_id="s24")
        assert search_res.approved is True
        assert search_res.attempts == 1
        assert search_res.tool_result is not None
        assert search_res.tool_result["tool"] == "memory_search"
        assert search_res.tool_result["query"] == "Yasuo"
        assert len(search_res.tool_result["facts"]) == 1
        assert "Yasuo" in search_res.tool_result["facts"][0]["value"]
        assert "Yasuo" in search_res.response
        assert len(backend.calls) == 0
    finally:
        memory.close()


@pytest.mark.asyncio
async def test_saved_facts_are_injected_into_normal_chat_prompts() -> None:
    memory = MemoryStore(":memory:")
    memory.save_fact("mi campeón favorito es", "mi campeón favorito es Yasuo")
    backend = MockBackend(["Tu campeón favorito es Yasuo."])
    try:
        orch = DualAgentOrchestrator(
            backend=backend,
            memory_store=memory,
            fast_supervisor=True,
        )

        res = await orch.run("¿Cuál es mi campeón favorito?", device_id="pc")
        assert res.approved is True
        assert res.response == "Tu campeón favorito es Yasuo."
        assert len(backend.calls) == 1
        prompt = backend.calls[0][1]
        assert "[Hechos guardados]" in prompt
        assert "mi campeón favorito es Yasuo" in prompt
    finally:
        memory.close()


@pytest.mark.asyncio
async def test_fast_command_router_routes_spanish_reminder_to_agenda_add() -> None:
    from jarvis.agents.orchestrator import _route_direct_tool

    routed = _route_direct_tool("recuérdame en 10 minutos revisar el horno")
    assert routed is not None
    assert routed["tool"] == "agenda_add"
    assert routed["title"] == "revisar el horno"
    assert "T" in routed["when"]

    store = AgendaStore(":memory:")
    backend = MockBackend([])
    try:
        orch = DualAgentOrchestrator(
            backend=backend,
            agenda_store=store,
            fast_supervisor=True,
        )
        res = await orch.run("recuérdame en 10 minutos revisar el horno", device_id="pc")
        assert res.approved is True
        assert res.attempts == 1
        assert backend.calls == []
        assert res.tool_result is not None
        assert res.tool_result["tool"] == "agenda_add"
        assert res.tool_result["event"]["title"] == "revisar el horno"
        events = store.list_events()
        assert len(events) == 1
        assert events[0].title == "revisar el horno"
    finally:
        store.close()


@pytest.mark.asyncio
async def test_fast_command_router_routes_system_tools() -> None:
    from jarvis.agents.orchestrator import _route_direct_tool

    assert _route_direct_tool("qué hora es") == {"tool": "system_time"}
    assert _route_direct_tool("dime la hora") == {"tool": "system_time"}
    assert _route_direct_tool("qué día es hoy") == {"tool": "system_time"}
    assert _route_direct_tool("qué fecha es") == {"tool": "system_time"}

    assert _route_direct_tool("batería") == {"tool": "system_status"}
    assert _route_direct_tool("estado de la laptop") == {"tool": "system_status"}
    assert _route_direct_tool("cuánta ram") == {"tool": "system_status"}
    assert _route_direct_tool("uso de cpu") == {"tool": "system_status"}

    assert _route_direct_tool("sube el volumen") == {"tool": "system_media", "action": "volume_up"}
    assert _route_direct_tool("baja el volumen") == {"tool": "system_media", "action": "volume_down"}
    assert _route_direct_tool("silencia") == {"tool": "system_media", "action": "mute"}
    assert _route_direct_tool("pon pausa") == {"tool": "system_media", "action": "play_pause"}
    assert _route_direct_tool("pausa") == {"tool": "system_media", "action": "play_pause"}
    assert _route_direct_tool("reproduce") == {"tool": "system_media", "action": "play_pause"}
    assert _route_direct_tool("siguiente canción") == {"tool": "system_media", "action": "next_track"}
    assert _route_direct_tool("canción anterior") == {"tool": "system_media", "action": "prev_track"}

    assert _route_direct_tool("abre descargas") == {"tool": "system_open_target", "target": "descargas"}
    assert _route_direct_tool("abre documentos") == {"tool": "system_open_target", "target": "documentos"}
    assert _route_direct_tool("abre escritorio") == {"tool": "system_open_target", "target": "escritorio"}
    assert _route_direct_tool("abre youtube") == {"tool": "system_open_target", "target": "youtube"}
    assert _route_direct_tool("abre github") == {"tool": "system_open_target", "target": "github"}
    assert _route_direct_tool("abre google") == {"tool": "system_open_target", "target": "google"}

    assert _route_direct_tool("bloquea la pantalla") == {"tool": "system_power", "action": "lock"}
    assert _route_direct_tool("bloquea la laptop") == {"tool": "system_power", "action": "lock"}
    assert _route_direct_tool("suspende la laptop") == {"tool": "system_power", "action": "sleep"}

    fake_sys = MagicMock()
    fake_sys.get_time_info.return_value = {
        "time": "10:30",
        "date": "23/11/2026",
        "weekday": "lunes",
        "formatted": "Son las 10:30 del lunes 23/11/2026",
    }
    fake_sys.get_system_status.return_value = {
        "cpu_percent": 15.0,
        "formatted": "Estado del sistema: CPU al 15.0%.",
    }
    fake_sys.media_action.return_value = "Subiendo el volumen."
    fake_sys.open_target.return_value = "Abriendo youtube en el navegador."
    fake_sys.power_action.return_value = "Bloqueando la pantalla."

    backend = MockBackend([])
    orch = DualAgentOrchestrator(backend=backend, system_controller=fake_sys, fast_supervisor=True)

    time_res = await orch.run("qué hora es", device_id="pc")
    assert time_res.approved is True
    assert time_res.response == "Son las 10:30 del lunes 23/11/2026"
    assert time_res.tool_result is not None and time_res.tool_result["tool"] == "system_time"

    status_res = await orch.run("estado de la laptop", device_id="pc")
    assert status_res.approved is True
    assert "CPU al 15.0%" in status_res.response

    media_res = await orch.run("sube el volumen", device_id="pc")
    assert media_res.approved is True
    fake_sys.media_action.assert_called_once_with("volume_up")

    open_res = await orch.run("abre youtube", device_id="pc")
    assert open_res.approved is True
    fake_sys.open_target.assert_called_once_with("youtube")

    # SAFE_FAST_TOOLS calls above must not invoke the LLM backend at all.
    assert backend.calls == []

    # system_power MUST go through supervisor validation even with fast_supervisor=True.
    sup_backend = MockBackend(["APPROVED"])
    sup_orch = DualAgentOrchestrator(
        backend=sup_backend,
        system_controller=fake_sys,
        fast_supervisor=True,
    )
    power_res = await sup_orch.run("bloquea la pantalla", device_id="pc")
    assert power_res.approved is True
    assert len(sup_backend.calls) == 1
    fake_sys.power_action.assert_called_once_with("lock")


@pytest.mark.asyncio
async def test_fast_command_router_exact_volume_and_dynamic_folder(tmp_path: Path) -> None:
    from jarvis.agents.orchestrator import _route_direct_tool
    from jarvis.tools.system_control import SystemController

    assert _route_direct_tool("sube el volumen a 10") == {
        "tool": "system_media",
        "action": "set_volume",
        "level": 10,
    }
    assert _route_direct_tool("pon el volumen en 50%") == {
        "tool": "system_media",
        "action": "set_volume",
        "level": 50,
    }
    assert _route_direct_tool("volumen al 30") == {
        "tool": "system_media",
        "action": "set_volume",
        "level": 30,
    }
    assert _route_direct_tool("baja el volumen a 20") == {
        "tool": "system_media",
        "action": "set_volume",
        "level": 20,
    }
    assert _route_direct_tool("abre la carpeta de TT") == {
        "tool": "system_open_target",
        "target": "TT",
        "kind": "folder",
    }

    fake_sys = MagicMock()
    fake_sys.set_volume.return_value = "Volumen ajustado al 10%."
    backend = MockBackend([])
    orch = DualAgentOrchestrator(backend=backend, system_controller=fake_sys, fast_supervisor=True)

    vol_res = await orch.run("sube el volumen a 10", device_id="pc")
    assert vol_res.approved is True
    assert vol_res.response == "Volumen ajustado al 10%."
    fake_sys.set_volume.assert_called_once_with(10)
    assert backend.calls == []

    # Real SystemController with tmp_path folder and mocked app_launcher to ensure no app_launch fallback
    tt_dir = tmp_path / "TT"
    tt_dir.mkdir()
    real_sys = SystemController()
    fake_launcher = MagicMock()
    folder_orch = DualAgentOrchestrator(
        backend=backend,
        app_controller=fake_launcher,
        system_controller=real_sys,
        fast_supervisor=True,
    )

    with (
        patch.object(real_sys, "_default_folder_roots", return_value=[tmp_path]),
        patch("jarvis.tools.system_control.subprocess.Popen") as popen_mock,
    ):
        found_res = await folder_orch.run("abre la carpeta de TT", device_id="pc")
        missing_res = await folder_orch.run("abre la carpeta de NoExisteXYZ", device_id="pc")

    assert found_res.approved is True
    assert "TT" in found_res.response
    popen_mock.assert_called_once()
    assert missing_res.approved is True
    assert "No encontré la carpeta 'NoExisteXYZ'" in missing_res.response
    assert [c for c in fake_launcher.mock_calls if c[0] != "__bool__"] == []
    assert backend.calls == []


def test_build_executor_prompt_omits_device_tags_and_clean_response_strips_echo() -> None:
    from jarvis.tools.memory import MemoryTurn

    orch = DualAgentOrchestrator(backend=MockBackend([]))
    turns = [MemoryTurn(id=1, device_id="s24-plus", role="user", content="Hola", created_at="2026-01-01")]

    prompt = orch._build_executor_prompt("¿Qué hora es?", "s24-plus", "", recent_turns=turns)
    vision_prompt = orch._build_executor_prompt("¿Qué ves?", "s24-plus", "", has_images=True, recent_turns=turns)

    assert "[Dispositivo: s24-plus]" not in prompt
    assert "[s24-plus]" not in prompt
    assert "Responde directo sin mencionar el nombre del dispositivo." in prompt
    assert "Usuario: ¿Qué hora es?" in prompt

    assert "[Dispositivo: s24-plus]" not in vision_prompt
    assert "[s24-plus]" not in vision_prompt
    assert "Solicitud: ¿Qué ves?" in vision_prompt

    assert _clean_assistant_response("Dispositivo s24-plus: Hola") == "Hola"
    assert _clean_assistant_response("[Dispositivo: s24-plus] Hola") == "Hola"
    assert _clean_assistant_response("s24-plus: Hola") == "Hola"
    assert _clean_assistant_response("Hola, ¿en qué te ayudo?") == "Hola, ¿en qué te ayudo?"


@pytest.mark.asyncio
async def test_orchestrator_run_cleans_device_echo_prefix() -> None:
    backend = MockBackend(["Dispositivo s24-plus: Son las diez."])
    orch = DualAgentOrchestrator(backend=backend, fast_supervisor=True)

    res = await orch.run("Hola JARVIS", device_id="s24-plus")

    assert res.approved is True
    assert res.response == "Son las diez."


def test_conversational_greeting_prompt_omits_tool_schemas_and_formats_turns() -> None:
    from jarvis.tools.memory import MemoryTurn

    orch = DualAgentOrchestrator(backend=MockBackend([]))
    turns = [
        MemoryTurn(id=1, device_id="pc", role="user", content="Buenas", created_at="2026-01-01"),
        MemoryTurn(id=2, device_id="pc", role="assistant", content="Hola, ¿cómo estás?", created_at="2026-01-01"),
    ]

    prompt = orch._build_executor_prompt("hola", "pc", "", recent_turns=turns)

    assert "Herramientas disponibles" not in prompt
    assert '{"tool":' not in prompt
    assert "- Tú: Buenas" in prompt
    assert "- JARVIS: Hola, ¿cómo estás?" in prompt
    assert "- user:" not in prompt
    assert "- assistant:" not in prompt


def test_clean_assistant_response_strips_assistant_and_jarvis_prefixes() -> None:
    assert _clean_assistant_response("Assistant: Hola señor") == "Hola señor"
    assert _clean_assistant_response("JARVIS: Buenos días") == "Buenos días"
    assert _clean_assistant_response("Assistant: Dispositivo s24-plus: Hola") == "Hola"


@pytest.mark.asyncio
async def test_orchestrator_never_leaks_raw_tool_json_on_greeting() -> None:
    backend = MockBackend(['Assistant: {"tool": "agenda_list"}'])
    orch = DualAgentOrchestrator(backend=backend, fast_supervisor=True)

    res = await orch.run("hola", device_id="pc")

    assert res.approved is True
    assert '"tool"' not in res.response
    assert "agenda_list" not in res.response
    assert res.response == "Hola, ¿en qué puedo ayudarte?"
