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


def temp_settings():
    """Settings stored in a throwaway file, never the real user settings."""
    import tempfile

    from PySide6.QtCore import QSettings

    path = os.path.join(tempfile.mkdtemp(), "parker.ini")
    return QSettings(path, QSettings.Format.IniFormat)


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
        tray_available=lambda: False,
        make_hotkey=None,
        settings=temp_settings(),
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
        tray_available=lambda: False,
        make_hotkey=None,
        settings=temp_settings(),
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
        assert window.talk_button.property("mode") == "listening"
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



# ---- premium layout: drawer and the one mic button ---------------------------

def test_drawer_is_closed_until_asked_and_toggles(app):
    window, _, _ = make_window(app)
    assert not window.drawer.is_open
    window.toggle_drawer("Agenda")
    assert window.drawer.current == "Agenda" and window.agenda_button.isChecked()
    window.toggle_drawer("Memories")
    assert window.drawer.current == "Memories" and not window.agenda_button.isChecked()
    window.toggle_drawer("Memories")  # same button again closes it
    assert not window.drawer.is_open and not window.memories_button.isChecked()


def test_escape_closes_the_drawer(app):
    window, _, _ = make_window(app)
    window.toggle_drawer("Agenda")
    window.escape()
    assert not window.drawer.is_open


def test_mic_button_changes_with_state(app):
    window, _, _ = make_window(app)
    assert window.talk_button.property("mode") == "talk"
    window.set_state("speaking")
    assert window.talk_button.property("mode") == "speaking"
    assert window.talk_button.isEnabled()


def test_mic_button_stops_speech_while_speaking(app):
    window, speaker, sent = make_window(app)
    window.set_state("speaking")
    window.mic_clicked()
    assert speaker.stopped == 1
    assert sent == []  # it did not start listening


def test_spoken_messages_are_marked_quietly(app):
    window, _, _ = make_window(app, listener_text="Hello there")
    window.toggle_listening()
    assert ("user", "Hello there") in window.chat.messages


def test_settings_menu_has_voice_toggle_and_clear(app):
    window, _, _ = make_window(app)
    labels = [a.text() for a in window.settings_button.menu().actions()]
    assert "Speak replies" in labels and "Clear conversation" in labels
    window.process("Hello")
    next(a for a in window.settings_button.menu().actions() if a.text() == "Clear conversation").trigger()
    assert window.assistant.history == []


# ---- hands-free conversation ------------------------------------------------

class HandsFreeListener:
    """Hears each scripted phrase in turn; '' means nobody spoke."""

    def __init__(self, phrases):
        self.phrases = list(phrases)
        self.waits = []

    def listen(self):
        raise AssertionError("hands-free mode should not use push-to-talk")

    def listen_until_silence(self, should_stop, wait_seconds):
        self.waits.append(wait_seconds)
        return self.phrases.pop(0) if self.phrases else ""


def hands_free_window(app, phrases, *, hands_free=True, voice=True):
    speaker = FakeSpeaker()
    listener = HandsFreeListener(phrases)
    sent = []
    assistant = Assistant(
        generate=lambda m, h, **kw: sent.append(m) or f"Reply to {m}",
        memory=Memory(":memory:"), agenda=Agenda(":memory:"), now=lambda: NOW,
    )
    settings = temp_settings()
    settings.setValue("hands_free", "true" if hands_free else "false")
    window = MainWindow(
        assistant, make_speaker=(lambda: speaker) if voice else None,
        make_listener=lambda wait: listener, threaded=False, now=lambda: NOW,
        tray_available=lambda: False, make_hotkey=None, settings=settings,
    )
    return window, listener, speaker, sent


def settle(window, ms=1500):
    """Let queued follow-up timers run (the app waits briefly before listening again)."""
    from PySide6.QtTest import QTest

    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        QTest.qWait(20)


def test_hands_free_keeps_listening_after_each_reply_until_silence(app):
    window, listener, speaker, sent = hands_free_window(app, ["What's the plan?", "And after that?"])
    assert window.hands_free and window.hands_free_action.isChecked()
    window.toggle_listening()  # one press starts the conversation
    settle(window)
    assert sent == ["What's the plan?", "And after that?"]
    assert speaker.spoken[-2:] == ["Reply to What's the plan?", "Reply to And after that?"]
    # The third recording heard nothing: the conversation ends quietly.
    assert len(listener.waits) == 3
    assert window.conversation is False and window.state == "idle"
    assert ("note", "Sorry, I didn't catch that.") not in window.chat.messages


def test_saying_thats_all_ends_with_a_short_farewell(app):
    window, listener, speaker, sent = hands_free_window(app, ["Tell me a joke", "Thanks, that's all."])
    window.toggle_listening()
    settle(window)
    assert sent == ["Tell me a joke"]  # the sign-off never reaches the model
    assert speaker.spoken[-1] == "Anytime, Raunak."
    assert len(listener.waits) == 2 and window.conversation is False


def test_silence_on_the_first_press_still_says_so(app):
    window, listener, _, _ = hands_free_window(app, [""])
    window.toggle_listening()
    settle(window, 600)
    assert window.chat.messages[-1] == ("note", "Sorry, I didn't catch that.")
    assert len(listener.waits) == 1


def test_escape_ends_the_conversation(app):
    window, listener, _, sent = hands_free_window(app, ["What's the plan?", "Next thing"])
    window.toggle_listening()
    window.escape()  # e.g. while PARKER replies
    settle(window, 800)
    assert sent == ["What's the plan?"] and len(listener.waits) == 1


def test_typing_ends_the_conversation(app):
    window, listener, _, sent = hands_free_window(app, ["Hello"], voice=False)
    window.toggle_listening()
    window.entry.setText("typed instead")
    window.send_typed()
    settle(window, 800)
    assert sent == ["Hello", "typed instead"] and len(listener.waits) == 1


def test_hands_free_can_be_switched_off_and_is_remembered(app):
    window, listener, _, _ = hands_free_window(app, [], hands_free=False)
    assert window.hands_free is False
    listener.listen = lambda: "push to talk"
    window.toggle_listening()
    settle(window, 600)
    assert listener.waits == [] and window.conversation is False
    window.hands_free_action.setChecked(True)
    assert window.settings.value("hands_free") == "true"


def test_old_microphones_without_silence_detection_use_push_to_talk(app):
    window, _, _ = make_window(app)  # FakeListener has only listen()
    assert window.hands_free_action.isChecked() and window.hands_free is False
    window.toggle_listening()
    settle(window, 600)
    assert window.conversation is False


def test_threaded_hands_free_conversation(app):
    """The real worker thread: listen, reply, listen again, end on silence."""
    listener = HandsFreeListener(["First question", "Second question"])
    sent = []
    assistant = Assistant(
        generate=lambda m, h, **kw: sent.append(m) or "Sure.",
        memory=Memory(":memory:"), agenda=Agenda(":memory:"), now=lambda: NOW,
    )
    window = MainWindow(
        assistant, make_speaker=FakeSpeaker, make_listener=lambda wait: listener,
        threaded=True, now=lambda: NOW, tray_available=lambda: False, make_hotkey=None,
        settings=temp_settings(),
    )
    errors = []
    original_add = window.chat.add

    def checked_add(*args, **kwargs):
        try:
            original_add(*args, **kwargs)
        except RuntimeError as err:  # a bubble built on the worker thread
            errors.append(str(err))

    window.chat.add = checked_add
    try:
        end = time.monotonic() + 5
        while time.monotonic() < end and not (window.mic_ready and window.state == "idle"):
            settle(window, 20)
        window.toggle_listening()
        end = time.monotonic() + 8
        while time.monotonic() < end and not (len(listener.waits) == 3 and not window.conversation):
            settle(window, 50)
        assert sent == ["First question", "Second question"]
        assert len(listener.waits) == 3 and window.conversation is False
        assert errors == []
    finally:
        window._quitting = True
        window.close()


# ---- wake word ("Hey Parker") ---------------------------------------------------

class FakeWakeDetector:
    def __init__(self, on_wake, on_error, on_ready):
        self.on_wake, self.on_error, self.on_ready = on_wake, on_error, on_ready
        self.ready = True
        self.running = False
        self.paused = True
        self.stopped = False

    def start(self):
        self.running = True

    def stop(self):
        self.running, self.stopped = False, True

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False


def wake_window(app, phrases, *, enabled=True):
    speaker = FakeSpeaker()
    listener = HandsFreeListener(phrases)
    sent, detectors = [], []
    assistant = Assistant(
        generate=lambda m, h, **kw: sent.append(m) or f"Reply to {m}",
        memory=Memory(":memory:"), agenda=Agenda(":memory:"), now=lambda: NOW,
    )
    settings = temp_settings()
    settings.setValue("wake_word", "true" if enabled else "false")

    def make_detector(on_wake, on_error, on_ready):
        detectors.append(FakeWakeDetector(on_wake, on_error, on_ready))
        return detectors[-1]

    window = MainWindow(
        assistant, make_speaker=lambda: speaker, make_listener=lambda wait: listener,
        threaded=False, now=lambda: NOW, tray_available=lambda: False, make_hotkey=None,
        settings=settings, make_wake_detector=make_detector,
    )
    return window, listener, speaker, sent, detectors


def test_wake_word_is_off_by_default_and_hidden_without_a_detector(app):
    window, _, _ = make_window(app)
    assert not window.wake_action.isVisible() and not window.wake_action.isChecked()
    window, _, _, _, detectors = wake_window(app, [], enabled=False)
    assert detectors == [] and not window.wake_action.isChecked()


def test_waits_for_the_name_only_when_idle(app):
    window, _, _, _, detectors = wake_window(app, [])
    settle(window, 600)  # the greeting is spoken first
    assert len(detectors) == 1 and detectors[0].running
    assert window.wake_listening and "HEY PARKER" in window.status_label.text()
    window.set_state("speaking")
    assert detectors[0].paused  # never listens to PARKER's own voice
    window.set_state("idle")
    assert not detectors[0].paused


def test_hey_parker_answers_then_listens_hands_free(app):
    window, listener, speaker, sent, detectors = wake_window(app, ["What's on today?"])
    settle(window, 600)
    detectors[0].paused = True  # the detector pauses itself when it hears the name
    window._woke("")
    assert speaker.spoken[-1] == "Yes, Raunak?"
    settle(window)
    assert sent == ["What's on today?"]
    # After the reply it listened once more, heard nothing, and went back to waiting.
    assert len(listener.waits) == 2 and window.conversation is False
    assert not detectors[0].paused


def test_request_in_the_same_breath_goes_straight_through(app):
    window, listener, speaker, sent, detectors = wake_window(app, [])
    settle(window, 600)
    window._woke("what's on today?")
    assert sent == ["what's on today?"]
    assert ("user", "what's on today?") in [m[:2] for m in window.chat.messages]
    settle(window)
    assert len(listener.waits) == 1 and not detectors[0].paused


def test_name_heard_while_busy_is_ignored(app):
    window, listener, speaker, sent, detectors = wake_window(app, [])
    settle(window, 600)
    window.set_state("thinking")
    window._woke("tell me a joke")
    assert sent == []


def test_switching_off_stops_listening_for_the_name(app):
    window, _, _, _, detectors = wake_window(app, [])
    settle(window, 600)
    window.wake_action.setChecked(False)
    assert detectors[0].stopped and window.wake_detector is None
    assert window.settings.value("wake_word") == "false"
    assert "HEY PARKER" not in window.status_label.text()


def test_wake_word_problem_is_shown_and_switches_it_off(app):
    window, _, _, _, detectors = wake_window(app, [])
    settle(window, 600)
    window._wake_failed("Wake word unavailable: no model")
    assert window.chat.messages[-1] == ("error", "Wake word unavailable: no model")
    assert not window.wake_action.isChecked() and detectors[0].stopped


def test_wake_word_says_when_it_is_ready(app):
    window, _, _, _, detectors = wake_window(app, [])
    settle(window, 600)
    detectors[0].ready = False  # still loading the model
    window.set_state("idle")
    assert "HEY PARKER" not in window.status_label.text()
    assert any("Getting the wake word ready" in m[1] for m in window.chat.messages)
    detectors[0].ready = True
    window._wake_ready()
    assert "HEY PARKER" in window.status_label.text()
    assert window.chat.messages[-1][1].startswith("Listening for “Hey Parker”")
