"""Tests for reminders: understanding requests, storing them and firing on time."""

import os
from datetime import datetime, timedelta

import pytest

from backend.assistant import Assistant
from backend.main import announce_due_reminders, handle_reminders, run
from backend.reminders import Reminder, ReminderError, Reminders, announcement, parse_reminder

NOW = datetime(2026, 11, 25, 14, 0)  # a Wednesday afternoon


def at(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute)


# ---- understanding requests -------------------------------------------------

@pytest.mark.parametrize(
    "message, due, task",
    [
        ("Remind me in 20 minutes to stretch", at(25, 14, 20), "stretch"),
        ("remind me to stretch in 20 minutes.", at(25, 14, 20), "stretch"),
        ("Remind me in an hour to drink water", at(25, 15), "drink water"),
        ("remind me in half an hour to check the oven", at(25, 14, 30), "check the oven"),
        ("Remind me in twenty minutes to call Rahul", at(25, 14, 20), "call Rahul"),
        ("remind me in 1.5 hours to stop gaming", at(25, 15, 30), "stop gaming"),
        ("remind me in 2 hours and a half to leave", at(25, 16, 30), "leave"),
        ("remind me at 6 pm to call Mum", at(25, 18), "call Mum"),
        ("Remind me at 18:30 to go to the gym", at(25, 18, 30), "go to the gym"),
        ("remind me at 3 to take a break", at(25, 15), "take a break"),  # 14:00 now, so 3 pm
        ("remind me at 11 am to email the professor", at(26, 11), "email the professor"),
        ("Remind me tomorrow at 9 to submit the assignment", at(26, 9), "submit the assignment"),
        ("remind me tomorrow to buy milk", at(26, 9), "buy milk"),
        ("Remind me tonight at 8 to review notes", at(25, 20), "review notes"),
        ("remind me on Friday at 10 am about the hackathon", at(27, 10), "the hackathon"),
        ("Can you remind me in 5 minutes to check the chai?", at(25, 14, 5), "check the chai"),
        ("Hey Parker, set a reminder for 7pm to call Dad", at(25, 19), "call Dad"),
        ("Remind me at noon tomorrow to eat lunch", at(26, 12), "eat lunch"),
    ],
)
def test_reminder_requests(message, due, task):
    assert parse_reminder(message, NOW) == (due, task)


@pytest.mark.parametrize(
    "message",
    [
        "Did you remind me?",
        "Remind me what my favourite colour is",
        "remind me about my plans for today",
        "What is a reminder?",
        "I keep forgetting things",
    ],
)
def test_not_reminder_requests(message):
    assert parse_reminder(message, NOW) is None


@pytest.mark.parametrize(
    "message, problem",
    [
        ("remind me to stretch", "When should I remind you"),
        ("remind me in 10 minutes", "What should I remind you about"),
        ("remind me at 25 to sleep", "valid time"),
        ("remind me today at 9 am to wake up", "already passed"),
    ],
)
def test_incomplete_requests_are_explained(message, problem):
    with pytest.raises(ReminderError, match=problem):
        parse_reminder(message, NOW)


# ---- storage and firing -----------------------------------------------------

def test_reminders_fire_once_when_due(tmp_path):
    store = Reminders(tmp_path / "parker.db")
    store.add(at(25, 14, 20), "stretch")
    store.add(at(25, 18), "call Mum")
    assert store.due(at(25, 14, 19)) == []
    fired = store.due(at(25, 14, 20))
    assert [r.text for r in fired] == ["stretch"]
    assert store.due(at(25, 14, 21)) == []  # never twice
    assert [r.text for r in store.upcoming()] == ["call Mum"]
    store.close()


def test_reminders_survive_a_restart(tmp_path):
    first = Reminders(tmp_path / "parker.db")
    first.add(at(25, 18), "call Mum")
    first.close()
    second = Reminders(tmp_path / "parker.db")
    assert [r.text for r in second.upcoming()] == ["call Mum"]
    second.close()


def test_cancel(tmp_path):
    store = Reminders(tmp_path / "parker.db")
    r = store.add(at(25, 18), "call Mum")
    assert store.cancel(r.id)
    assert not store.cancel(r.id)
    assert store.upcoming() == []
    store.close()


def test_announcements_mention_missed_reminders():
    on_time = Reminder(1, at(25, 14, 20), "stretch")
    assert announcement(on_time, at(25, 14, 20)) == "Reminder: stretch."
    missed = Reminder(2, at(25, 9), "take vitamins")
    assert announcement(missed, at(25, 14)) == "You missed a reminder from 09:00: take vitamins."


def test_when_wording():
    r = Reminder(1, at(26, 9), "x")
    assert r.when(NOW) == "tomorrow at 09:00"
    assert Reminder(1, at(27, 10), "x").when(NOW) == "on Fri 27 Nov at 10:00"


# ---- chat handler and terminal ----------------------------------------------

def test_handler_sets_and_confirms(tmp_path):
    store = Reminders(":memory:")
    said, printed = [], []
    assert handle_reminders("remind me in 20 minutes to stretch", store, said.append, printed.append, NOW)
    assert said == ["Done. I'll remind you at 14:20: stretch."]
    assert handle_reminders("remind me to stretch", store, said.append, printed.append, NOW)
    assert "When should I remind you" in printed[0]
    assert not handle_reminders("remind me what my name is", store, said.append, printed.append, NOW)


def test_reminder_commands():
    store = Reminders(":memory:")
    store.add(at(25, 18), "call Mum")
    said, printed = [], []
    handle_reminders("/reminders", store, said.append, printed.append, NOW)
    assert printed[-1] == "PARKER: Upcoming reminders:\n  [1] at 18:00: call Mum\n"
    handle_reminders("/reminder cancel 1", store, said.append, printed.append, NOW)
    assert said == ["Reminder cancelled."]
    handle_reminders("/reminders", store, said.append, printed.append, NOW)
    assert "No reminders set" in printed[-1]


def test_terminal_announces_due_reminders_between_messages():
    store = Reminders(":memory:")
    clock = [NOW]
    out, sent = [], []
    inputs = iter(["remind me in 1 minute to stretch", "hello", "/quit"])

    def next_input(_prompt):
        line = next(inputs)
        clock[0] += timedelta(minutes=1)
        return line

    run(
        Assistant(generate=lambda m, h, **k: sent.append(m) or "hi", now=lambda: clock[0]),
        input_fn=next_input,
        print_fn=lambda *a: out.append(" ".join(map(str, a))),
        now=lambda: clock[0],
        reminders=store,
    )
    assert "PARKER: Reminder: stretch.\n" in out
    assert sent == ["hello"]


def test_announce_due_reminders_without_store():
    assert announce_due_reminders(None, print, NOW) == 0


def test_model_is_told_it_cannot_set_reminders():
    from backend import brain

    assert "you cannot set reminders yourself" in brain.SYSTEM_PROMPT


# ---- desktop app --------------------------------------------------------------

def test_desktop_app_announces_reminders_even_when_hidden(tmp_path):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from backend.agenda import Agenda
    from backend.memory import Memory
    from frontend.app import MainWindow

    QApplication.instance() or QApplication([])
    spoken = []

    class Speaker:
        def speak(self, text):
            spoken.append(text)

        def stop(self):
            pass

    clock = [NOW]
    store = Reminders(":memory:")
    window = MainWindow(
        Assistant(generate=lambda m, h, **k: "ok", memory=Memory(":memory:"), agenda=Agenda(":memory:"),
                  now=lambda: clock[0]),
        make_speaker=Speaker, make_listener=None, threaded=False, now=lambda: clock[0],
        tray_available=lambda: False, make_hotkey=None,
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat),
        reminders=store,
    )
    window.process("Remind me in 20 minutes to stretch")
    assert window.agenda_panel.reminder_list.item(0).text() == "stretch\nat 14:20"
    window.hide()
    clock[0] = at(25, 14, 20)
    window.check_reminders()
    assert spoken[-1] == "Reminder: stretch."
    assert ("parker", "Reminder: stretch.") in window.chat.messages
    window.check_reminders()
    assert spoken.count("Reminder: stretch.") == 1
