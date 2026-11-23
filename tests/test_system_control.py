"""Unit tests for SystemController (time, status, media keys, folders/URLs, power)."""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

import jarvis.tools.system_control as sc_mod
from jarvis.tools.system_control import SystemController

_NO_WINDOW_KWARGS = {
    "stdin": subprocess.DEVNULL,
    "stdout": subprocess.DEVNULL,
    "stderr": subprocess.DEVNULL,
    "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
}


def test_get_time_info_formats_spanish_datetime() -> None:
    ctrl = SystemController()
    fixed = datetime(2026, 11, 23, 14, 5)  # Monday
    info = ctrl.get_time_info(now=fixed)

    assert info["time"] == "14:05"
    assert info["date"] == "23/11/2026"
    assert info["weekday"] == "lunes"
    assert info["formatted"] == "Son las 14:05 del lunes 23/11/2026"


def test_get_system_status_with_and_without_battery() -> None:
    ctrl = SystemController()
    fake_psutil = SimpleNamespace(
        cpu_percent=MagicMock(return_value=24.6),
        virtual_memory=MagicMock(
            return_value=SimpleNamespace(
                used=8 * (1024**3),
                total=16 * (1024**3),
                percent=50.0,
            )
        ),
        disk_usage=MagicMock(return_value=SimpleNamespace(free=120 * (1024**3))),
        sensors_battery=MagicMock(return_value=SimpleNamespace(percent=82.0, power_plugged=True)),
    )

    with patch.object(sc_mod, "psutil", fake_psutil):
        status = ctrl.get_system_status()

    assert status["cpu_percent"] == 24.6
    assert status["ram_used_gb"] == 8.0
    assert status["ram_total_gb"] == 16.0
    assert status["disk_free_gb"] == 120.0
    assert status["battery_percent"] == 82.0
    assert status["power_plugged"] is True
    assert "CPU al 24.6%" in status["formatted"]
    assert "batería al 82.0% (conectada)" in status["formatted"]

    fake_psutil.sensors_battery.return_value = None
    with patch.object(sc_mod, "psutil", fake_psutil):
        desktop_status = ctrl.get_system_status()
    assert desktop_status["battery_percent"] is None
    assert "batería" not in desktop_status["formatted"]


def test_get_system_status_fallback_when_psutil_missing() -> None:
    ctrl = SystemController()
    with patch.object(sc_mod, "psutil", None):
        status = ctrl.get_system_status()
    assert status["cpu_percent"] is None
    assert "psutil no está disponible" in status["formatted"]


@pytest.mark.parametrize(
    ("action", "expected_vk"),
    [
        ("volume_up", 0xAF),
        ("volume_down", 0xAE),
        ("mute", 0xAD),
        ("play_pause", 0xB3),
        ("next_track", 0xB0),
        ("prev_track", 0xB1),
    ],
)
def test_media_action_sends_windows_keybd_event(action: str, expected_vk: int) -> None:
    ctrl = SystemController()
    fake_user32 = MagicMock()
    fake_ctypes = SimpleNamespace(windll=SimpleNamespace(user32=fake_user32))

    with (
        patch.object(sc_mod.sys, "platform", "win32"),
        patch.object(sc_mod, "ctypes", fake_ctypes),
    ):
        msg = ctrl.media_action(action)

    assert msg
    assert fake_user32.keybd_event.call_args_list == [
        call(expected_vk, 0, 0, 0),
        call(expected_vk, 0, 0x0002, 0),
    ]


def test_media_action_rejects_unknown_and_handles_non_windows() -> None:
    ctrl = SystemController()
    with pytest.raises(ValueError, match="Unknown media action"):
        ctrl.media_action("invalid_action")

    with patch.object(sc_mod.sys, "platform", "linux"):
        msg = ctrl.media_action("mute")
    assert "no soportada" in msg


def test_open_target_opens_folders_and_urls() -> None:
    ctrl = SystemController()

    with (
        patch("jarvis.tools.system_control.Path.home", return_value=Path(r"C:\Users\Test")),
        patch("jarvis.tools.system_control.subprocess.Popen") as popen_mock,
    ):
        msg = ctrl.open_target("descargas")

    assert "descargas" in msg
    popen_mock.assert_called_once_with(
        ["explorer.exe", str(Path(r"C:\Users\Test") / "Downloads")],
        **_NO_WINDOW_KWARGS,
    )

    with patch("jarvis.tools.system_control.webbrowser.open") as wb_mock:
        yt_msg = ctrl.open_target("youtube")
        custom_msg = ctrl.open_target("https://example.com")

    assert "youtube" in yt_msg
    assert "https://example.com" in custom_msg
    assert wb_mock.call_args_list == [
        call("https://www.youtube.com"),
        call("https://example.com"),
    ]

    with pytest.raises(ValueError, match="Unknown target"):
        ctrl.open_target("desconocido")


def test_power_action_lock_and_sleep() -> None:
    ctrl = SystemController()
    with (
        patch.object(sc_mod.sys, "platform", "win32"),
        patch("jarvis.tools.system_control.subprocess.Popen") as popen_mock,
    ):
        lock_msg = ctrl.power_action("lock")
        sleep_msg = ctrl.power_action("sleep")

    assert "Bloqueando" in lock_msg
    assert "Suspendiendo" in sleep_msg
    assert popen_mock.call_args_list == [
        call(["rundll32.exe", "user32.dll,LockWorkStation"], **_NO_WINDOW_KWARGS),
        call(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], **_NO_WINDOW_KWARGS),
    ]

    with pytest.raises(ValueError, match="Unknown power action"):
        ctrl.power_action("shutdown")

    with patch.object(sc_mod.sys, "platform", "linux"):
        assert "no soportada" in ctrl.power_action("lock")
