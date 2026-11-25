"""Tests for the desktop app, run off-screen with a fake brain, voice and microphone."""

import os
import threading
import time
from datetime import date, datetime

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from backend.agenda import Agenda  # noqa: E402
from backend.assistant import Assistant  # noqa: E402
from backend.brain import BrainError  # noqa: E402
from backend.memory import Memory  # noqa: E402
from frontend import theme  # noqa: E402
from frontend.app import MainWindow  # noqa: E402

NOW = datetime(2026, 11, 25, 19, 30)


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setStyleSheet(theme.STYLESHEET)
    return application


class FakeSpeaker:
    def __init__(self):
        self.spoken = []
        self.stopped = 0

    def speak(self, text):
        self.spoken.append(text)

    def stop(self):
        self.stopped += 1


class FakeListener:
    def __init__(self, text="What's the plan?"):
        self.text = text

    def listen(self):
        return self.text


def make_window(app, *, reply="Happy to help, Raunak.", brain=None, listener_text="What's the plan?",
                voice=True, mic=True, agenda=None, memory=None):
    speaker = FakeSpeaker()
    sent = []

    def default_brain(message, history, **kw):
        sent.append(message)
        return reply

    assistant = Assistant(
        generate=brain or default_brain,
        memory=memory if memory is not None else Memory(":memory:"),
        agenda=agenda if agenda is not None else Agenda(":memory:"),
        now=lambda: NOW,
    )
    window = MainWindow(
        assistant,
        make_speaker=(lambda: speaker) if voice else None,
        make_listener=(lambda wait: FakeListener(listener_text)) if mic else None,
        threaded=False,
        now=lambda: NOW,
    )
    return window, speaker, sent


def test_greets_by_name_with_plans_and_todays_events(app):
    agenda = Agenda(":memory:")
    agenda.add_plan("start the desktop app")
    agenda.add_event(date(2026, 11, 25), "21:00", "Review progress")
    window, speaker, _ = make_window(app, agenda=agenda)
    expected = (
        "Good evening, Raunak. Planned for this session: start the desktop app. "
        "Today: Review progress at 21:00. Let's make it a good one."
    )
    assert window.chat.messages[0] == ("parker", expected)
    assert speaker.spoken == [expected]
    assert window.state == "idle"


def test_typed_message_gets_a_spoken_reply(app):
    window, speaker, sent = make_window(app)
    window.entry.setText("How am I doing?")
    window.send_typed()
    assert sent == ["How am I doing?"]
    assert window.chat.messages[-2:] == [("user", "How am I doing?"), ("parker", "Happy to help, Raunak.")]
    assert speaker.spoken[-1] == "Happy to help, Raunak."
    assert window.entry.text() == ""


def test_talk_button_sends_what_was_heard(app):
    window, _, sent = make_window(app, listener_text="What's on tomorrow?")
    window.toggle_listening()
    assert sent == ["What's on tomorrow?"]
    assert ("user", "What's on tomorrow?") in window.chat.messages


def test_nothing_heard_is_reported(app):
    window, _, sent = make_window(app, listener_text="   ")
    window.toggle_listening()
    assert sent == []
    assert window.chat.messages[-1] == ("note", "Sorry, I didn't catch that.")


def test_remember_updates_the_memories_panel_without_the_model(app):
    window, speaker, sent = make_window(app)
    window.process("Remember that my exam is on Friday")
    assert sent == []
    assert window.memories_panel.list.count() == 1
    assert window.memories_panel.list.item(0).text() == "my exam is on Friday"
    assert speaker.spoken[-1] == "Noted. I'll remember that: my exam is on Friday"


def test_memories_panel_add_and_forget(app):
    window, _, _ = make_window(app)
    panel = window.memories_panel
    panel.entry.setText("I prefer tea")
    panel.add()
    assert [f.text for f in window.assistant.memory.all()] == ["I prefer tea"]
    panel.list.item(0).setSelected(True)
    panel.delete_selected()
    assert window.assistant.memory.all() == []


def test_agenda_panel_plans_and_events(app):
    window, _, _ = make_window(app)
    panel = window.agenda_panel
    panel.plan_entry.setText("write the README")
    panel.add_plan()
    assert panel.plans.count() == 1
    panel.event_time.setText("18:00")
    panel.event_text.setText("Gym")
    panel.add_event()
    assert panel.events.item(0).text() == "Gym\ntoday at 18:00"
    panel.plans.item(0).setCheckState(Qt.CheckState.Checked)  # tick = done
    assert window.assistant.agenda.open_plans() == []


def test_bad_event_time_is_explained(app, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a: shown.append(a[2]))
    window, _, _ = make_window(app)
    panel = window.agenda_panel
    panel.event_time.setText("25:99")
    panel.event_text.setText("Party")
    panel.add_event()
    assert window.assistant.agenda.events_on(NOW.date()) == []
    assert shown  # the user is told what went wrong


def test_slash_commands_work_in_the_window(app):
    window, _, sent = make_window(app)
    window.process("/plan test the app")
    window.process("/memory")
    assert window.agenda_panel.plans.count() == 1
    assert window.chat.messages[-1] == ("note", "Unknown command /memory. Type /help for commands.")
    assert sent == []


def test_forget_all_asks_for_confirmation(app, monkeypatch):
    window, _, _ = make_window(app)
    window.process("/remember one thing")
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No)
    window.process("/forget all")
    assert len(window.assistant.memory.all()) == 1
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    window.process("/forget all")
    assert window.assistant.memory.all() == []


def test_model_errors_are_shown_not_spoken(app):
    def broken(message, history, **kw):
        raise BrainError("Cannot reach Ollama")

    window, speaker, _ = make_window(app, brain=broken)
    window.process("Hello")
    assert window.chat.messages[-1] == ("error", "Cannot reach Ollama")
    assert len(speaker.spoken) == 1  # only the greeting
    assert window.state == "idle"


def test_speak_replies_toggle(app):
    window, speaker, _ = make_window(app)
    window.voice_toggle.setChecked(False)
    window.process("Quiet please")
    assert speaker.spoken == [window.chat.messages[0][1]]  # greeting only
    assert speaker.stopped == 1


def test_without_voice_or_microphone(app):
    window, _, _ = make_window(app, voice=False, mic=False)
    assert not window.talk_button.isEnabled()
    assert not window.voice_toggle.isEnabled()
    assert not window.voice_toggle.isChecked()
    window.toggle_listening()  # does nothing, no crash
    assert window.state == "idle"


def test_reset_keeps_memories(app):
    window, _, _ = make_window(app)
    window.process("/remember I like tea")
    window.process("Hello")
    window.process("/reset")
    assert window.assistant.history == []
    assert len(window.assistant.memory.all()) == 1


def test_threaded_listening_stops_when_talk_is_pressed_again(app):
    """The real background thread: recording waits until Talk is clicked again."""

    class WaitingListener:
        def __init__(self, wait):
            self.wait = wait

        def listen(self):
            self.wait("")  # blocks until the window says stop
            return "Hello from the microphone"

    sent = []
    assistant = Assistant(
        generate=lambda m, h, **kw: sent.append(m) or "Hi!",
        memory=Memory(":memory:"),
        agenda=Agenda(":memory:"),
        now=lambda: NOW,
    )
    window = MainWindow(
        assistant,
        make_speaker=FakeSpeaker,
        make_listener=lambda wait: WaitingListener(wait),
        threaded=True,
        now=lambda: NOW,
    )

    def wait_until(condition, seconds=5):
        end = time.monotonic() + seconds
        while time.monotonic() < end and not condition():
            QCoreApplication.processEvents()
            time.sleep(0.01)
        return condition()

    errors = []
    original_add = window.chat.add

    def checked_add(*args, **kwargs):
        # Catch the bug that froze the app: bubbles built on the worker thread.
        try:
            original_add(*args, **kwargs)
        except RuntimeError as err:
            errors.append(str(err))

    window.chat.add = checked_add

    try:
        assert wait_until(lambda: window.mic_ready and window.state == "idle")
        assert wait_until(lambda: window.chat.messages and window.chat.messages[0][0] == "parker")
        window.toggle_listening()
        assert wait_until(lambda: window.state == "listening")
        assert window.talk_button.text() == "Done"
        window.toggle_listening()  # click again: stop recording
        assert wait_until(lambda: sent == ["Hello from the microphone"])
        assert wait_until(lambda: ("parker", "Hi!") in window.chat.messages)
        assert errors == []
    finally:
        window.close()
    assert threading.active_count() >= 1


def test_chat_refuses_widgets_from_a_background_thread(app):
    window, _, _ = make_window(app)
    failures = []

    def from_thread():
        try:
            window.chat.add("parker", "from the wrong thread")
        except RuntimeError as err:
            failures.append(str(err))

    t = threading.Thread(target=from_thread)
    t.start()
    t.join()
    assert failures == ["ChatView.add called from a background thread"]


def test_recording_time_limit_stops_listening_directly(app):
    window, _, _ = make_window(app)
    stopped = []
    window.worker.stop_listening = lambda: stopped.append(True)
    window._recording_limit.timeout.emit()
    assert stopped == [True]
