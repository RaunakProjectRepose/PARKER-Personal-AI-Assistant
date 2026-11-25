"""PARKER's agenda: plans for the next session and dated events.

Stored in the same private SQLite database as memories (ignored by Git).
This is PARKER's own small calendar; syncing with Google Calendar is planned
for Milestone 4.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from backend.memory import DB_PATH

MAX_TEXT_LENGTH = 200
_TIME = re.compile(r"^([01]?\d|2[0-3])[:.]([0-5]\d)$")
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class AgendaError(Exception):
    """Raised when a plan or event cannot be saved."""


@dataclass(frozen=True)
class Plan:
    id: int
    text: str


@dataclass(frozen=True)
class Event:
    id: int
    day: date
    time: str | None  # "HH:MM" or None for all-day
    text: str

    def when(self, today: date | None = None) -> str:
        """'today at 18:00', 'tomorrow', 'Sat 28 Nov at 10:00'."""
        today = today or date.today()
        if self.day == today:
            day = "today"
        elif self.day == today + timedelta(days=1):
            day = "tomorrow"
        else:
            day = f"{self.day:%a} {self.day.day} {self.day:%b}"
        return f"{day} at {self.time}" if self.time else day

    def describe(self, today: date | None = None) -> str:
        return f"{self.text} ({self.when(today)})"


def parse_day(word: str, today: date | None = None) -> date:
    """Understand 'today', 'tomorrow', a weekday, '2026-12-03' or '3/12' (day/month)."""
    today = today or date.today()
    w = word.strip().lower()
    if w == "today":
        return today
    if w == "tomorrow":
        return today + timedelta(days=1)
    if w in _WEEKDAYS:
        ahead = (_WEEKDAYS.index(w) - today.weekday()) % 7
        return today + timedelta(days=ahead or 7)  # "friday" on a Friday = next week
    try:
        return date.fromisoformat(w)
    except ValueError:
        pass
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?", w)
    if m:
        d, mo, y = int(m[1]), int(m[2]), int(m[3] or today.year)
        try:
            result = date(y, mo, d)
        except ValueError as exc:
            raise AgendaError(f"'{word}' isn't a real date.") from exc
        if not m[3] and result < today:
            result = date(y + 1, mo, d)  # "3/1" in December means next January
        return result
    raise AgendaError(
        f"I couldn't understand the date '{word}'. Use today, tomorrow, a weekday, "
        "2026-12-03 or 3/12 (day/month)."
    )


def parse_time(text: str) -> str | None:
    """'18:00', '9.30' -> 'HH:MM'; '' -> None (all day). Raises AgendaError if invalid."""
    text = text.strip()
    if not text:
        return None
    m = _TIME.match(text)
    if not m:
        raise AgendaError(f"'{text}' isn't a valid time. Use HH:MM, e.g. 18:00.")
    return f"{int(m[1]):02d}:{m[2]}"


def parse_event(args: str, today: date | None = None) -> tuple[date, str | None, str]:
    """Split '/event' arguments: '<day> [HH:MM] <text>'."""
    parts = args.split(maxsplit=2)
    if len(parts) < 2:
        raise AgendaError("Usage: /event <day> [HH:MM] <what>, e.g. /event today 18:00 Gym")
    day = parse_day(parts[0], today)
    m = _TIME.match(parts[1])
    if m:
        if len(parts) < 3:
            raise AgendaError("What's the event? e.g. /event today 18:00 Gym")
        return day, f"{int(m[1]):02d}:{m[2]}", parts[2]
    return day, None, " ".join(parts[1:])


def _clean(text: str) -> str:
    text = " ".join(text.split())
    if not text:
        raise AgendaError("That can't be empty.")
    if len(text) > MAX_TEXT_LENGTH:
        raise AgendaError(f"That's too long (limit {MAX_TEXT_LENGTH} characters).")
    return text


class Agenda:
    """Open plans for the next session, and dated events."""

    def __init__(self, path: Path | str = DB_PATH) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # The desktop app uses PARKER from a background thread as well as the
        # window, so one connection is shared and guarded by a lock.
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.RLock()
        self._db.executescript(
            """CREATE TABLE IF NOT EXISTS plans (
                   id         INTEGER PRIMARY KEY AUTOINCREMENT,
                   text       TEXT NOT NULL,
                   created_at TEXT NOT NULL,
                   done_at    TEXT
               );
               CREATE TABLE IF NOT EXISTS events (
                   id   INTEGER PRIMARY KEY AUTOINCREMENT,
                   day  TEXT NOT NULL,
                   time TEXT,
                   text TEXT NOT NULL
               );"""
        )
        self._db.commit()

    # ---- plans ------------------------------------------------------------
    def add_plan(self, text: str) -> Plan:
        with self._lock:
            text = _clean(text)
            now = datetime.now().isoformat(timespec="seconds")
            cur = self._db.execute("INSERT INTO plans (text, created_at) VALUES (?, ?)", (text, now))
            self._db.commit()
            return Plan(cur.lastrowid, text)

    def open_plans(self) -> list[Plan]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, text FROM plans WHERE done_at IS NULL ORDER BY id"
            ).fetchall()
            return [Plan(*r) for r in rows]

    def complete_plan(self, plan_id: int) -> bool:
        with self._lock:
            now = datetime.now().isoformat(timespec="seconds")
            cur = self._db.execute(
                "UPDATE plans SET done_at = ? WHERE id = ? AND done_at IS NULL", (now, plan_id)
            )
            self._db.commit()
            return cur.rowcount == 1

    # ---- events -----------------------------------------------------------
    def add_event(self, day: date, time: str | None, text: str) -> Event:
        with self._lock:
            text = _clean(text)
            cur = self._db.execute(
                "INSERT INTO events (day, time, text) VALUES (?, ?, ?)", (day.isoformat(), time, text)
            )
            self._db.commit()
            return Event(cur.lastrowid, day, time, text)

    def events_between(self, start: date, end: date) -> list[Event]:
        """Events from `start` to `end` inclusive, in date and time order."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, day, time, text FROM events WHERE day BETWEEN ? AND ? "
                "ORDER BY day, time IS NOT NULL, time, id",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
            return [Event(r[0], date.fromisoformat(r[1]), r[2], r[3]) for r in rows]

    def events_on(self, day: date) -> list[Event]:
        with self._lock:
            return self.events_between(day, day)

    def delete_event(self, event_id: int) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM events WHERE id = ?", (event_id,))
            self._db.commit()
            return cur.rowcount == 1

    def close(self) -> None:
        with self._lock:
            self._db.close()
