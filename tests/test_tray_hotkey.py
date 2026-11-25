"""Tests for the system tray, global hotkey and start-with-Windows option.

Windows APIs are replaced with fakes, so these run on any system."""

import ctypes
import os
import threading
import time
from datetime import datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QCoreApplication, QObject, QSettings, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from backend.agenda import Agenda  # noqa: E402
from backend.assistant import Assistant  # noqa: E402
from backend.memory import Memory  # noqa: E402
from frontend import autostart  # noqa: E402
from frontend.app import MainWindow  # noqa: E402
from frontend.hotkey import (  # noqa: E402
    HOTKEY_ID,
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    WM_HOTKEY,
    WM_QUIT,
    GlobalHotkey,
    HotkeyError,
    parse_hotkey,
)

NOW = datetime(2026, 11, 25, 19, 30)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def settings(tmp_path):
    return QSettings(str(tmp_path / "parker.ini"), QSettings.Format.IniFormat)


def process_events(seconds=0.3):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.01)


# ---- hotkey parsing ---------------------------------------------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        ("Ctrl+Alt+Space", (MOD_CONTROL | MOD_ALT, 0x20)),
        ("ctrl + shift + p", (MOD_CONTROL | MOD_SHIFT, ord("P"))),
        ("Alt+F9", (MOD_ALT, 0x78)),
        ("Win+Shift+1", (0x8 | MOD_SHIFT, ord("1"))),
    ],
)
def test_parse_hotkey(text, expected):
    assert parse_hotkey(text) == expected


@pytest.mark.parametrize("bad", ["", "Space", "Ctrl+Banana", "Hyper+Space", "Ctrl+F99"])
def test_bad_hotkeys_are_rejected(bad):
    with pytest.raises(HotkeyError):
        parse_hotkey(bad)


# ---- the hotkey thread, with fake Windows functions -------------------------

class FakeWindows:
    """Pretends to be user32/kernel32: delivers queued messages to GetMessageW."""

    def __init__(self, register_ok=True):
        self.register_ok = register_ok
        self.registered = []
        self.unregistered = 0
        self.inbox = []
        self.has_mail = threading.Condition()

    # kernel32
    def GetCurrentThreadId(self):  # noqa: N802
        return 42

    # user32
    def RegisterHotKey(self, hwnd, ident, mods, vk):  # noqa: N802
        self.registered.append((ident, mods, vk))
        return 1 if self.register_ok else 0

    def UnregisterHotKey(self, hwnd, ident):  # noqa: N802
        self.unregistered += 1
        return 1

    def post(self, message, wparam=0):
        with self.has_mail:
            self.inbox.append((message, wparam))
            self.has_mail.notify()

    def PostThreadMessageW(self, thread_id, message, wparam, lparam):  # noqa: N802
        self.post(message, wparam)
        return 1

    def GetMessageW(self, msg_ref, hwnd, lo, hi):  # noqa: N802
        with self.has_mail:
            while not self.inbox:
                self.has_mail.wait()
            message, wparam = self.inbox.pop(0)
        msg = msg_ref._obj
        msg.message = message
        msg.wParam = wparam
        return 0 if message == WM_QUIT else 1


class Counter(QObject):
    pass


def test_hotkey_registers_without_repeat_and_reports_presses(app):
    fake = FakeWindows()
    hotkey = GlobalHotkey("Ctrl+Alt+Space", user32=fake, kernel32=fake)
    presses = []
    hotkey.pressed.connect(lambda: presses.append(1))
    assert hotkey.start()
    assert fake.registered == [(HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x20)]
    fake.post(WM_HOTKEY, HOTKEY_ID)
    fake.post(WM_HOTKEY, 999)  # someone else's hotkey: ignored
    fake.post(WM_HOTKEY, HOTKEY_ID)
    process_events()  # presses arrive through Qt's event queue, on this thread
    hotkey.stop()
    assert len(presses) == 2
    assert fake.unregistered == 1
    assert not hotkey.active


def test_hotkey_in_use_by_another_app_is_reported(app):
    fake = FakeWindows(register_ok=False)
    hotkey = GlobalHotkey("Ctrl+Alt+Space", user32=fake, kernel32=fake)
    messages = []
    hotkey.failed.connect(messages.append)
    assert not hotkey.start()
    process_events()
    assert "another app may already be using it" in messages[0]


# ---- start with Windows (fake registry) -------------------------------------

class FakeRegistry:
    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1
    KEY_SET_VALUE = 2

    def __init__(self):
        self.values = {}

    class _Key:
        def __init__(self, reg):
            self.reg = reg

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, root, path, *args):  # noqa: N802
        return self._Key(self)

    def CreateKey(self, root, path):  # noqa: N802
        return self._Key(self)

    def QueryValueEx(self, key, name):  # noqa: N802
        if name not in self.values:
            raise FileNotFoundError
        return self.values[name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):  # noqa: N802
        self.values[name] = value

    def DeleteValue(self, key, name):  # noqa: N802
        if name not in self.values:
            raise FileNotFoundError
        del self.values[name]


def test_autostart_enable_and_disable():
    reg = FakeRegistry()
    assert not autostart.is_enabled(reg)
    autostart.enable(reg, command='"pythonw.exe" "parker.pyw" --background')
    assert autostart.is_enabled(reg)
    assert reg.values["PARKER"].endswith("--background")
    autostart.disable(reg)
    assert not autostart.is_enabled(reg)
    autostart.disable(reg)  # disabling twice is fine


def test_launch_command_uses_the_launcher_in_background_mode():
    command = autostart.launch_command("/venv/Scripts/python.exe")
    assert command.endswith('parker.pyw" --background')


# ---- the window with a tray and hotkey --------------------------------------

class FakeHotkey(QObject):
    pressed = Signal()
    failed = Signal(str)
    taken: set = set()  # shortcuts "another app" already uses

    def __init__(self, text):
        super().__init__()
        self.text = text
        self.started = self.stopped = 0
        self.active = False

    def start(self):
        self.started += 1
        if self.text in FakeHotkey.taken:
            self.failed.emit(f"Couldn't use {self.text}: another app may already be using it.")
            return False
        self.active = True
        return True

    def stop(self):
        self.stopped += 1


class FakeListener:
    def listen(self):
        return "From another app"


class FakeSpeaker:
    def speak(self, text):
        pass

    def stop(self):
        pass


def make_window(app, tmp_path, start_hidden=False):
    hotkeys = []

    def make_hotkey(text):
        hk = FakeHotkey(text)
        hotkeys.append(hk)
        return hk

    sent = []
    window = MainWindow(
        Assistant(generate=lambda m, h, **k: sent.append(m) or "Done.", memory=Memory(":memory:"),
                  agenda=Agenda(":memory:"), now=lambda: NOW),
        make_speaker=FakeSpeaker,
        make_listener=lambda wait: FakeListener(),
        threaded=False,
        now=lambda: NOW,
        tray_available=lambda: True,
        make_hotkey=make_hotkey,
        settings=settings(tmp_path),
        start_hidden=start_hidden,
    )
    return window, hotkeys, sent


def test_closing_the_window_hides_it_to_the_tray(app, tmp_path):
    window, hotkeys, _ = make_window(app, tmp_path)
    window.show()
    window.close()
    assert window.isHidden()
    assert hotkeys[0].stopped == 0  # still listening for the hotkey
    window.quit_app()
    assert hotkeys[0].stopped == 1


def test_hotkey_press_starts_listening_even_when_hidden(app, tmp_path):
    window, hotkeys, sent = make_window(app, tmp_path)
    window.hide()
    hotkeys[0].pressed.emit()
    process_events()
    assert sent == ["From another app"]
    assert window.isHidden()  # answered without popping the window up
    window.quit_app()


def test_tray_icon_follows_the_state(app, tmp_path):
    window, _, _ = make_window(app, tmp_path)
    window.set_state("listening")
    assert window.tray.toolTip() == "PARKER · Listening"
    window.quit_app()


def test_default_hotkey_is_ctrl_alt_p_and_can_be_changed(app, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.delenv("PARKER_HOTKEY", raising=False)
    window, hotkeys, _ = make_window(app, tmp_path)
    assert hotkeys[0].text == "Ctrl+Alt+P"
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Ctrl+Shift+P", True))
    window.change_hotkey()
    assert hotkeys[0].stopped == 1 and hotkeys[1].text == "Ctrl+Shift+P"
    assert window.settings.value("hotkey") == "Ctrl+Shift+P"
    window.quit_app()
    # The choice is remembered next time.
    window2, hotkeys2, _ = make_window(app, tmp_path)
    assert hotkeys2[0].text == "Ctrl+Shift+P"
    window2.quit_app()


def test_starting_in_the_background_does_not_speak_the_greeting(app, tmp_path):
    spoken = []

    class Recorder(FakeSpeaker):
        def speak(self, text):
            spoken.append(text)

    window = MainWindow(
        Assistant(generate=lambda m, h, **k: "ok", memory=Memory(":memory:"), agenda=Agenda(":memory:"),
                  now=lambda: NOW),
        make_speaker=Recorder, make_listener=lambda wait: FakeListener(), threaded=False,
        now=lambda: NOW, tray_available=lambda: True, make_hotkey=FakeHotkey,
        settings=settings(tmp_path), start_hidden=True,
    )
    assert window.chat.messages[0][0] == "parker"  # greeting is still in the chat
    assert spoken == []
    window.quit_app()



def test_taken_default_falls_back_to_a_free_shortcut_and_says_so(app, tmp_path, monkeypatch):
    monkeypatch.delenv("PARKER_HOTKEY", raising=False)
    monkeypatch.setattr(FakeHotkey, "taken", {"Ctrl+Alt+P"})
    window, hotkeys, _ = make_window(app, tmp_path)
    assert [h.text for h in hotkeys] == ["Ctrl+Alt+P", "Ctrl+Shift+Space"]
    assert window.hotkey_text == "Ctrl+Shift+Space"
    process_events(0.1)
    assert any("the talk shortcut is Ctrl+Shift+Space" in text for _, text in window.chat.messages)
    assert not any(kind == "error" for kind, _ in window.chat.messages)  # fallback is not an error
    window.quit_app()


def test_a_chosen_shortcut_that_is_taken_is_reported_loudly(app, tmp_path, monkeypatch):
    monkeypatch.setenv("PARKER_HOTKEY", "Ctrl+Alt+Space")
    monkeypatch.setattr(FakeHotkey, "taken", {"Ctrl+Alt+Space"})
    window, hotkeys, _ = make_window(app, tmp_path)
    process_events(0.1)
    assert [h.text for h in hotkeys] == ["Ctrl+Alt+Space"]  # no silent switching
    assert ("error", "Couldn't use Ctrl+Alt+Space: another app may already be using it.") in window.chat.messages
    window.quit_app()


def test_hotkey_diagnostic_reports_a_refused_shortcut(monkeypatch, capsys):
    import frontend.hotkey as hk

    class Refused(hk.GlobalHotkey):
        def start(self):
            self.failed.emit("taken")
            return False

    monkeypatch.setattr(hk, "GlobalHotkey", Refused)
    QCoreApplication.instance() or QCoreApplication([])
    assert hk._test("Ctrl+Alt+Space", seconds=0) == 1
    assert "Windows refused Ctrl+Alt+Space" in capsys.readouterr().out
