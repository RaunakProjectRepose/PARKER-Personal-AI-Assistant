"""A system-wide hotkey (default Ctrl+Alt+P) that works from any app.

Uses Windows' own RegisterHotKey: Windows tells PARKER only when that exact
combination is pressed. Unlike keyboard-hook libraries, PARKER never sees any
other keystrokes, and no administrator rights are needed.
"""

from __future__ import annotations

import ctypes
import os
import sys
import threading
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal

DEFAULT_HOTKEY = "Ctrl+Alt+P"  # "P for PARKER"
# Tried in order when the default is already taken by another app. (Ctrl+Alt+Space
# clashes with the Claude desktop app's quick-launch shortcut, for example.)
FALLBACK_HOTKEYS = ["Ctrl+Alt+P", "Ctrl+Shift+Space", "Ctrl+Alt+Space", "Ctrl+Alt+F12"]

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x1, 0x2, 0x4, 0x8, 0x4000
WM_HOTKEY, WM_QUIT = 0x0312, 0x0012
HOTKEY_ID = 0x5041  # "PA"

_MODIFIERS = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT,
              "shift": MOD_SHIFT, "win": MOD_WIN}
_KEYS = {"space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
         "insert": 0x2D, "home": 0x24, "end": 0x23, "pause": 0x13}


class HotkeyError(Exception):
    pass


def parse_hotkey(text: str) -> tuple[int, int]:
    """'Ctrl+Alt+Space' -> (modifier flags, virtual-key code)."""
    parts = [p.strip().lower() for p in text.split("+") if p.strip()]
    if not parts:
        raise HotkeyError("The hotkey is empty.")
    *mods, key = parts
    flags = 0
    for mod in mods:
        if mod not in _MODIFIERS:
            raise HotkeyError(f"Unknown modifier '{mod}'. Use Ctrl, Alt, Shift or Win.")
        flags |= _MODIFIERS[mod]
    if not flags:
        raise HotkeyError("Use at least one of Ctrl, Alt, Shift or Win, so normal typing isn't affected.")
    if key in _KEYS:
        vk = _KEYS[key]
    elif len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x6F + int(key[1:])  # F1 = 0x70
    else:
        raise HotkeyError(f"Unknown key '{key}'.")
    return flags, vk


class GlobalHotkey(QObject):
    """Emits `pressed` whenever the hotkey is pressed, in any app.

    Windows delivers the hotkey to the thread that registered it, so a small
    background thread registers it and waits for it. Connect `pressed` with a
    queued connection: it is emitted from that thread.
    """

    pressed = Signal()
    failed = Signal(str)

    def __init__(self, hotkey: str = DEFAULT_HOTKEY, *, user32=None, kernel32=None) -> None:
        super().__init__()
        self.hotkey = hotkey
        self.modifiers, self.vk = parse_hotkey(hotkey)
        self._user32 = user32
        self._kernel32 = kernel32
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None
        self._ready = threading.Event()
        self.active = False

    @staticmethod
    def supported() -> bool:
        return sys.platform == "win32"

    def start(self) -> bool:
        """Register the hotkey. Returns False (and emits `failed`) if it can't."""
        if self._user32 is None:
            if not self.supported():
                self.failed.emit("Global hotkeys are only available on Windows.")
                return False
            self._user32 = ctypes.WinDLL("user32", use_last_error=True)
            self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="parker-hotkey", daemon=True)
        self._thread.start()
        self._ready.wait(2)
        return self.active

    def stop(self) -> None:
        if self._thread_id is not None and self._thread is not None and self._thread.is_alive():
            self._user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self._thread.join(2)
        self.active = False

    def _run(self) -> None:
        self._thread_id = self._kernel32.GetCurrentThreadId()
        ok = self._user32.RegisterHotKey(None, HOTKEY_ID, self.modifiers | MOD_NOREPEAT, self.vk)
        if not ok:
            self.active = False
            self._ready.set()
            self.failed.emit(
                f"Couldn't use {self.hotkey}: another app may already be using it. "
                "Choose a different one in PARKER's settings."
            )
            return
        self.active = True
        self._ready.set()
        msg = wintypes.MSG()
        try:
            # GetMessage blocks until a message arrives; it returns 0 on WM_QUIT.
            while self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    self.pressed.emit()
        finally:
            self._user32.UnregisterHotKey(None, HOTKEY_ID)
            self.active = False


def _test(hotkey: str, seconds: int = 20) -> int:
    """Diagnostic: python -m frontend.hotkey [--test "Ctrl+Alt+P"]

    Registers the shortcut on its own (PARKER's window not needed), then counts
    presses for a few seconds, so it is clear whether Windows delivers them.
    """
    from PySide6.QtCore import QCoreApplication, QTimer

    app = QCoreApplication.instance() or QCoreApplication([])
    hk = GlobalHotkey(hotkey)
    count = [0]

    def pressed():
        count[0] += 1
        print(f"  Pressed! ({count[0]})", flush=True)

    hk.pressed.connect(pressed)
    hk.failed.connect(lambda message: print(f"FAILED: {message}", flush=True))
    if not hk.start():
        app.processEvents()
        print(f"Windows refused {hotkey}. Another app is using it. Try another, e.g.:")
        print('  python -m frontend.hotkey --test "Ctrl+Shift+Space"')
        return 1
    print(f"Registered {hotkey}. Press it a few times in any app (testing for {seconds} s)...", flush=True)
    QTimer.singleShot(seconds * 1000, app.quit)
    app.exec()
    hk.stop()
    if count[0]:
        print(f"OK: Windows delivered {count[0]} press(es). The shortcut works.")
        return 0
    print("Registered, but no presses arrived. Another program may be catching the keys first.")
    return 2


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--test":
        args = args[1:]
    sys.exit(_test(args[0] if args else DEFAULT_HOTKEY))
