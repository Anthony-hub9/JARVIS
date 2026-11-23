from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any

import pystray
import uvicorn
from PIL import Image, ImageDraw

from jarvis.config import settings


def create_tray_icon_image(size: int = 64) -> Image.Image:
    """Generate a cyan/dark JARVIS arc-reactor icon."""
    img = Image.new("RGBA", (size, size), (5, 10, 18, 255))
    draw = ImageDraw.Draw(img)

    pad_outer = max(4, size // 12)
    pad_mid = max(10, size // 5)
    pad_core = max(18, size // 3)

    # Outer cyan ring
    draw.ellipse(
        (pad_outer, pad_outer, size - pad_outer, size - pad_outer),
        outline=(0, 212, 255, 255),
        width=max(2, size // 16),
    )
    # Inner reactor ring
    draw.ellipse(
        (pad_mid, pad_mid, size - pad_mid, size - pad_mid),
        outline=(0, 160, 220, 255),
        width=max(2, size // 24),
    )
    # Bright arc-reactor core
    draw.ellipse(
        (pad_core, pad_core, size - pad_core, size - pad_core),
        fill=(0, 212, 255, 255),
        outline=(180, 245, 255, 255),
        width=max(1, size // 32),
    )
    return img


def _is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    connect_host = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    try:
        with socket.create_connection((connect_host, port), timeout=timeout):
            return True
    except OSError:
        return False


class JarvisTrayApp:
    """Background system tray controller for the JARVIS Hub server."""

    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        self.host = host or settings.hub_host
        self.port = port if port is not None else settings.hub_port
        self.server: uvicorn.Server | None = None
        self.server_thread: threading.Thread | None = None
        self.ollama_proc: subprocess.Popen[Any] | None = None
        self.icon: pystray.Icon | None = None

    @property
    def hud_url(self) -> str:
        return f"http://localhost:{self.port}/"

    def ensure_ollama_running(self, ollama_port: int = 11434) -> bool:
        """Start `ollama serve` in the background if the Ollama port is not open."""
        if _is_port_open("127.0.0.1", ollama_port):
            return False
        ollama_exe = shutil.which("ollama")
        if not ollama_exe:
            return False
        self.ollama_proc = subprocess.Popen(
            [ollama_exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True

    def start_server(self) -> bool:
        """Start uvicorn in a daemon thread unless the port is already open."""
        if _is_port_open(self.host, self.port):
            return False

        config = uvicorn.Config(
            "jarvis.hub.server:app",
            host=self.host,
            port=self.port,
            log_level="warning",
        )
        self.server = uvicorn.Server(config)
        self.server_thread = threading.Thread(
            target=self.server.run,
            name="jarvis-hub-server",
            daemon=True,
        )
        self.server_thread.start()
        return True

    def open_hud(self, _icon: Any = None, _item: Any = None) -> None:
        webbrowser.open(self.hud_url)

    def quit(self, icon: Any = None, _item: Any = None) -> None:
        if self.server is not None:
            self.server.should_exit = True
        if self.ollama_proc is not None:
            try:
                self.ollama_proc.terminate()
            except OSError:
                pass
            self.ollama_proc = None
        target_icon = icon if icon is not None else self.icon
        if target_icon is not None:
            target_icon.stop()

    def run(self) -> None:
        self.ensure_ollama_running()
        self.start_server()
        menu = pystray.Menu(
            pystray.MenuItem("Abrir HUD JARVIS", self.open_hud, default=True),
            pystray.MenuItem("Salir", self.quit),
        )
        self.icon = pystray.Icon(
            "JARVIS",
            create_tray_icon_image(),
            "JARVIS Hub",
            menu=menu,
        )
        self.icon.run()


def _ensure_stdio(log_path: Path | None = None) -> None:
    """Redirect missing stdout/stderr (e.g. under pythonw.exe) so uvicorn does not crash."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    target = log_path or Path("jarvis_tray.log")
    try:
        stream = open(target, "a", encoding="utf-8")
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def main() -> None:
    _ensure_stdio()
    JarvisTrayApp().run()


if __name__ == "__main__":
    main()
