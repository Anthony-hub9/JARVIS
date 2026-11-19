"""Unit tests for JARVIS tools (AppController, dynamic discovery/close, and mobile intents)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from jarvis.tools.app_control import (
    PROTECTED_SYSTEM_PROCESSES,
    AppController,
    _scan_start_menu_shortcuts,
    build_mobile_intent,
)


def test_app_controller_accepts_allowlisted_app() -> None:
    controller = AppController(discover=False)
    fake_proc = MagicMock()

    with patch("jarvis.tools.app_control.subprocess.Popen", return_value=fake_proc) as popen_mock:
        proc = controller.launch_app("notepad")

    assert proc is fake_proc
    popen_mock.assert_called_once_with(["notepad.exe"])


def test_app_controller_rejects_unknown_app() -> None:
    controller = AppController(discover=False)

    with patch("jarvis.tools.app_control.subprocess.Popen") as popen_mock:
        with pytest.raises(ValueError, match="not in the allowlist"):
            controller.launch_app("rm -rf /")

    popen_mock.assert_not_called()


def test_dynamic_discovery_start_menu_and_which(tmp_path: Path) -> None:
    lnk_file = tmp_path / "VLC Media Player.lnk"
    lnk_file.write_text("", encoding="utf-8")

    discovered = _scan_start_menu_shortcuts([tmp_path])
    assert "vlc media player" in discovered
    assert discovered["vlc media player"] == ["cmd", "/c", "start", "", str(lnk_file)]

    controller = AppController(allowlist={}, discover=False)
    with patch("jarvis.tools.app_control.shutil.which", return_value=r"C:\Tools\ffmpeg.exe"):
        with patch("jarvis.tools.app_control.subprocess.Popen", return_value=MagicMock()) as popen_mock:
            controller.launch_app("ffmpeg")

    popen_mock.assert_called_once_with([r"C:\Tools\ffmpeg.exe"])


def test_app_controller_close_app_calls_taskkill() -> None:
    controller = AppController(discover=False)
    fake_done = SimpleNamespace(returncode=0, stdout="SUCCESS", stderr="")

    with patch("jarvis.tools.app_control.subprocess.run", return_value=fake_done) as run_mock:
        res = controller.close_app("notepad")

    run_mock.assert_called_once_with(
        ["taskkill", "/IM", "notepad.exe", "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res["process"] == "notepad.exe"
    assert res["returncode"] == 0


@pytest.mark.parametrize("proc", sorted(PROTECTED_SYSTEM_PROCESSES))
def test_app_controller_blocks_protected_system_processes(proc: str) -> None:
    controller = AppController(discover=False)

    with patch("jarvis.tools.app_control.subprocess.run") as run_mock:
        with pytest.raises(ValueError, match="protected system process"):
            controller.close_app(proc)

    run_mock.assert_not_called()


def test_build_mobile_intent_for_s24_plus() -> None:
    intent = build_mobile_intent("Spotify")

    assert intent == {
        "device": "s24_plus",
        "action": "android.intent.action.MAIN",
        "category": "android.intent.category.LAUNCHER",
        "package": "com.spotify.music",
        "app_name": "spotify",
    }


def test_build_mobile_intent_rejects_unknown_app() -> None:
    with pytest.raises(ValueError, match="not supported"):
        build_mobile_intent("unknown_app")
