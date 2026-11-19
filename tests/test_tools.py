"""Unit tests for JARVIS tools (AppController and mobile intents)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jarvis.tools.app_control import AppController, build_mobile_intent


def test_app_controller_accepts_allowlisted_app() -> None:
    controller = AppController()
    fake_proc = MagicMock()

    with patch("jarvis.tools.app_control.subprocess.Popen", return_value=fake_proc) as popen_mock:
        proc = controller.launch_app("notepad")

    assert proc is fake_proc
    popen_mock.assert_called_once_with(["notepad.exe"])


def test_app_controller_rejects_unknown_app() -> None:
    controller = AppController()

    with patch("jarvis.tools.app_control.subprocess.Popen") as popen_mock:
        with pytest.raises(ValueError, match="not in the allowlist"):
            controller.launch_app("rm -rf /")

    popen_mock.assert_not_called()


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
