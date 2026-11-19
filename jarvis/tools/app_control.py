"""Dynamic application control for Windows (open/close) and S24+ mobile intent builder."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

WINDOWS_APP_ALLOWLIST: dict[str, list[str]] = {
    "notepad": ["notepad.exe"],
    "calc": ["calc.exe"],
    "chrome": ["chrome.exe"],
    "spotify": ["spotify.exe"],
    "discord": ["discord.exe"],
    "steam": ["steam.exe"],
}

PROTECTED_SYSTEM_PROCESSES: frozenset[str] = frozenset(
    {
        "explorer.exe",
        "csrss.exe",
        "svchost.exe",
        "lsass.exe",
        "wininit.exe",
        "dwm.exe",
        "winlogon.exe",
        "services.exe",
        "smss.exe",
        "system",
        "system idle process",
    }
)

MOBILE_APP_PACKAGES: dict[str, str] = {
    "spotify": "com.spotify.music",
    "discord": "com.discord",
    "chrome": "com.android.chrome",
    "youtube": "com.google.android.youtube",
    "whatsapp": "com.whatsapp",
}

_SAFE_APP_NAME_RE = re.compile(r"^[a-zA-Z0-9 ._\-+()]+$")


def _normalize_key(name: str) -> str:
    cleaned = name.strip().lower()
    return cleaned[:-4] if cleaned.endswith(".exe") else cleaned


def _scan_start_menu_shortcuts(dirs: list[Path]) -> dict[str, list[str]]:
    discovered: dict[str, list[str]] = {}
    for base in dirs:
        if not base.is_dir():
            continue
        for lnk in base.rglob("*.lnk"):
            key = _normalize_key(lnk.stem)
            if key and key not in discovered:
                discovered[key] = ["cmd", "/c", "start", "", str(lnk)]
    return discovered


def _scan_program_dirs(dirs: list[Path]) -> dict[str, list[str]]:
    discovered: dict[str, list[str]] = {}
    for base in dirs:
        if not base.is_dir():
            continue
        for entry in base.iterdir():
            if entry.is_file() and entry.suffix.lower() == ".exe":
                key = _normalize_key(entry.stem)
                discovered.setdefault(key, [str(entry)])
            elif entry.is_dir():
                try:
                    for sub in entry.iterdir():
                        if sub.is_file() and sub.suffix.lower() == ".exe":
                            key = _normalize_key(sub.stem)
                            discovered.setdefault(key, [str(sub)])
                except OSError:
                    continue
    return discovered


def _scan_registry_app_paths() -> dict[str, list[str]]:
    discovered: dict[str, list[str]] = {}
    try:
        import winreg
    except ImportError:
        return discovered

    subkey_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, subkey_path) as key:
                idx = 0
                while True:
                    try:
                        app_subkey = winreg.EnumKey(key, idx)
                        idx += 1
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(key, app_subkey) as sub:
                            exe_path, _ = winreg.QueryValueEx(sub, None)
                            if isinstance(exe_path, str) and exe_path.strip():
                                norm = _normalize_key(app_subkey)
                                discovered.setdefault(norm, [exe_path.strip().strip('"')])
                    except OSError:
                        continue
        except OSError:
            continue
    return discovered


def _scan_start_apps(timeout: float = 5.0) -> dict[str, list[str]]:
    """Discover Microsoft Store / UWP and Start Apps via PowerShell Get-StartApps."""
    discovered: dict[str, list[str]] = {}
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-StartApps | ConvertTo-Json -Compress",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return discovered

    if result.returncode != 0 or not result.stdout or not result.stdout.strip():
        return discovered

    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError, ValueError):
        return discovered

    items = [payload] if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return discovered

    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("Name")
        app_id = item.get("AppID")
        if not isinstance(name, str) or not isinstance(app_id, str):
            continue
        key = _normalize_key(name)
        cleaned_id = app_id.strip()
        if key and cleaned_id and key not in discovered:
            discovered[key] = ["explorer.exe", f"shell:AppsFolder\\{cleaned_id}"]

    return discovered


def discover_windows_apps() -> dict[str, list[str]]:
    """Discover launchable Windows apps from Start Menu, Program Files, Registry, and Start Apps."""
    apps: dict[str, list[str]] = {}

    start_dirs = [
        Path(p)
        for p in (
            os.environ.get("ProgramData", ""),
            os.environ.get("APPDATA", ""),
        )
        if p
    ]
    start_menu_paths = [d / "Microsoft" / "Windows" / "Start Menu" / "Programs" for d in start_dirs]
    apps.update(_scan_start_menu_shortcuts(start_menu_paths))

    program_dirs = [
        Path(p)
        for p in (
            os.environ.get("ProgramFiles", ""),
            os.environ.get("ProgramFiles(x86)", ""),
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs")
            if os.environ.get("LOCALAPPDATA")
            else "",
        )
        if p
    ]
    for k, cmd in _scan_program_dirs(program_dirs).items():
        apps.setdefault(k, cmd)

    for k, cmd in _scan_registry_app_paths().items():
        apps.setdefault(k, cmd)

    for k, cmd in _scan_start_apps().items():
        apps.setdefault(k, cmd)

    return apps


class AppController:
    """Safely discover, launch, and close Windows applications."""

    def __init__(
        self,
        allowlist: dict[str, list[str]] | None = None,
        discover: bool = True,
    ) -> None:
        self.allowlist: dict[str, list[str]] = (
            dict(allowlist) if allowlist is not None else dict(WINDOWS_APP_ALLOWLIST)
        )
        self._discovered: dict[str, list[str]] = discover_windows_apps() if discover else {}

    def refresh_discovered(self) -> dict[str, list[str]]:
        """Re-scan installed Windows applications."""
        self._discovered = discover_windows_apps()
        return dict(self._discovered)

    def list_available_apps(self) -> list[str]:
        """Return sorted list of known application names."""
        return sorted(set(self.allowlist) | set(self._discovered))

    def _resolve_command(self, app_name: str) -> list[str] | None:
        raw = app_name.strip()
        if not raw or not _SAFE_APP_NAME_RE.match(raw):
            return None

        key = _normalize_key(raw)
        if key in self.allowlist:
            return self.allowlist[key]
        if key in self._discovered:
            return self._discovered[key]

        which_hit = shutil.which(raw) or shutil.which(f"{key}.exe")
        if which_hit:
            return [which_hit]
        return None

    def launch_app(self, app_name: str) -> subprocess.Popen[bytes]:
        """Launch a known or dynamically discovered Windows app via subprocess.Popen."""
        cmd = self._resolve_command(app_name)
        if cmd is None:
            raise ValueError(f"Application '{app_name}' not found or not in the allowlist.")
        return subprocess.Popen(cmd)

    def _resolve_process_name(self, app_name: str) -> str:
        raw = app_name.strip()
        if not raw or not _SAFE_APP_NAME_RE.match(raw):
            raise ValueError(f"Invalid application name '{app_name}'.")

        key = _normalize_key(raw)
        cmd = self.allowlist.get(key) or self._discovered.get(key)
        if cmd:
            if len(cmd) >= 2 and cmd[1].startswith("shell:AppsFolder\\"):
                proc_name = f"{key}.exe"
            else:
                candidate = Path(cmd[-1]).name
                if candidate.lower().endswith(".exe"):
                    proc_name = candidate.lower()
                else:
                    proc_name = f"{key}.exe"
        else:
            proc_name = raw.lower() if raw.lower().endswith(".exe") else f"{key}.exe"

        if proc_name in PROTECTED_SYSTEM_PROCESSES or _normalize_key(proc_name) in PROTECTED_SYSTEM_PROCESSES:
            raise ValueError(f"Refusing to close protected system process '{proc_name}'.")
        return proc_name

    def _find_running_uwp_process(self, key: str, tried_proc: str) -> str | None:
        """Find a running process matching a UWP app key (e.g. WhatsApp.Root.exe)."""
        try:
            tl = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        if tl.returncode != 0 or not tl.stdout:
            return None

        compact_key = re.sub(r"[^a-z0-9]", "", key)
        if not compact_key:
            return None

        for row in csv.reader(io.StringIO(tl.stdout)):
            if not row:
                continue
            image = row[0].strip().lower()
            if not image.endswith(".exe") or image == tried_proc:
                continue
            if image in PROTECTED_SYSTEM_PROCESSES or _normalize_key(image) in PROTECTED_SYSTEM_PROCESSES:
                continue
            norm_img = _normalize_key(image)
            compact_img = re.sub(r"[^a-z0-9]", "", norm_img)
            if norm_img == key or norm_img.startswith(f"{key}.") or compact_img.startswith(compact_key):
                return image
        return None

    def close_app(self, app_name: str) -> dict[str, Any]:
        """Safely terminate a non-system Windows process via taskkill."""
        proc_name = self._resolve_process_name(app_name)
        result = subprocess.run(
            ["taskkill", "/IM", proc_name, "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            key = _normalize_key(app_name)
            cmd = self.allowlist.get(key) or self._discovered.get(key)
            if cmd and len(cmd) >= 2 and cmd[1].startswith("shell:AppsFolder\\"):
                alt_proc = self._find_running_uwp_process(key, proc_name)
                if alt_proc:
                    proc_name = alt_proc
                    result = subprocess.run(
                        ["taskkill", "/IM", proc_name, "/F"],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
        return {
            "process": proc_name,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }


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
