"""Google Calendar: see upcoming events and add new ones (after confirmation).

One-time setup (see docs/GOOGLE_CALENDAR.md):
    1. Put the "Desktop app" OAuth client file from Google Cloud Console at
       memory/credentials.json  (ignored by Git).
    2. Run:  python -m backend.calendar_connect   (or: python -m backend.google_calendar --connect)
       A browser opens on Google's own sign-in page; PARKER never sees the password.
       The resulting key is saved to memory/google_token.json (ignored by Git).

Permission asked: calendar.events (read and write events only, not calendar
settings or sharing). Revoke any time at myaccount.google.com/permissions.

Event requests ("add a meeting with Rahul to my calendar tomorrow at 3") are
understood in code; PARKER always shows the event and asks before creating it.
"""

from __future__ import annotations

import re
import sys
import threading
import time as _time
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable

from backend.agenda import Event
from backend.memory import PROJECT_ROOT
from backend.reminders import _AT, _DAY, _WEEKDAYS

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
MEMORY_DIR = PROJECT_ROOT / "memory"
CREDENTIALS_PATH = MEMORY_DIR / "credentials.json"
TOKEN_PATH = MEMORY_DIR / "google_token.json"
CACHE_SECONDS = 300  # fetch from Google at most every 5 minutes
WINDOW_DAYS = 8  # today + the next 7 days


class CalendarError(Exception):
    pass


@dataclass(frozen=True)
class CalendarEvent:
    title: str
    start: datetime  # local time; midnight for all-day events
    end: datetime
    all_day: bool

    def as_agenda_event(self) -> Event:
        """In the same shape as PARKER's own agenda events, for greetings and lists."""
        return Event(id=-1, day=self.start.date(), time=None if self.all_day else f"{self.start:%H:%M}",
                     text=self.title)


def _local(value: str) -> datetime:
    """RFC 3339 from Google ("2026-11-27T15:00:00+05:30") -> naive local time."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)


def _parse_event(item: dict) -> CalendarEvent | None:
    start, end = item.get("start", {}), item.get("end", {})
    title = item.get("summary") or "(no title)"
    if "date" in start:  # all-day
        day = date.fromisoformat(start["date"])
        last = date.fromisoformat(end.get("date", start["date"]))
        return CalendarEvent(title, datetime.combine(day, time()), datetime.combine(last, time()), True)
    if "dateTime" in start:
        return CalendarEvent(title, _local(start["dateTime"]), _local(end.get("dateTime", start["dateTime"])), False)
    return None


def build_service(credentials_path: Path = CREDENTIALS_PATH, token_path: Path = TOKEN_PATH,
                  interactive: bool = False):
    """Load the saved key (refreshing it if needed). With interactive=True and no
    key yet, open Google's sign-in page in the browser."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise CalendarError("Google libraries missing. Run: python -m pip install -r requirements.txt") from exc

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            creds = None
            if not interactive:
                raise CalendarError(
                    "Google sign-in expired. Run: python -m backend.calendar_connect"
                ) from exc
    if not creds or not creds.valid:
        if not interactive:
            raise CalendarError("Google Calendar isn't connected yet. Run: python -m backend.calendar_connect")
        if not credentials_path.exists():
            raise CalendarError(
                f"Put the OAuth client file from Google Cloud Console at {credentials_path} first "
                "(see docs/GOOGLE_CALENDAR.md)."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


class GoogleCalendar:
    """Reads (with a 5-minute cache) and adds events on the primary calendar."""

    def __init__(self, service=None, *, make_service: Callable[[], object] = build_service,
                 clock: Callable[[], datetime] = datetime.now) -> None:
        self._service = service
        self._make_service = make_service
        self._clock = clock
        self._lock = threading.RLock()
        self._events: list[CalendarEvent] = []
        self._fetched_at: float | None = None
        self._window_start: date | None = None

    @property
    def service(self):
        if self._service is None:
            self._service = self._make_service()
        return self._service

    # ---- reading -----------------------------------------------------------
    def refresh(self) -> list[CalendarEvent]:
        """Fetch today and the next 7 days from Google (network)."""
        today = self._clock().date()
        start = datetime.combine(today, time()).astimezone()
        end = start + timedelta(days=WINDOW_DAYS)
        try:
            response = self.service.events().list(
                calendarId="primary", timeMin=start.isoformat(), timeMax=end.isoformat(),
                singleEvents=True, orderBy="startTime", maxResults=100,
            ).execute()
        except CalendarError:
            raise
        except Exception as exc:
            raise CalendarError(f"Couldn't read Google Calendar: {exc}") from exc
        events = [e for e in (_parse_event(i) for i in response.get("items", [])) if e]
        with self._lock:
            self._events, self._fetched_at, self._window_start = events, _time.monotonic(), today
        return events

    def refresh_if_stale(self, max_age: float = CACHE_SECONDS) -> None:
        with self._lock:
            fresh = (
                self._fetched_at is not None
                and _time.monotonic() - self._fetched_at < max_age
                and self._window_start == self._clock().date()
            )
        if not fresh:
            self.refresh()

    def cached(self, start: date, end: date) -> list[CalendarEvent]:
        """Events overlapping start..end (inclusive), from the cache only (no network)."""
        with self._lock:
            events = list(self._events)
        lo, hi = datetime.combine(start, time()), datetime.combine(end + timedelta(days=1), time())
        return [e for e in events if e.start < hi and (e.end > lo or e.start >= lo)]

    # ---- adding --------------------------------------------------------------
    def add(self, title: str, start: datetime, end: datetime, all_day: bool) -> CalendarEvent:
        if all_day:
            body = {"summary": title, "start": {"date": start.date().isoformat()},
                    "end": {"date": (start.date() + timedelta(days=1)).isoformat()}}
        else:
            body = {"summary": title, "start": {"dateTime": start.astimezone().isoformat()},
                    "end": {"dateTime": end.astimezone().isoformat()}}
        try:
            created = self.service.events().insert(calendarId="primary", body=body).execute()
        except CalendarError:
            raise
        except Exception as exc:
            raise CalendarError(f"Couldn't add the event to Google Calendar: {exc}") from exc
        event = _parse_event(created) or CalendarEvent(title, start, end, all_day)
        with self._lock:
            self._events = sorted(self._events + [event], key=lambda e: e.start)
        return event


# ---- understanding "add ... to my calendar" ----------------------------------

_PREAMBLE = (r"^(?:(?:hey|ok|okay)[\s,]+)?(?:parker[\s,]+)?(?:(?:can|could|would|will)\s+you\s+)?"
             r"(?:please\s+)?")
_ADD = re.compile(
    _PREAMBLE + r"(?:add|put|create|book|schedule)\s+(?P<a>.+?)\s+(?:to|in|on|into)\s+(?:my\s+)?"
    r"(?:google\s+)?calendar(?P<b>.*)$",
    re.IGNORECASE,
)
_SCHEDULE = re.compile(_PREAMBLE + r"schedule\s+(?P<a>.+)$", re.IGNORECASE)
_FOR = re.compile(
    r"\bfor\s+(?:(?P<half>half\s+an?\s+hour)|(?P<n>\d+(?:\.\d+)?|an?|one|two|three|four|five|six)\s*"
    r"(?P<unit>hours?|hrs?|minutes?|mins?)(?P<andhalf>\s+and\s+a\s+half)?)\b",
    re.IGNORECASE,
)
_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
_ORD = r"(?:st|nd|rd|th)?"
# "on the 3rd", "on 3 December", "on December 3rd", "on 3/12" (day/month)
_DATE = re.compile(
    rf"\b(?:on\s+(?P<dd>\d{{1,2}})/(?P<mm>\d{{1,2}})(?:/(?P<yy>\d{{4}}))?"
    rf"|on\s+(?:the\s+)?(?P<d1>\d{{1,2}}){_ORD}(?:\s+(?:of\s+)?(?P<m1>{_MON}))?"
    rf"|(?:on\s+)?(?P<m2>{_MON})\s+(?:the\s+)?(?P<d2>\d{{1,2}}){_ORD}"
    rf"|(?:on\s+)?(?:the\s+)?(?P<d3>\d{{1,2}}){_ORD}\s+(?:of\s+)?(?P<m3>{_MON}))\b",
    re.IGNORECASE,
)


def _date_from(match: re.Match, today: date) -> date:
    if match.group("dd"):
        d, mo = int(match.group("dd")), int(match.group("mm"))
        year = int(match.group("yy") or today.year)
        explicit_month = True
    else:
        d = int(match.group("d1") or match.group("d2") or match.group("d3"))
        name = (match.group("m1") or match.group("m2") or match.group("m3") or "").lower()
        explicit_month = bool(name)
        mo = _MONTHS.index(name[:3]) + 1 if name else today.month
        year = today.year
    try:
        result = date(year, mo, d)
    except ValueError as exc:
        raise CalendarError("That isn't a real date.") from exc
    if result < today:  # already passed: the next one
        if explicit_month:
            result = result.replace(year=year + 1)
        else:
            nxt = date(year + (mo == 12), mo % 12 + 1, 1)
            try:
                result = nxt.replace(day=d)
            except ValueError as exc:
                raise CalendarError("That isn't a real date.") from exc
    return result


@dataclass(frozen=True)
class EventRequest:
    title: str
    start: datetime
    end: datetime
    all_day: bool

    def describe(self) -> str:
        day = f"{self.start:%a} {self.start.day} {self.start:%b}"
        if self.all_day:
            return f"\"{self.title}\", {day} (all day)"
        return f"\"{self.title}\", {day} {self.start:%H:%M}–{self.end:%H:%M}"


def parse_event_request(message: str, now: datetime) -> EventRequest | None:
    """Understand "add X to my calendar <when>" / "schedule X <when>".

    None if it isn't such a request; CalendarError if the time or title is missing.
    """
    text = message.strip().rstrip("?.! ")
    m = _ADD.match(text) or _SCHEDULE.match(text)
    if not m:
        return None
    rest = " ".join(g for g in m.groupdict().values() if g)

    duration = timedelta(hours=1)
    if f := _FOR.search(rest):
        if f.group("half"):
            duration = timedelta(minutes=30)
        else:
            n = f.group("n").lower()
            amount = float(_NUMBERS.get(n, n)) + (0.5 if f.group("andhalf") else 0)
            duration = timedelta(hours=amount) if f.group("unit").lower().startswith("h") else timedelta(minutes=amount)
        rest = rest[: f.start()] + " " + rest[f.end():]

    day_match, at_match = _DAY.search(rest), _AT.search(rest)
    date_match = None if day_match else _DATE.search(rest)
    if date_match:  # "on the 3rd" must not also be read as a time
        if at_match and at_match.start() < date_match.end() and at_match.end() > date_match.start():
            at_match = None
        day_match = date_match
    if not day_match and not at_match:
        raise CalendarError("When is it? For example: \"add a meeting with Rahul to my calendar tomorrow at 3\".")
    day, explicit_day, evening = now.date(), False, False
    if date_match:
        explicit_day = True
        day = _date_from(date_match, now.date())
    elif day_match:
        explicit_day = True
        rel, wd = (day_match.group("rel") or "").lower(), (day_match.group("wd") or "").lower()
        if rel == "tomorrow":
            day += timedelta(days=1)
        elif rel in ("tonight", "this evening", "this afternoon"):
            evening = True
        elif wd:
            day += timedelta(days=(_WEEKDAYS.index(wd) - now.weekday()) % 7 or 7)

    all_day = at_match is None
    start = datetime.combine(day, time())
    if at_match:
        if at_match.group("word"):
            hour, minute, ampm = (0 if at_match.group("word").lower() == "midnight" else 12), 0, None
        else:
            hour, minute = int(at_match.group("h")), int(at_match.group("m") or 0)
            ampm = (at_match.group("ampm") or "").lower().replace(".", "").replace(" ", "") or None
        if hour > 23 or minute > 59 or (ampm and not 1 <= hour <= 12):
            raise CalendarError("That isn't a valid time.")
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        elif ampm is None and 1 <= hour <= 7:
            hour += 12  # "at 3" for a meeting almost always means 3 pm
        elif ampm is None and evening and hour < 12:
            hour += 12
        start = datetime.combine(day, time(hour, minute))
        if start <= now and not explicit_day:
            start += timedelta(days=1)
        if start <= now:
            raise CalendarError(f"{start:%H:%M} has already passed.")
    for match in sorted((x for x in (day_match, at_match) if x), key=lambda x: x.start(), reverse=True):
        rest = rest[: match.start()] + " " + rest[match.end():]

    title = " ".join(rest.split()).strip(" ,.;:-")
    title = re.sub(r"^(?:an?\s+event\s+(?:called|named|for)\s+|(?:called|named)\s+|the\s+|"
                   r"an?\s+(?=event|meeting|call|session|appointment))", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"\s+(?:on|at|for|to)$", "", title, flags=re.IGNORECASE).strip()
    if not title:
        raise CalendarError("What should the event be called?")
    title = title[0].upper() + title[1:]
    end = start + (timedelta(days=1) if all_day else duration)
    return EventRequest(title, start, end, all_day)


def connect_and_show() -> int:
    """`python -m backend.google_calendar --connect`: sign in once and list the week."""
    try:
        calendar = GoogleCalendar(make_service=lambda: build_service(interactive=True))
        events = calendar.refresh()
    except CalendarError as err:
        print(f"PARKER calendar error: {err}")
        return 1
    print("Connected to Google Calendar. Coming up:")
    for e in events:
        when = f"{e.start:%a %d %b}" + ("" if e.all_day else f" {e.start:%H:%M}")
        print(f"  {when}  {e.title}")
    if not events:
        print("  (nothing in the next 7 days)")
    return 0


if __name__ == "__main__":
    sys.exit(connect_and_show() if "--connect" in sys.argv else 0)
