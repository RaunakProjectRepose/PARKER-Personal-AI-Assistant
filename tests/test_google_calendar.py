"""Tests for Google Calendar, using a fake Google service (no network, no account)."""

import os
import subprocess
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.agenda import Agenda
from backend.assistant import Assistant
from backend.google_calendar import (
    CalendarError,
    CalendarEvent,
    GoogleCalendar,
    _parse_event,
    build_service,
    parse_event_request,
)
from backend.main import events_today, handle_calendar

NOW = datetime(2026, 11, 26, 14, 0)  # Thursday afternoon


def local_iso(dt: datetime) -> str:
    return dt.astimezone().isoformat()


class FakeRequest:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def execute(self):
        if self.error:
            raise self.error
        return self.result


class FakeEvents:
    def __init__(self, items, error=None):
        self.items, self.error = items, error
        self.list_calls, self.inserted = [], []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return FakeRequest({"items": self.items}, self.error)

    def insert(self, calendarId, body):  # noqa: N803 (Google's name)
        self.inserted.append((calendarId, body))
        return FakeRequest({**body, "id": "new"}, self.error)


class FakeService:
    def __init__(self, items=(), error=None):
        self._events = FakeEvents(list(items), error)

    def events(self):
        return self._events


def google_items():
    return [
        {"summary": "AIML303 lecture", "start": {"dateTime": local_iso(datetime(2026, 11, 26, 16))},
         "end": {"dateTime": local_iso(datetime(2026, 11, 26, 17))}},
        {"summary": "Holiday", "start": {"date": "2026-11-26"}, "end": {"date": "2026-11-27"}},
        {"summary": "Hackathon", "start": {"dateTime": local_iso(datetime(2026, 11, 28, 9))},
         "end": {"dateTime": local_iso(datetime(2026, 11, 28, 18))}},
        {"start": {"dateTime": local_iso(datetime(2026, 11, 27, 8))}, "end": {"dateTime": local_iso(datetime(2026, 11, 27, 9))}},
    ]


@pytest.fixture
def calendar():
    service = FakeService(google_items())
    cal = GoogleCalendar(service, clock=lambda: NOW)
    cal.refresh()
    cal.fake = service
    return cal


# ---- understanding requests -------------------------------------------------

@pytest.mark.parametrize(
    "message, described",
    [
        ("Add a meeting with Rahul to my calendar tomorrow at 3", '"Meeting with Rahul", Fri 27 Nov 15:00–16:00'),
        ("Schedule gym on Friday at 7 am for an hour", '"Gym", Fri 27 Nov 07:00–08:00'),
        ("add Mum's birthday to my calendar on Sunday", '"Mum\'s birthday", Sun 29 Nov (all day)'),
        ("Schedule a call with the team tomorrow at 10:30 for 30 minutes", '"Call with the team", Fri 27 Nov 10:30–11:00'),
        ("can you add project review to my google calendar on Monday at 4 pm for 2 hours", '"Project review", Mon 30 Nov 16:00–18:00'),
        ("schedule dinner tonight at 8", '"Dinner", Thu 26 Nov 20:00–21:00'),
        ("add lunch with Priya to my calendar at noon tomorrow", '"Lunch with Priya", Fri 27 Nov 12:00–13:00'),
        ("add an event called Hackathon kickoff to my calendar on Saturday at 9 am", '"Hackathon kickoff", Sat 28 Nov 09:00–10:00'),
        ("put the AIML303 exam in my calendar on the 3rd", '"AIML303 exam", Thu 3 Dec (all day)'),
        ("add AIML303 exam to my calendar on 3 December at 10 am", '"AIML303 exam", Thu 3 Dec 10:00–11:00'),
        ("add submission deadline to my calendar on December 1st", '"Submission deadline", Tue 1 Dec (all day)'),
        ("add holiday to my calendar on 2/1", '"Holiday", Sat 2 Jan (all day)'),
    ],
)
def test_event_requests(message, described):
    assert parse_event_request(message, NOW).describe() == described


@pytest.mark.parametrize("message", ["add milk to my shopping list", "what is on my calendar tomorrow", "open my calendar"])
def test_not_event_requests(message):
    assert parse_event_request(message, NOW) is None


@pytest.mark.parametrize(
    "message, problem",
    [
        ("Add a meeting to my calendar", "When is it"),
        ("schedule something", "When is it"),
        ("add review to my calendar on the 31st of February", "real date"),
        ("add standup to my calendar today at 9 am", "already passed"),
    ],
)
def test_incomplete_event_requests(message, problem):
    with pytest.raises(CalendarError, match=problem):
        parse_event_request(message, NOW)


# ---- reading from Google ----------------------------------------------------

def test_google_times_become_local_times():
    utc = {"summary": "x", "start": {"dateTime": "2026-11-26T10:30:00Z"}, "end": {"dateTime": "2026-11-26T11:30:00Z"}}
    event = _parse_event(utc)
    expected = datetime(2026, 11, 26, 10, 30, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    assert event.start == expected and not event.all_day


def test_refresh_asks_for_this_week_in_order(calendar):
    call = calendar.fake.events().list_calls[0]
    assert call["calendarId"] == "primary" and call["singleEvents"] and call["orderBy"] == "startTime"
    start = datetime.fromisoformat(call["timeMin"]).replace(tzinfo=None)
    end = datetime.fromisoformat(call["timeMax"]).replace(tzinfo=None)
    assert start == datetime(2026, 11, 26) and end - start == timedelta(days=8)


def test_cached_events_by_day(calendar):
    today = [e.title for e in calendar.cached(date(2026, 11, 26), date(2026, 11, 26))]
    assert today == ["AIML303 lecture", "Holiday"]
    assert [e.title for e in calendar.cached(date(2026, 11, 27), date(2026, 11, 27))] == ["(no title)"]


def test_refresh_if_stale_uses_the_cache(calendar):
    calendar.refresh_if_stale()
    assert len(calendar.fake.events().list_calls) == 1  # fresh: no new request
    calendar.refresh_if_stale(max_age=0)
    assert len(calendar.fake.events().list_calls) == 2


def test_google_errors_become_readable(calendar):
    broken = GoogleCalendar(FakeService(error=OSError("no internet")), clock=lambda: NOW)
    with pytest.raises(CalendarError, match="Couldn't read Google Calendar: no internet"):
        broken.refresh()


def test_not_connected_never_opens_a_browser(tmp_path):
    pytest.importorskip("google_auth_oauthlib")
    with pytest.raises(CalendarError, match="isn't connected yet"):
        build_service(tmp_path / "credentials.json", tmp_path / "token.json", interactive=False)


# ---- adding to Google -------------------------------------------------------

def test_add_timed_and_all_day_events(calendar):
    calendar.add("Gym", datetime(2026, 11, 27, 7), datetime(2026, 11, 27, 8), False)
    calendar.add("Exam", datetime(2026, 12, 3), datetime(2026, 12, 4), True)
    (cal_id, timed), (_, all_day) = calendar.fake.events().inserted
    assert cal_id == "primary" and timed["summary"] == "Gym"
    assert datetime.fromisoformat(timed["start"]["dateTime"]).replace(tzinfo=None) == datetime(2026, 11, 27, 7)
    assert all_day["start"] == {"date": "2026-12-03"} and all_day["end"] == {"date": "2026-12-04"}
    assert "Gym" in [e.title for e in calendar.cached(date(2026, 11, 27), date(2026, 11, 27))]


def test_handler_asks_before_adding(calendar):
    said, printed, asked = [], [], []

    def no(question):
        asked.append(question)
        return "no"

    assert handle_calendar("Add a meeting with Rahul to my calendar tomorrow at 3", calendar,
                           said.append, printed.append, no, NOW)
    assert asked == ['Add "Meeting with Rahul", Fri 27 Nov 15:00–16:00 to Google Calendar? Type yes: ']
    assert calendar.fake.events().inserted == []
    assert printed[-1] == "PARKER: Okay, I haven't added it.\n"

    handle_calendar("Add a meeting with Rahul to my calendar tomorrow at 3", calendar,
                    said.append, printed.append, lambda q: "yes", NOW)
    assert len(calendar.fake.events().inserted) == 1
    assert said == ['Added to your calendar: "Meeting with Rahul", Fri 27 Nov 15:00–16:00.']


def test_handler_without_a_connected_calendar():
    printed = []
    assert handle_calendar("add gym to my calendar tomorrow at 7 am", None, print, printed.append,
                           lambda q: "yes", NOW)
    assert "isn't connected yet" in printed[0]
    assert not handle_calendar("what's on tomorrow?", None, print, print, lambda q: "yes", NOW)


# ---- greeting and PARKER's knowledge -----------------------------------------

def test_greeting_events_merge_parker_and_google(calendar):
    agenda = Agenda(":memory:")
    agenda.add_event(date(2026, 11, 26), "18:00", "Gym")
    merged = [(e.time, e.text) for e in events_today(agenda, calendar, date(2026, 11, 26))]
    assert merged == [(None, "Holiday"), ("16:00", "AIML303 lecture"), ("18:00", "Gym")]


def test_assistant_knows_the_google_week(calendar):
    seen = []
    a = Assistant(generate=lambda m, h, **k: seen.append(k["context"]) or "ok", calendar=calendar, now=lambda: NOW)
    a.ask("What's on this week?")
    assert "Google Calendar, next 7 days: " in seen[0]
    assert "AIML303 lecture (today at 16:00)" in seen[0] and "Hackathon (Sat 28 Nov at 09:00)" in seen[0]


def test_assistant_says_when_google_is_unreachable():
    broken = GoogleCalendar(FakeService(error=OSError("offline")), clock=lambda: NOW)
    seen = []
    Assistant(generate=lambda m, h, **k: seen.append(k["context"]) or "ok", calendar=broken,
              now=lambda: NOW).ask("What's on?")
    assert "couldn't be reached" in seen[0]


def test_model_is_told_it_cannot_add_events():
    from backend import brain

    assert "You cannot add calendar events yourself" in brain.SYSTEM_PROMPT


def test_google_secrets_are_never_committed(tmp_path):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for path in ["memory/credentials.json", "memory/google_token.json", "credentials.json",
                 "client_secret_123.apps.googleusercontent.com.json"]:
        result = subprocess.run(["git", "check-ignore", "-q", path], cwd=root)
        assert result.returncode == 0, f"{path} is not ignored by Git"


# ---- desktop app --------------------------------------------------------------

def test_desktop_app_greets_with_google_events_and_adds_after_confirming(calendar, tmp_path, monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    pytest.importorskip("PySide6.QtWidgets")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QMessageBox

    from frontend.app import MainWindow

    QApplication.instance() or QApplication([])
    window = MainWindow(
        Assistant(generate=lambda m, h, **k: "ok", agenda=Agenda(":memory:"), calendar=calendar, now=lambda: NOW),
        make_speaker=None, make_listener=None, threaded=False, now=lambda: NOW,
        tray_available=lambda: False, make_hotkey=None,
        settings=QSettings(str(tmp_path / "s.ini"), QSettings.Format.IniFormat),
    )
    greeting = window.chat.messages[0][1]
    assert "Today: Holiday and AIML303 lecture at 16:00." in greeting
    texts = [window.agenda_panel.events.item(i).text() for i in range(window.agenda_panel.events.count())]
    assert "AIML303 lecture\ntoday at 16:00  ·  Google" in texts

    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.No)
    window.process("Add gym to my calendar tomorrow at 7 am")
    assert calendar.fake.events().inserted == []
    monkeypatch.setattr(QMessageBox, "question", lambda *a: QMessageBox.StandardButton.Yes)
    window.process("Add gym to my calendar tomorrow at 7 am")
    assert calendar.fake.events().inserted[0][1]["summary"] == "Gym"
    assert ("parker", 'Added to your calendar: "Gym", Fri 27 Nov 07:00–08:00.') in window.chat.messages
