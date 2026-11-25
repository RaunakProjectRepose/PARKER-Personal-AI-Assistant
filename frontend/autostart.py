"""Optional: start PARKER quietly in the tray when you log in to Windows.

Off by default. Turning it on adds one entry for your user account under
HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run (the same
place Windows' own "Startup apps" setting manages); turning it off removes it.
"""

from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "PARKER"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = PROJECT_ROOT / "parker.pyw"


def _winreg():
    import winreg  # Windows only

    return winreg


def launch_command(python: str | None = None) -> str:
    """pythonw.exe runs PARKER without a console window."""
    exe = Path(python or sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw
    return f'"{exe}" "{LAUNCHER}" --background'


def supported() -> bool:
    return sys.platform == "win32"


def is_enabled(winreg=None) -> bool:
    winreg = winreg or _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except FileNotFoundError:
        return False


def enable(winreg=None, command: str | None = None) -> None:
    winreg = winreg or _winreg()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command or launch_command())


def disable(winreg=None) -> None:
    winreg = winreg or _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass
