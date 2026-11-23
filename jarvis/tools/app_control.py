"""Dynamic application control for Windows (open/close) and S24+ mobile intent builder."""

from __future__ import annotations

import csv
import difflib
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

PROCESS_ALIASES: dict[str, str] = {
    "calculadora": "calculatorapp.exe",
    "calculator": "calculatorapp.exe",
    "calc": "calculatorapp.exe",
    "cliente de riot": "riotclientservices.exe",
    "riot client": "riotclientservices.exe",
    "riot": "riotclientservices.exe",
    "microsoft edge": "msedge.exe",
    "edge": "msedge.exe",
    "visual studio code": "code.exe",
    "vscode": "code.exe",
    "word": "winword.exe",
    "excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
}

MOBILE_APP_PACKAGES: dict[str, str] = {
    "spotify": "com.spotify.music",
    "discord": "com.discord",
    "chrome": "com.android.chrome",
    "youtube": "com.google.android.youtube",
    "whatsapp": "com.whatsapp",
    "calculadora": "com.sec.android.app.popupcalculator",
    "calculator": "com.sec.android.app.popupcalculator",
    "calc": "com.sec.android.app.popupcalculator",
    "camara": "com.sec.android.app.camera",
    "cámara": "com.sec.android.app.camera",
    "camera": "com.sec.android.app.camera",
    "reloj": "com.sec.android.app.clockpackage",
    "clock": "com.sec.android.app.clockpackage",
    "ajustes": "com.android.settings",
    "settings": "com.android.settings",
    "maps": "com.google.android.apps.maps",
    "gmail": "com.google.android.gm",
    "instagram": "com.instagram.android",
    "galeria": "com.sec.android.gallery3d",
    "galería": "com.sec.android.gallery3d",
    "gallery": "com.sec.android.gallery3d",
    "notas": "com.samsung.android.app.notes",
    "notes": "com.samsung.android.app.notes",
    "telefono": "com.samsung.android.dialer",
    "teléfono": "com.samsung.android.dialer",
    "phone": "com.samsung.android.dialer",
    "mensajes": "com.samsung.android.messaging",
    "messages": "com.samsung.android.messaging",
    "calendario": "com.samsung.android.calendar",
    "calendar": "com.samsung.android.calendar",
}

MOBILE_WEB_SCHEMES: dict[str, str] = {
    "whatsapp": "whatsapp://",
    "spotify": "spotify://",
    "youtube": "https://www.youtube.com",
    "maps": "https://maps.google.com",
    "instagram": "instagram://",
    "gmail": "mailto:",
    "telefono": "tel:",
    "teléfono": "tel:",
    "phone": "tel:",
}

_SAFE_APP_NAME_RE = re.compile(r"^[a-zA-Z0-9 ._\-+()]+$")

_FILLER_WORDS: frozenset[str] = frozenset(
    {"el", "la", "los", "las", "de", "del", "the", "of", "app", "aplicacion", "aplicación"}
)


def _normalize_key(name: str) -> str:
    cleaned = name.strip().lower()
    return cleaned[:-4] if cleaned.endswith(".exe") else cleaned


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _clean_tokens(text: str) -> list[str]:
    return [tok for tok in _tokenize(text) if tok not in _FILLER_WORDS]


def _scan_start_menu_shortcuts(dirs: list[Path]) -> dict[str, list[str]]:
    discovered: dict[str, list[str]] = {}
    for base in dirs:
        if not base.is_dir():
            continue
        for lnk in base.rglob("*.lnk"):
            key = _normalize_key(lnk.stem)
            if key and key not in discovered:
                discovered[key] = ["explorer.exe", str(lnk)]
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
        self._is_custom_allowlist: bool = allowlist is not None
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

    def _prefer_allowlist(self, key: str, cmd: list[str]) -> list[str]:
        """Use allowlist command only if custom, absolute, or on PATH; else prefer discovered."""
        if (
            self._is_custom_allowlist
            or not cmd
            or Path(cmd[0]).is_absolute()
            or shutil.which(cmd[0])
        ):
            return cmd
        if key in self._discovered:
            return self._discovered[key]
        return cmd

    def _fuzzy_match_entry(self, key: str) -> tuple[str, list[str]] | None:
        resolved_allowlist = {
            k: self._prefer_allowlist(k, v) for k, v in self.allowlist.items()
        }
        combined = {**self._discovered, **resolved_allowlist}
        if not combined:
            return None

        cleaned_tokens = _clean_tokens(key)
        if not cleaned_tokens:
            return None
        cleaned_key = " ".join(cleaned_tokens)

        substring_hits = [k for k in combined if cleaned_key in k]
        if substring_hits:
            best = min(substring_hits, key=len)
            return best, combined[best]

        query_token_set = set(cleaned_tokens)
        token_hits = [k for k in combined if query_token_set.issubset(set(_tokenize(k)))]
        if token_hits:
            best = min(token_hits, key=len)
            return best, combined[best]

        close = difflib.get_close_matches(cleaned_key, combined.keys(), n=1, cutoff=0.75)
        if close:
            best = close[0]
            return best, combined[best]

        return None

    def _resolve_entry(self, key: str) -> tuple[str, list[str]] | None:
        if key in self.allowlist:
            return key, self._prefer_allowlist(key, self.allowlist[key])
        if key in self._discovered:
            return key, self._discovered[key]
        return self._fuzzy_match_entry(key)

    def _resolve_command(self, app_name: str) -> list[str] | None:
        raw = app_name.strip()
        if not raw or not _SAFE_APP_NAME_RE.match(raw):
            return None

        key = _normalize_key(raw)
        if key in self.allowlist:
            return self._prefer_allowlist(key, self.allowlist[key])
        if key in self._discovered:
            return self._discovered[key]

        which_hit = shutil.which(raw) or shutil.which(f"{key}.exe")
        if which_hit:
            return [which_hit]

        fuzzy = self._fuzzy_match_entry(key)
        if fuzzy is not None:
            return fuzzy[1]
        return None

    def launch_app(self, app_name: str) -> subprocess.Popen[bytes]:
        """Launch a known or dynamically discovered Windows app via subprocess.Popen."""
        cmd = self._resolve_command(app_name)
        if cmd is None:
            raise ValueError(f"Application '{app_name}' not found or not in the allowlist.")
        return subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _resolve_process_name(self, app_name: str) -> str:
        raw = app_name.strip()
        if not raw or not _SAFE_APP_NAME_RE.match(raw):
            raise ValueError(f"Invalid application name '{app_name}'.")

        key = _normalize_key(raw)
        if key in PROTECTED_SYSTEM_PROCESSES or f"{key}.exe" in PROTECTED_SYSTEM_PROCESSES:
            raise ValueError(f"Refusing to close protected system process '{key}.exe'.")

        if key in PROCESS_ALIASES:
            proc_name = PROCESS_ALIASES[key]
        else:
            entry = self._resolve_entry(key)
            if entry is not None:
                matched_key, cmd = entry
                if len(cmd) >= 2 and cmd[1].startswith("shell:AppsFolder\\"):
                    proc_name = f"{matched_key}.exe"
                else:
                    candidate = Path(cmd[-1]).name
                    if candidate.lower().endswith(".exe"):
                        proc_name = candidate.lower()
                    elif candidate.lower().endswith(".lnk"):
                        proc_name = f"{Path(cmd[-1]).stem.lower()}.exe"
                    else:
                        proc_name = f"{matched_key}.exe"
            else:
                proc_name = raw.lower() if raw.lower().endswith(".exe") else f"{key}.exe"

        if proc_name in PROTECTED_SYSTEM_PROCESSES or _normalize_key(proc_name) in PROTECTED_SYSTEM_PROCESSES:
            raise ValueError(f"Refusing to close protected system process '{proc_name}'.")
        return proc_name

    def _find_running_uwp_process(self, key: str, tried_proc: str) -> str | None:
        """Find a running process matching a UWP app key or window title."""
        try:
            tl = subprocess.run(
                ["tasklist", "/V", "/FO", "CSV", "/NH"],
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

        def _matches(candidate: str) -> bool:
            if not candidate:
                return False
            compact_cand = re.sub(r"[^a-z0-9]", "", candidate)
            if not compact_cand:
                return False
            return (
                candidate == key
                or candidate.startswith(f"{key}.")
                or compact_cand.startswith(compact_key)
                or (len(compact_key) >= 4 and compact_key in compact_cand)
            )

        for row in csv.reader(io.StringIO(tl.stdout)):
            if not row:
                continue
            image = row[0].strip().lower()
            if not image.endswith(".exe") or image == tried_proc:
                continue
            if image in PROTECTED_SYSTEM_PROCESSES or _normalize_key(image) in PROTECTED_SYSTEM_PROCESSES:
                continue
            norm_img = _normalize_key(image)
            window_title = row[-1].strip().lower() if len(row) > 1 else ""
            if _matches(norm_img) or _matches(window_title):
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
            entry = self._resolve_entry(key)
            search_key = entry[0] if entry is not None else (" ".join(_clean_tokens(key)) or key)
            alt_proc = self._find_running_uwp_process(search_key, proc_name)
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
    package = MOBILE_APP_PACKAGES[key]
    if key in MOBILE_WEB_SCHEMES:
        intent_url = MOBILE_WEB_SCHEMES[key]
        requires_native_bridge = False
    else:
        intent_url = ""
        requires_native_bridge = True
    return {
        "device": "s24_plus",
        "action": "android.intent.action.MAIN",
        "category": "android.intent.category.LAUNCHER",
        "package": package,
        "app_name": key,
        "intent_url": intent_url,
        "requires_native_bridge": requires_native_bridge,
    }
