from __future__ import annotations

from unittest.mock import MagicMock, patch

from PIL import Image

from jarvis.clients.tray_app import JarvisTrayApp, create_tray_icon_image


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
    tray = JarvisTrayApp()
    mock_server = MagicMock()
    mock_server.should_exit = False
    mock_icon = MagicMock()
    tray.server = mock_server
    tray.icon = mock_icon

    tray.quit(mock_icon)

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
    tray = JarvisTrayApp(host="127.0.0.1", port=8000)
    mock_server = MagicMock()
    mock_icon = MagicMock()

    with (
        patch("jarvis.clients.tray_app._is_port_open", return_value=False),
        patch("jarvis.clients.tray_app.uvicorn.Config") as mock_config_cls,
        patch("jarvis.clients.tray_app.uvicorn.Server", return_value=mock_server),
        patch("jarvis.clients.tray_app.threading.Thread") as mock_thread_cls,
        patch("jarvis.clients.tray_app.pystray.Icon", return_value=mock_icon) as mock_icon_cls,
    ):
        tray.run()

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
    mock_icon.run.assert_called_once()
