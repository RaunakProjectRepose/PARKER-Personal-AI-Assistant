"""PARKER's long-term memory: facts you have asked it to remember.

Facts are stored in a private SQLite database on this laptop
(`memory/parker.db` by default). The database is ignored by Git, so it never
goes to GitHub. PARKER only saves what you explicitly ask it to: nothing is
remembered automatically.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("PARKER_MEMORY_DB", PROJECT_ROOT / "memory" / "parker.db"))
MAX_FACT_LENGTH = 300  # Keeps the system prompt (and the context window) in check.
MAX_FACTS_IN_PROMPT = 50

# Separators Whisper may insert between words: "Remember, my favourite..."
_SEP = r"[\s,.;:!-]+"
_ASK = r"(?:remember|don'?t\s+forget|make\s+a\s+note|note\s+down|note)"

# Request first: "remember that my favourite colour is blue",
# "Parker, please remember I'm vegetarian", "Remember, my colour is blue",
# "Can you remember that I study at night", "Don't forget that I'm allergic to nuts"
_REQUEST_FIRST = re.compile(
    rf"^(?:(?:hey|ok|okay){_SEP})?(?:parker{_SEP})?"
    rf"(?:(?:can|could|will|would)\s+you{_SEP})?(?:please{_SEP})?"
    rf"{_ASK}{_SEP}(?:(?:that|this){_SEP})?(?P<fact>.+)$",
    re.IGNORECASE,
)
# Fact first: "My favourite colour is blue, do remember that.",
# "I'm vegetarian. Please remember that", "I live in Pune, remember this"
_FACT_FIRST = re.compile(
    rf"^(?P<fact>.+?){_SEP}(?:(?:please|do|so|and)\s+)*(?:parker{_SEP})?"
    rf"{_ASK}(?:{_SEP}(?:that|this|it))?(?:{_SEP}please)?(?:{_SEP}parker)?[\s.!]*$",
    re.IGNORECASE,
)
# "remember when...", "remember to buy milk" are not facts to store.
_NOT_A_FACT = re.compile(r"^(?:when|to|what|how|why|if|who|where|me)\b", re.IGNORECASE)
_ENDS_WITH_POINTER = re.compile(r"\b(?:that|this|it)\W*(?:please|parker)?\W*$", re.IGNORECASE)
# "Help me remember", "I want you to remember" are not facts either.
_NOT_A_FACT_END = re.compile(r"\b(?:me|you|us|to)$", re.IGNORECASE)
# Leftover words at the end of a fact: "I live in Pune, so" -> "I live in Pune"
_TRAILING_FILLER = re.compile(r"[\s,.;:!-]+(?:so|and|please|do)?$", re.IGNORECASE)


class MemoryStoreError(Exception):
    """Raised when a memory cannot be saved or changed."""


@dataclass(frozen=True)
class Fact:
    id: int
    text: str
    created_at: str


def parse_remember_request(message: str) -> str | None:
    """Return the fact in a "remember that ..." message, or None if it isn't one."""
    text = message.strip()
    if text.endswith("?"):
        return None  # "Do you remember ...?" / "Remember what I said?" are questions.
    match = _REQUEST_FIRST.match(text)
    if not match:
        match = _FACT_FIRST.match(text)
        # Fact first needs a clear break before "remember" ("..., remember that")
        # or an explicit "that/this/it" after it, so "Help me remember" is ignored.
        if match and not (
            re.match(r"\s*[,.;:!-]", text[match.end("fact"):])
            or _ENDS_WITH_POINTER.search(text)
        ):
            match = None
    if not match:
        return None
    fact = match.group("fact").strip()
    fact = _TRAILING_FILLER.sub("", fact).strip(" ,.;:!-")
    if (
        len(fact.split()) < 2  # "that", "things", "it"
        or _NOT_A_FACT.match(fact)
        or _NOT_A_FACT_END.search(fact)
    ):
        return None
    return fact


def _clean(text: str) -> str:
    text = " ".join(text.split())
    if not text:
        raise MemoryStoreError("A memory can't be empty.")
    if len(text) > MAX_FACT_LENGTH:
        raise MemoryStoreError(f"That's too long to remember (limit {MAX_FACT_LENGTH} characters).")
    return text


class Memory:
    """A small store of facts, kept in SQLite."""

    def __init__(self, path: Path | str = DB_PATH) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        # The desktop app uses PARKER from a background thread as well as the
        # window, so one connection is shared and guarded by a lock.
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.RLock()
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS facts (
                   id         INTEGER PRIMARY KEY AUTOINCREMENT,
                   text       TEXT NOT NULL,
                   created_at TEXT NOT NULL
               )"""
        )
        self._db.commit()

    def add(self, text: str) -> tuple[Fact, bool]:
        """Save a fact. Returns (fact, created); created is False for a duplicate."""
        with self._lock:
            text = _clean(text)
            for fact in self.all():
                if fact.text.casefold() == text.casefold():
                    return fact, False
            now = datetime.now().isoformat(timespec="seconds")
            cur = self._db.execute(
                "INSERT INTO facts (text, created_at) VALUES (?, ?)", (text, now)
            )
            self._db.commit()
            return Fact(cur.lastrowid, text, now), True

    def all(self) -> list[Fact]:
        with self._lock:
            rows = self._db.execute("SELECT id, text, created_at FROM facts ORDER BY id").fetchall()
            return [Fact(*row) for row in rows]

    def texts(self, limit: int = MAX_FACTS_IN_PROMPT) -> list[str]:
        """The most recent facts' text, oldest first, for the system prompt."""
        with self._lock:
            return [f.text for f in self.all()[-limit:]]

    def update(self, fact_id: int, text: str) -> bool:
        with self._lock:
            text = _clean(text)
            cur = self._db.execute("UPDATE facts SET text = ? WHERE id = ?", (text, fact_id))
            self._db.commit()
            return cur.rowcount == 1

    def delete(self, fact_id: int) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
            self._db.commit()
            return cur.rowcount == 1

    def clear(self) -> int:
        with self._lock:
            cur = self._db.execute("DELETE FROM facts")
            self._db.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._db.close()
