from __future__ import annotations

import base64
import io
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from jarvis.agents.orchestrator import DualAgentOrchestrator, _route_direct_tool
from jarvis.clients import autostart
from jarvis.clients.tray_app import JarvisTrayApp
from jarvis.tools.desktop_context import read_clipboard_text, read_local_document
from jarvis.tools.laptop_vision import capture_screen_base64


class FakeBackend:
    def __init__(self, reply: str = "Respuesta simulada", replies: list[str] | None = None) -> None:
        self.reply = reply
        self._replies = iter(replies) if replies is not None else None
        self.calls: list[tuple[str, str, list[str] | None]] = []

    async def generate(
        self,
        model: str,
        prompt: str,
        images: list[str] | None = None,
    ) -> str:
        self.calls.append((model, prompt, images))
        if self._replies is not None:
            return next(self._replies)
        return self.reply


def test_capture_screen_base64_resizes_and_encodes_jpeg() -> None:
    fake_img = Image.new("RGBA", (2048, 1024), (10, 20, 30, 255))
    with patch("jarvis.tools.laptop_vision.ImageGrab.grab", return_value=fake_img):
        b64 = capture_screen_base64(max_width=1024)

    raw = base64.b64decode(b64)
    decoded = Image.open(io.BytesIO(raw))
    assert decoded.format == "JPEG"
    assert decoded.size == (1024, 512)
    assert decoded.mode == "RGB"


def test_capture_screen_base64_rejects_non_positive_width() -> None:
    with pytest.raises(ValueError):
        capture_screen_base64(max_width=0)


def test_read_clipboard_text_returns_truncated_text() -> None:
    with patch("jarvis.tools.desktop_context._read_windows_clipboard", return_value="  Hola JARVIS  "):
        assert read_clipboard_text(max_chars=10) == "Hola JARVI"


def test_read_clipboard_text_raises_on_empty() -> None:
    with patch("jarvis.tools.desktop_context._read_windows_clipboard", return_value="   "):
        with pytest.raises(ValueError, match="vacío"):
            read_clipboard_text()


def test_read_local_document_direct_and_top_two_levels(tmp_path: Path) -> None:
    root = tmp_path / "Docs"
    sub1 = root / "Proyecto"
    sub2 = sub1 / "Profundo"
    sub2.mkdir(parents=True)

    target_file = sub1 / "notas_jarvis.md"
    target_file.write_text("Contenido importante de pruebas para JARVIS.", encoding="utf-8")
    deep_file = sub2 / "oculto.txt"
    deep_file.write_text("No debe encontrarse en nivel 3", encoding="utf-8")

    found_path, text = read_local_document("notas_jarvis", search_roots=[root], max_chars=20)
    assert found_path == target_file
    assert text == "Contenido importante"

    direct_path, direct_text = read_local_document(str(target_file), max_chars=100)
    assert direct_path == target_file
    assert "JARVIS" in direct_text

    with pytest.raises(FileNotFoundError):
        read_local_document("oculto", search_roots=[root])


def test_read_local_document_pdf_uses_pypdf_when_available(tmp_path: Path) -> None:
    pdf_path = tmp_path / "reporte.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    fake_page = MagicMock()
    fake_page.extract_text.return_value = "Resumen ejecutivo del sistema."
    fake_reader = MagicMock(return_value=SimpleNamespace(pages=[fake_page]))

    with patch.dict(sys.modules, {"pypdf": SimpleNamespace(PdfReader=fake_reader)}):
        path, text = read_local_document(str(pdf_path))

    assert path == pdf_path
    assert text == "Resumen ejecutivo del sistema."


def test_autostart_command_formatting_prefers_pythonw(tmp_path: Path) -> None:
    python_exe = tmp_path / "python.exe"
    pythonw_exe = tmp_path / "pythonw.exe"
    script_path = tmp_path / "start_jarvis_tray.pyw"
    python_exe.write_text("", encoding="utf-8")
    pythonw_exe.write_text("", encoding="utf-8")
    script_path.write_text("", encoding="utf-8")

    cmd = autostart.build_autostart_command(python_exe=python_exe, script_path=script_path)
    assert cmd == f'"{pythonw_exe}" "{script_path}"'


def test_autostart_registry_operations_with_mocked_winreg() -> None:
    store: dict[str, str] = {}

    class FakeKey:
        def __enter__(self) -> FakeKey:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def fake_open_key(_hive: object, _subkey: str, _res: int = 0, _access: int = 0) -> FakeKey:
        return FakeKey()

    def fake_create_key(_hive: object, _subkey: str) -> FakeKey:
        return FakeKey()

    def fake_query(_key: FakeKey, name: str) -> tuple[str, int]:
        if name not in store:
            raise FileNotFoundError(name)
        return store[name], 1

    def fake_set(_key: FakeKey, name: str, _res: int, _kind: int, val: str) -> None:
        store[name] = val

    def fake_delete(_key: FakeKey, name: str) -> None:
        if name not in store:
            raise FileNotFoundError(name)
        del store[name]

    with (
        patch.object(autostart.winreg, "OpenKey", side_effect=fake_open_key),
        patch.object(autostart.winreg, "CreateKey", side_effect=fake_create_key),
        patch.object(autostart.winreg, "QueryValueEx", side_effect=fake_query),
        patch.object(autostart.winreg, "SetValueEx", side_effect=fake_set),
        patch.object(autostart.winreg, "DeleteValue", side_effect=fake_delete),
    ):
        assert autostart.is_autostart_enabled() is False
        assert autostart.toggle_autostart() is True
        assert autostart.is_autostart_enabled() is True
        assert autostart.VALUE_NAME in store
        assert autostart.toggle_autostart() is False
        assert autostart.is_autostart_enabled() is False


def test_tray_app_toggle_autostart_delegates() -> None:
    tray = JarvisTrayApp(voice_listener=MagicMock())
    with patch("jarvis.clients.tray_app.toggle_windows_autostart", return_value=True) as mock_toggle:
        assert tray.toggle_autostart() is True
    mock_toggle.assert_called_once_with()


def test_route_direct_tool_laptop_tools() -> None:
    assert _route_direct_tool("¿Qué ves en mi pantalla?") == {
        "tool": "laptop_screen_vision",
        "question": "Qué ves en mi pantalla?",
    }
    assert _route_direct_tool("Ayúdame con este error en pantalla") == {
        "tool": "laptop_screen_vision",
        "question": "Ayúdame con este error en pantalla",
    }
    assert _route_direct_tool("Lee lo que copié") == {
        "tool": "clipboard_read",
        "summarize": False,
    }
    assert _route_direct_tool("Resume el portapapeles") == {
        "tool": "clipboard_read",
        "summarize": True,
    }
    assert _route_direct_tool("Lee el archivo notas.md") == {
        "tool": "document_read",
        "target": "notas.md",
        "summarize": False,
    }
    assert _route_direct_tool("Resume el documento informe.pdf") == {
        "tool": "document_read",
        "target": "informe.pdf",
        "summarize": True,
    }


@pytest.mark.parametrize(
    "phrase",
    [
        "ve mi pantalla",
        "puedes ver mi pantalla",
        "lee mi pantalla",
        "qué ves en la pantalla",
        "qué está en mi pantalla",
        "mira la pantalla",
        "analiza mi pantalla",
    ],
)
def test_route_direct_tool_screen_vision_phrases(phrase: str) -> None:
    assert _route_direct_tool(phrase) == {
        "tool": "laptop_screen_vision",
        "question": phrase,
    }


@pytest.mark.asyncio
async def test_orchestrator_executes_laptop_screen_vision() -> None:
    backend = FakeBackend(
        replies=[
            "A code editor with a syntax error.",
            "Veo un editor de código con un error de sintaxis.",
        ]
    )
    orchestrator = DualAgentOrchestrator(
        backend=backend,
        executor_model="exec-test",
        vision_model="vision-test",
        fast_supervisor=True,
    )

    with patch("jarvis.agents.orchestrator.capture_screen_base64", return_value="BASE64DATA"):
        result = await orchestrator.run("¿Qué ves en mi pantalla?", device_id="pc")

    assert "editor de código" in result.response
    assert result.tool_result is not None
    assert result.tool_result["tool"] == "laptop_screen_vision"
    assert len(backend.calls) == 2
    assert backend.calls[0][0] == "vision-test"
    assert "English" in backend.calls[0][1]
    assert backend.calls[0][2] == ["BASE64DATA"]
    assert backend.calls[1][0] == "exec-test"
    assert "A code editor with a syntax error." in backend.calls[1][1]
    assert backend.calls[1][2] is None


@pytest.mark.asyncio
async def test_orchestrator_executes_clipboard_read_plain_and_summary() -> None:
    backend = FakeBackend(reply="Resumen del portapapeles.")
    orchestrator = DualAgentOrchestrator(backend=backend, executor_model="exec-test", fast_supervisor=True)

    with patch("jarvis.agents.orchestrator.read_clipboard_text", return_value="Texto copiado"):
        plain = await orchestrator.run("Lee el portapapeles", device_id="pc")
        summarized = await orchestrator.run("Resume el portapapeles", device_id="pc")

    assert "Texto copiado" in plain.response
    assert plain.tool_result is not None
    assert plain.tool_result["summarized"] is False
    assert summarized.response == "Resumen del portapapeles."
    assert summarized.tool_result is not None
    assert summarized.tool_result["summarized"] is True
    assert backend.calls[0][0] == "exec-test"


@pytest.mark.asyncio
async def test_orchestrator_executes_document_read_plain_and_summary(tmp_path: Path) -> None:
    doc = tmp_path / "plan.txt"
    backend = FakeBackend(reply="Resumen del plan.")
    orchestrator = DualAgentOrchestrator(backend=backend, executor_model="exec-test", fast_supervisor=True)

    with patch("jarvis.agents.orchestrator.read_local_document", return_value=(doc, "Paso 1: probar")):
        plain = await orchestrator.run("Lee el archivo plan.txt", device_id="pc")
        summarized = await orchestrator.run("Resume el documento plan.txt", device_id="pc")

    assert "Paso 1: probar" in plain.response
    assert plain.tool_result is not None
    assert plain.tool_result["path"] == str(doc)
    assert summarized.response == "Resumen del plan."
    assert summarized.tool_result is not None
    assert summarized.tool_result["summarized"] is True


def test_build_executor_prompt_distinguishes_game_mode_from_general_vision() -> None:
    orchestrator = DualAgentOrchestrator(backend=FakeBackend())
    game_prompt = orchestrator._build_executor_prompt("[Modo Juego] ¿Dónde está el enemigo?", "pc", "", has_images=True)
    general_prompt = orchestrator._build_executor_prompt("¿Qué error hay aquí?", "pc", "", has_images=True)

    assert "visión táctica" in game_prompt
    assert "munición baja" in game_prompt
    assert "visión táctica" not in general_prompt
    assert "munición baja" not in general_prompt
