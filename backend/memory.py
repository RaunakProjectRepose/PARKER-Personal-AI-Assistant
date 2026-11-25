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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("PARKER_MEMORY_DB", PROJECT_ROOT / "memory" / "parker.db"))
MAX_FACT_LENGTH = 300  # Keeps the system prompt (and the context window) in check.
MAX_FACTS_IN_PROMPT = 50

# "remember that my favourite colour is blue", "Parker, please remember I'm vegetarian"
_REMEMBER = re.compile(
    r"^(?:(?:hey|ok|okay)\s+)?(?:parker[\s,]+)?(?:please\s+)?remember\s+(?:that\s+)?(?P<fact>.+)$",
    re.IGNORECASE,
)
# "remember when...", "remember to buy milk" are not facts to store.
_NOT_A_FACT = re.compile(r"^(?:when|to|what|how|why|if|who|where)\b", re.IGNORECASE)


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
    match = _REMEMBER.match(text)
    if not match:
        return None
    fact = match.group("fact").strip().rstrip(".!").strip()
    if not fact or _NOT_A_FACT.match(fact):
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
        self._db = sqlite3.connect(str(path))
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
        rows = self._db.execute("SELECT id, text, created_at FROM facts ORDER BY id").fetchall()
        return [Fact(*row) for row in rows]

    def texts(self, limit: int = MAX_FACTS_IN_PROMPT) -> list[str]:
        """The most recent facts' text, oldest first, for the system prompt."""
        return [f.text for f in self.all()[-limit:]]

    def update(self, fact_id: int, text: str) -> bool:
        text = _clean(text)
        cur = self._db.execute("UPDATE facts SET text = ? WHERE id = ?", (text, fact_id))
        self._db.commit()
        return cur.rowcount == 1

    def delete(self, fact_id: int) -> bool:
        cur = self._db.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
        self._db.commit()
        return cur.rowcount == 1

    def clear(self) -> int:
        cur = self._db.execute("DELETE FROM facts")
        self._db.commit()
        return cur.rowcount

    def close(self) -> None:
        self._db.close()
