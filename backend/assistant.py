"""PARKER's conversation manager.

The brain answers one message at a time and remembers nothing. This module
keeps the recent conversation and passes it to the brain with every new
message, so PARKER can follow along ("What did I just ask you?").

The conversation itself lasts only while the program runs. Facts you ask
PARKER to remember are kept in `memory.py` and survive restarts.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from backend import brain
from backend.agenda import Agenda
from backend.memory import Memory

# Qwen is loaded with a 4096-token context window (see `ollama ps`).
# Ten exchanges of short spoken-style replies fit comfortably inside it.
DEFAULT_MAX_TURNS = 10


class Assistant:
    """Holds the conversation history and asks the brain for replies."""

    def __init__(
        self,
        generate: Callable[..., str] = brain.generate_response,
        max_turns: int = DEFAULT_MAX_TURNS,
        memory: Memory | None = None,
        agenda: Agenda | None = None,
        now: Callable[[], datetime] = datetime.now,
        calendar=None,
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")
        # `generate` is swappable so tests can use a fake brain instead of Qwen.
        self._generate = generate
        self.max_turns = max_turns
        self.history: list[dict] = []
        self.memory = memory  # Long-term facts; None means no saved memory.
        self.agenda = agenda  # Plans and events; None means no agenda.
        self.calendar = calendar  # Google Calendar; None if not connected.
        self._now = now

    def ask(self, user_message: str) -> str:
        """Send a message to PARKER and return the reply.

        If the brain fails, the error is raised and the history is left
        unchanged, so a failed message is not half-remembered.
        """
        text = user_message.strip()
        facts = self.memory.texts() if self.memory else []
        reply = self._generate(
            text, list(self.history), facts=facts, context=self.context()
        )
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": reply})
        self._trim()
        return reply

    def context(self) -> str:
        """Today's date and the agenda, so PARKER can answer "what's on today?"."""
        now = self._now()
        lines = [f"Current date and time: {now:%A} {now.day} {now:%B %Y}, {now:%H:%M}."]
        if self.agenda is not None:
            today = now.date()
            plans = self.agenda.open_plans()
            events = self.agenda.events_between(today, today + timedelta(days=7))
            lines.append(
                "Plans for this session: "
                + ("; ".join(p.text for p in plans) if plans else "none.")
            )
            lines.append(
                "Events in the next 7 days: "
                + ("; ".join(e.describe(today) for e in events) if events else "none.")
            )
            lines.append(
                "Only mention plans and events listed here. You cannot add or change "
                "them yourself: your owner uses /plan and /event for that."
            )
        if self.calendar is not None:
            today = now.date()
            try:
                self.calendar.refresh_if_stale()  # runs on the worker thread in the app
                google = self.calendar.cached(today, today + timedelta(days=7))
                described = "; ".join(e.as_agenda_event().describe(today) for e in google)
                lines.append("Google Calendar, next 7 days: " + (described or "nothing scheduled."))
            except Exception:
                lines.append("Google Calendar: couldn't be reached just now, so say you can't check it.")
        return "\n".join(lines)

    def reset(self) -> None:
        """Forget the current conversation."""
        self.history.clear()

    def _trim(self) -> None:
        # Each turn is two messages: the user's and PARKER's. Drop the oldest.
        excess = len(self.history) - self.max_turns * 2
        if excess > 0:
            del self.history[:excess]
