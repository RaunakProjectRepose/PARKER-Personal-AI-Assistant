"""Reminders: "remind me in 20 minutes to stretch".

Requests are understood in code, never by the model, so a reminder's time is
exactly what was said. Reminders are stored in the private SQLite database, so
they survive restarts; ones that fell due while PARKER was closed are reported
as missed the next time it runs.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from backend.memory import DB_PATH

MAX_TEXT_LENGTH = 200
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45, "fifty": 50,
    "sixty": 60, "ninety": 90, "a couple of": 2, "a few": 3,
}

_START = re.compile(
    r"^(?:(?:hey|ok|okay)[\s,]+)?(?:parker[\s,]+)?(?:(?:can|could|would|will)\s+you\s+)?"
    r"(?:please\s+)?(?:remind\s+me|set\s+(?:a\s+|me\s+a\s+)?reminder|add\s+a\s+reminder)\b(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_NUM = r"\d+(?:\.\d+)?|a couple of|a few|forty-five|" + "|".join(
    sorted((w for w in _NUMBER_WORDS if " " not in w and "-" not in w), key=len, reverse=True)
)
_IN = re.compile(
    rf"\b(?:in|after)\s+(?:(?P<half>half\s+an?\s+hour)|(?P<n>{_NUM})\s*"
    r"(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?|h)\b(?P<andhalf>\s+and\s+a\s+half)?)",
    re.IGNORECASE,
)
_AT = re.compile(
    r"\b(?:at|by|for)\s+(?:(?P<word>noon|midday|midnight)|(?P<h>\d{1,2})(?:[:.](?P<m>\d{2}))?"
    r"\s*(?P<ampm>a\.?\s?m\.?|p\.?\s?m\.?)?(?:\s*o'?clock)?)(?=\W|$)",
    re.IGNORECASE,
)
_DAY = re.compile(
    r"\b(?:(?P<rel>today|tonight|tomorrow|this\s+evening|this\s+afternoon|this\s+morning)|"
    r"(?:on\s+)?(?P<wd>monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
    re.IGNORECASE,
)
_LEAD = re.compile(r"^(?:to|that|about|for|of|i\s+need\s+to|i\s+have\s+to)\s+", re.IGNORECASE)


class ReminderError(Exception):
    pass


@dataclass(frozen=True)
class Reminder:
    id: int
    due: datetime
    text: str

    def when(self, now: datetime) -> str:
        """'at 18:42', 'tomorrow at 09:00', 'on Fri 28 Nov at 10:00'."""
        at = f"at {self.due:%H:%M}"
        if self.due.date() == now.date():
            return at
        if self.due.date() == now.date() + timedelta(days=1):
            return f"tomorrow {at}"
        return f"on {self.due:%a} {self.due.day} {self.due:%b} {at}"


def _amount(word: str) -> float:
    word = word.lower()
    return float(_NUMBER_WORDS[word]) if word in _NUMBER_WORDS else float(word)


def parse_reminder(message: str, now: datetime) -> tuple[datetime, str] | None:
    """Return (due time, what to remind about) for a reminder request.

    Returns None if the message isn't a reminder request at all. Raises
    ReminderError if it is one but the time or the task is missing.
    """
    text = message.strip()
    if text.endswith("?") and not re.match(r"^(?:can|could|would|will)\s+you", text, re.I):
        return None  # "Did you remind me?" is a question, not a request
    start = _START.match(text)
    if not start:
        return None
    rest = start.group("rest")
    due: datetime | None = None

    if m := _IN.search(rest):
        if m.group("half"):
            delta = timedelta(minutes=30)
        else:
            amount = _amount(m.group("n")) + (0.5 if m.group("andhalf") else 0)
            unit = m.group("unit").lower()
            if unit.startswith(("h",)):
                delta = timedelta(hours=amount)
            elif unit.startswith("s"):
                delta = timedelta(seconds=amount)
            else:
                delta = timedelta(minutes=amount)
        if delta <= timedelta(0) or delta > timedelta(days=365):
            raise ReminderError("That's not a time I can set a reminder for.")
        due = now + delta
        rest = rest[: m.start()] + " " + rest[m.end():]
    else:
        day_match = _DAY.search(rest)
        at_match = _AT.search(rest)
        # "remind me what my exam date is" / "remind me about my plans for today"
        # are questions for PARKER to answer, not reminders to set.
        if not at_match and re.match(
            r"^\s*(?:what|who|where|when|how|why|which|whether|if|of|about)\b", rest, re.I
        ):
            return None
        if not day_match and not at_match:
            raise ReminderError(
                "When should I remind you? For example: \"remind me in 20 minutes to stretch\" "
                "or \"remind me at 6 pm to call Mum\"."
            )
        day = now.date()
        evening = False
        explicit_day = False
        if day_match:
            explicit_day = True
            rel = (day_match.group("rel") or "").lower()
            wd = (day_match.group("wd") or "").lower()
            if rel == "tomorrow":
                day += timedelta(days=1)
            elif rel in ("tonight", "this evening", "this afternoon"):
                evening = True
            elif wd:
                ahead = (_WEEKDAYS.index(wd) - now.weekday()) % 7
                day += timedelta(days=ahead or 7)
        if at_match:
            if at_match.group("word"):
                hour, minute = (0, 0) if at_match.group("word").lower() == "midnight" else (12, 0)
                ampm = None
            else:
                hour, minute = int(at_match.group("h")), int(at_match.group("m") or 0)
                ampm = (at_match.group("ampm") or "").lower().replace(".", "").replace(" ", "") or None
            if hour > 23 or minute > 59 or (ampm and not 1 <= hour <= 12):
                raise ReminderError("That isn't a valid time.")
            if ampm == "pm" and hour != 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0
            elif ampm is None and (evening and hour < 12):
                hour += 12
            due = datetime.combine(day, time(hour, minute))
            if ampm is None and hour <= 12 and not evening and due <= now and due + timedelta(hours=12) > now:
                due += timedelta(hours=12)  # "at 3" at 14:00 means 15:00
            if due <= now and not explicit_day:
                due += timedelta(days=1)  # "at 7" after 19:00 means tomorrow
        else:
            # A day but no time: morning for tomorrow/weekdays, 18:00 for "tonight".
            due = datetime.combine(day, time(18, 0) if evening else time(9, 0))
        if due <= now:
            raise ReminderError(f"{due:%H:%M} has already passed.")
        for match in sorted((x for x in (day_match, at_match) if x), key=lambda x: x.start(), reverse=True):
            rest = rest[: match.start()] + " " + rest[match.end():]

    task = " ".join(rest.split()).strip(" ,.;:!?-")
    task = _LEAD.sub("", task).strip(" ,.;:!?-")
    task = _LEAD.sub("", task).strip(" ,.;:!?-")
    if not task:
        raise ReminderError("What should I remind you about?")
    if len(task) > MAX_TEXT_LENGTH:
        raise ReminderError("That reminder is too long.")
    return due.replace(microsecond=0), task


class Reminders:
    """Stored reminders. `due(now)` returns the ones to announce, once each."""

    def __init__(self, path: Path | str = DB_PATH) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.RLock()
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS reminders (
                   id       INTEGER PRIMARY KEY AUTOINCREMENT,
                   due      TEXT NOT NULL,
                   text     TEXT NOT NULL,
                   fired_at TEXT
               )"""
        )
        self._db.commit()

    def add(self, due: datetime, text: str) -> Reminder:
        with self._lock:
            cur = self._db.execute(
                "INSERT INTO reminders (due, text) VALUES (?, ?)",
                (due.isoformat(timespec="seconds"), text),
            )
            self._db.commit()
            return Reminder(cur.lastrowid, due, text)

    def upcoming(self) -> list[Reminder]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, due, text FROM reminders WHERE fired_at IS NULL ORDER BY due, id"
            ).fetchall()
        return [Reminder(r[0], datetime.fromisoformat(r[1]), r[2]) for r in rows]

    def due(self, now: datetime) -> list[Reminder]:
        """Reminders that are due, marked as announced so they fire only once."""
        with self._lock:
            ready = [r for r in self.upcoming() if r.due <= now]
            for r in ready:
                self._db.execute(
                    "UPDATE reminders SET fired_at = ? WHERE id = ?",
                    (now.isoformat(timespec="seconds"), r.id),
                )
            self._db.commit()
        return ready

    def cancel(self, reminder_id: int) -> bool:
        with self._lock:
            cur = self._db.execute(
                "DELETE FROM reminders WHERE id = ? AND fired_at IS NULL", (reminder_id,)
            )
            self._db.commit()
        return cur.rowcount == 1

    def close(self) -> None:
        self._db.close()


def announcement(reminder: Reminder, now: datetime) -> str:
    """What PARKER says when a reminder fires (mentioning if it was missed)."""
    late = now - reminder.due
    if late > timedelta(minutes=5):
        return f"You missed a reminder from {reminder.when(now).replace('at ', '')}: {reminder.text}."
    return f"Reminder: {reminder.text}."
