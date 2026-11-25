from __future__ import annotations

import sys
import winreg
from pathlib import Path

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "JARVIS_Hub"


def build_autostart_command(
    python_exe: Path | None = None,
    script_path: Path | None = None,
) -> str:
    """Build the quoted Windows Run registry command pointing to pythonw.exe and start_jarvis_tray.pyw."""
    exe = Path(python_exe) if python_exe is not None else Path(sys.executable)
    if exe.name.lower() == "python.exe":
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            exe = pythonw

    tray_script = (
        Path(script_path)
        if script_path is not None
        else Path(__file__).resolve().parents[2] / "start_jarvis_tray.pyw"
    )
    return f'"{exe}" "{tray_script}"'


def is_autostart_enabled(value_name: str = VALUE_NAME) -> bool:
    """Return True when the JARVIS Hub autostart value exists in HKCU Run."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
            return bool(str(value).strip())
    except OSError:
        return False


def enable_autostart(command: str | None = None, value_name: str = VALUE_NAME) -> str:
    """Register JARVIS Hub in HKCU Run and return the configured command string."""
    cmd = command or build_autostart_command()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH) as key:
        winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, cmd)
    return cmd


def disable_autostart(value_name: str = VALUE_NAME) -> bool:
    """Remove JARVIS Hub from HKCU Run. Returns True if removed, False if not present."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, value_name)
            return True
    except FileNotFoundError:
        return False


def toggle_autostart() -> bool:
    """Toggle Windows autostart for JARVIS Hub and return the new enabled state."""
    if is_autostart_enabled():
        disable_autostart()
        return False
    enable_autostart()
    return True
