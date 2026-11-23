from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from jarvis.clients.tray_app import JarvisTrayApp, _ensure_stdio, create_tray_icon_image


def test_create_tray_icon_image_returns_valid_rgba_image() -> None:
    img = create_tray_icon_image()
    assert isinstance(img, Image.Image)
    assert img.mode in ("RGBA", "RGB")
    assert img.size == (64, 64)
    # Center pixel should be bright cyan arc-reactor core
    center = img.getpixel((32, 32))
    assert center[:3] == (0, 212, 255)


def test_tray_app_open_hud_opens_browser() -> None:
    tray = JarvisTrayApp(host="127.0.0.1", port=8123)
    with patch("jarvis.clients.tray_app.webbrowser.open") as mock_open:
        tray.open_hud()
    mock_open.assert_called_once_with("http://localhost:8123/")


def test_tray_app_quit_stops_server_and_icon() -> None:
    mock_listener = MagicMock()
    tray = JarvisTrayApp(voice_listener=mock_listener)
    mock_server = MagicMock()
    mock_server.should_exit = False
    mock_icon = MagicMock()
    tray.server = mock_server
    tray.icon = mock_icon

    tray.quit(mock_icon)

    mock_listener.stop.assert_called_once_with()
    assert mock_server.should_exit is True
    mock_icon.stop.assert_called_once()


def test_tray_app_start_server_skips_when_port_open() -> None:
    tray = JarvisTrayApp(host="127.0.0.1", port=8000)
    with (
        patch("jarvis.clients.tray_app._is_port_open", return_value=True),
        patch("jarvis.clients.tray_app.uvicorn.Server") as mock_server_cls,
    ):
        started = tray.start_server()

    assert started is False
    assert tray.server is None
    mock_server_cls.assert_not_called()


def test_tray_app_run_starts_server_and_runs_pystray_icon() -> None:
    mock_listener = MagicMock()
    mock_listener.voice_profile = "jarvis"
    tray = JarvisTrayApp(host="127.0.0.1", port=8000, voice_listener=mock_listener)
    mock_server = MagicMock()
    mock_icon = MagicMock()

    with (
        patch("jarvis.clients.tray_app._is_port_open", return_value=False),
        patch.object(tray, "ensure_ollama_running", return_value=False) as mock_ensure_ollama,
        patch("jarvis.clients.tray_app.uvicorn.Config") as mock_config_cls,
        patch("jarvis.clients.tray_app.uvicorn.Server", return_value=mock_server),
        patch("jarvis.clients.tray_app.threading.Thread") as mock_thread_cls,
        patch("jarvis.clients.tray_app.pystray.Icon", return_value=mock_icon) as mock_icon_cls,
    ):
        tray.run()

    mock_ensure_ollama.assert_called_once_with()
    mock_listener.start.assert_called_once_with()

    mock_config_cls.assert_called_once_with(
        "jarvis.hub.server:app",
        host="127.0.0.1",
        port=8000,
        log_level="warning",
    )
    mock_thread_cls.assert_called_once()
    assert mock_thread_cls.call_args.kwargs["daemon"] is True
    mock_thread_cls.return_value.start.assert_called_once()
    mock_icon_cls.assert_called_once()
    menu = mock_icon_cls.call_args.kwargs["menu"]
    labels = [item.text for item in menu.items]
    assert "Escucha continua (Jarvis)" in labels
    assert "Voz: JARVIS / Albedo" in labels
    mock_icon.run.assert_called_once()


def test_ensure_stdio_replaces_none_streams(tmp_path: Path, monkeypatch) -> None:
    import sys

    log_file = tmp_path / "jarvis_tray.log"
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    _ensure_stdio(log_file)

    try:
        assert sys.stdout is not None
        assert sys.stderr is not None
        assert sys.stdout.writable()
        assert sys.stderr.writable()
        sys.stdout.write("hello\n")
        sys.stdout.flush()
    finally:
        if sys.stdout is not None:
            sys.stdout.close()

    assert "hello" in log_file.read_text(encoding="utf-8")


def test_ensure_ollama_running_skips_when_port_open() -> None:
    tray = JarvisTrayApp()
    with (
        patch("jarvis.clients.tray_app._is_port_open", return_value=True) as mock_port,
        patch("jarvis.clients.tray_app.shutil.which") as mock_which,
        patch("jarvis.clients.tray_app.subprocess.Popen") as mock_popen,
    ):
        started = tray.ensure_ollama_running()

    assert started is False
    assert tray.ollama_proc is None
    mock_port.assert_called_once_with("127.0.0.1", 11434)
    mock_which.assert_not_called()
    mock_popen.assert_not_called()


def test_ensure_ollama_running_returns_false_when_missing_executable() -> None:
    tray = JarvisTrayApp()
    with (
        patch("jarvis.clients.tray_app._is_port_open", return_value=False),
        patch("jarvis.clients.tray_app.shutil.which", return_value=None),
        patch("jarvis.clients.tray_app.subprocess.Popen") as mock_popen,
    ):
        started = tray.ensure_ollama_running()

    assert started is False
    assert tray.ollama_proc is None
    mock_popen.assert_not_called()


def test_ensure_ollama_running_spawns_when_port_closed_and_exe_found() -> None:
    import subprocess

    tray = JarvisTrayApp()
    mock_proc = MagicMock()
    with (
        patch("jarvis.clients.tray_app._is_port_open", return_value=False),
        patch("jarvis.clients.tray_app.shutil.which", return_value=r"C:\Ollama\ollama.exe"),
        patch("jarvis.clients.tray_app.subprocess.Popen", return_value=mock_proc) as mock_popen,
    ):
        started = tray.ensure_ollama_running()

    assert started is True
    assert tray.ollama_proc is mock_proc
    mock_popen.assert_called_once_with(
        [r"C:\Ollama\ollama.exe", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def test_tray_app_quit_terminates_ollama_proc_if_started() -> None:
    tray = JarvisTrayApp()
    mock_proc = MagicMock()
    mock_icon = MagicMock()
    tray.ollama_proc = mock_proc
    tray.icon = mock_icon

    tray.quit(mock_icon)

    mock_proc.terminate.assert_called_once_with()
    assert tray.ollama_proc is None
    mock_icon.stop.assert_called_once_with()


def test_tray_app_toggle_voice_listener() -> None:
    mock_listener = MagicMock()
    tray = JarvisTrayApp(voice_listener=mock_listener, voice_enabled=True)

    tray.toggle_voice_listener()
    assert tray.voice_enabled is False
    mock_listener.stop.assert_called_once_with()

    tray.toggle_voice_listener()
    assert tray.voice_enabled is True
    mock_listener.start.assert_called_once_with()


def test_tray_app_toggle_voice_profile() -> None:
    mock_listener = MagicMock()
    mock_listener.voice_profile = "jarvis"
    tray = JarvisTrayApp(voice_listener=mock_listener)

    tray.toggle_voice_profile()
    assert mock_listener.voice_profile == "albedo"

    tray.toggle_voice_profile()
    assert mock_listener.voice_profile == "jarvis"
