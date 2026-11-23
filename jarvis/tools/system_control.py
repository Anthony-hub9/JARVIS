"""System control utilities for time, hardware status, media keys, folders/URLs, and power."""

from __future__ import annotations

import ctypes
import logging
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:  # pragma: no cover - fallback when psutil is absent
    psutil = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_SPANISH_WEEKDAYS = (
    "lunes",
    "martes",
    "miércoles",
    "jueves",
    "viernes",
    "sábado",
    "domingo",
)

_MEDIA_VK_CODES: dict[str, tuple[int, str]] = {
    "volume_up": (0xAF, "Subiendo el volumen."),
    "volume_down": (0xAE, "Bajando el volumen."),
    "mute": (0xAD, "Silenciando el audio."),
    "play_pause": (0xB3, "Alternando reproducción y pausa."),
    "next_track": (0xB0, "Pasando a la siguiente pista."),
    "prev_track": (0xB1, "Volviendo a la pista anterior."),
}

_USER_FOLDER_MAP: dict[str, str] = {
    "descargas": "Downloads",
    "downloads": "Downloads",
    "documentos": "Documents",
    "documents": "Documents",
    "escritorio": "Desktop",
    "desktop": "Desktop",
    "imagenes": "Pictures",
    "imágenes": "Pictures",
    "pictures": "Pictures",
    "musica": "Music",
    "música": "Music",
    "music": "Music",
    "videos": "Videos",
}

_QUICK_WEB_URLS: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "github": "https://github.com",
    "twitch": "https://www.twitch.tv",
    "netflix": "https://www.netflix.com",
}

_POWER_COMMANDS: dict[str, tuple[list[str], str]] = {
    "lock": (["rundll32.exe", "user32.dll,LockWorkStation"], "Bloqueando la pantalla."),
    "sleep": (["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], "Suspendiendo el equipo."),
}

_KEYEVENTF_KEYUP = 0x0002


def _subprocess_no_window_kwargs() -> dict[str, Any]:
    return {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }


class SystemController:
    """Controls local PC time/status queries, media keys, folders/URLs, and power actions."""

    def get_time_info(self, now: datetime | None = None) -> dict[str, str]:
        """Return local time, date, and weekday formatted in Spanish."""
        current = now or datetime.now()
        weekday = _SPANISH_WEEKDAYS[current.weekday()]
        time_str = current.strftime("%H:%M")
        date_str = current.strftime("%d/%m/%Y")
        return {
            "time": time_str,
            "date": date_str,
            "weekday": weekday,
            "formatted": f"Son las {time_str} del {weekday} {date_str}",
        }

    def get_system_status(self) -> dict[str, Any]:
        """Return CPU, RAM, disk, and battery metrics with graceful fallback."""
        if psutil is None:
            return {
                "cpu_percent": None,
                "ram_used_gb": None,
                "ram_total_gb": None,
                "ram_percent": None,
                "disk_free_gb": None,
                "battery_percent": None,
                "power_plugged": None,
                "formatted": "psutil no está disponible para consultar el estado del sistema.",
            }

        cpu_percent: float | None = None
        ram_used_gb: float | None = None
        ram_total_gb: float | None = None
        ram_percent: float | None = None
        disk_free_gb: float | None = None
        battery_percent: float | None = None
        power_plugged: bool | None = None

        try:
            cpu_percent = round(float(psutil.cpu_percent(interval=0.1)), 1)
        except Exception as exc:
            logger.warning("Failed to read CPU usage: %s", exc)

        try:
            mem = psutil.virtual_memory()
            ram_used_gb = round(mem.used / (1024**3), 1)
            ram_total_gb = round(mem.total / (1024**3), 1)
            ram_percent = round(float(mem.percent), 1)
        except Exception as exc:
            logger.warning("Failed to read memory usage: %s", exc)

        try:
            root_path = Path.home().anchor or "/"
            disk = psutil.disk_usage(root_path)
            disk_free_gb = round(disk.free / (1024**3), 1)
        except Exception as exc:
            logger.warning("Failed to read disk usage: %s", exc)

        try:
            battery = psutil.sensors_battery()
            if battery is not None:
                battery_percent = round(float(battery.percent), 1)
                power_plugged = bool(battery.power_plugged)
        except Exception as exc:
            logger.warning("Failed to read battery status: %s", exc)

        parts: list[str] = []
        if cpu_percent is not None:
            parts.append(f"CPU al {cpu_percent}%")
        if ram_used_gb is not None and ram_total_gb is not None:
            parts.append(f"RAM {ram_used_gb}/{ram_total_gb} GB")
        if disk_free_gb is not None:
            parts.append(f"disco libre {disk_free_gb} GB")
        if battery_percent is not None:
            plug_state = "conectada" if power_plugged else "sin conectar"
            parts.append(f"batería al {battery_percent}% ({plug_state})")

        formatted = (
            "Estado del sistema: " + ", ".join(parts) + "."
            if parts
            else "No se pudieron obtener métricas del sistema."
        )
        return {
            "cpu_percent": cpu_percent,
            "ram_used_gb": ram_used_gb,
            "ram_total_gb": ram_total_gb,
            "ram_percent": ram_percent,
            "disk_free_gb": disk_free_gb,
            "battery_percent": battery_percent,
            "power_plugged": power_plugged,
            "formatted": formatted,
        }

    def media_action(self, action: str) -> str:
        """Send a Windows media/volume virtual-key event."""
        norm = action.strip().lower()
        if norm not in _MEDIA_VK_CODES:
            raise ValueError(f"Unknown media action: '{action}'")

        vk_code, message = _MEDIA_VK_CODES[norm]
        if sys.platform != "win32" or not hasattr(ctypes, "windll"):
            return f"Acción multimedia '{norm}' no soportada en esta plataforma."

        user32 = ctypes.windll.user32
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, _KEYEVENTF_KEYUP, 0)
        return message

    def open_target(self, target: str) -> str:
        """Open a standard user folder in Explorer or a quick web URL in the browser."""
        cleaned = target.strip()
        norm = cleaned.lower()

        if norm in _USER_FOLDER_MAP:
            folder_path = Path.home() / _USER_FOLDER_MAP[norm]
            subprocess.Popen(["explorer.exe", str(folder_path)], **_subprocess_no_window_kwargs())
            return f"Abriendo carpeta '{norm}'."

        if norm in _QUICK_WEB_URLS:
            url = _QUICK_WEB_URLS[norm]
            webbrowser.open(url)
            return f"Abriendo {norm} en el navegador."

        if norm.startswith(("https://", "http://")):
            webbrowser.open(cleaned)
            return f"Abriendo {cleaned} en el navegador."

        raise ValueError(f"Unknown target: '{target}'")

    def power_action(self, action: str) -> str:
        """Lock or sleep the Windows workstation."""
        norm = action.strip().lower()
        if norm not in _POWER_COMMANDS:
            raise ValueError(f"Unknown power action: '{action}'")

        cmd, message = _POWER_COMMANDS[norm]
        if sys.platform != "win32":
            return f"Acción de energía '{norm}' no soportada en esta plataforma."

        subprocess.Popen(cmd, **_subprocess_no_window_kwargs())
        return message
