"""Allowlisted application control for Windows and S24+ mobile intent builder."""

from __future__ import annotations

import subprocess
from typing import Any

WINDOWS_APP_ALLOWLIST: dict[str, list[str]] = {
    "notepad": ["notepad.exe"],
    "calc": ["calc.exe"],
    "chrome": ["chrome.exe"],
    "spotify": ["spotify.exe"],
    "discord": ["discord.exe"],
    "steam": ["steam.exe"],
}

MOBILE_APP_PACKAGES: dict[str, str] = {
    "spotify": "com.spotify.music",
    "discord": "com.discord",
    "chrome": "com.android.chrome",
    "youtube": "com.google.android.youtube",
    "whatsapp": "com.whatsapp",
}


class AppController:
    """Safely launch allowlisted Windows applications."""

    def __init__(self, allowlist: dict[str, list[str]] | None = None) -> None:
        self.allowlist = allowlist if allowlist is not None else dict(WINDOWS_APP_ALLOWLIST)

    def launch_app(self, app_name: str) -> subprocess.Popen[bytes]:
        """Launch an allowlisted Windows app via subprocess.Popen."""
        key = app_name.strip().lower()
        if key not in self.allowlist:
            raise ValueError(f"Application '{app_name}' is not in the allowlist.")
        cmd = self.allowlist[key]
        return subprocess.Popen(cmd)


def build_mobile_intent(app_name: str) -> dict[str, Any]:
    """Build an Android intent payload for S24+ app launching."""
    key = app_name.strip().lower()
    if key not in MOBILE_APP_PACKAGES:
        raise ValueError(f"Mobile application '{app_name}' is not supported.")
    return {
        "device": "s24_plus",
        "action": "android.intent.action.MAIN",
        "category": "android.intent.category.LAUNCHER",
        "package": MOBILE_APP_PACKAGES[key],
        "app_name": key,
    }
