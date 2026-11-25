"""PARKER's conversation manager.

The brain answers one message at a time and remembers nothing. This module
keeps the recent conversation and passes it to the brain with every new
message, so PARKER can follow along ("What did I just ask you?").

Memory here lasts only while the program runs. Saving memories between
sessions is Milestone 2.
"""

from __future__ import annotations

from typing import Callable

from backend import brain

# Qwen is loaded with a 4096-token context window (see `ollama ps`).
# Ten exchanges of short spoken-style replies fit comfortably inside it.
DEFAULT_MAX_TURNS = 10


class Assistant:
    """Holds the conversation history and asks the brain for replies."""

    def __init__(
        self,
        generate: Callable[..., str] = brain.generate_response,
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")
        # `generate` is swappable so tests can use a fake brain instead of Qwen.
        self._generate = generate
        self.max_turns = max_turns
        self.history: list[dict] = []

    def ask(self, user_message: str) -> str:
        """Send a message to PARKER and return the reply.

        If the brain fails, the error is raised and the history is left
        unchanged, so a failed message is not half-remembered.
        """
        text = user_message.strip()
        reply = self._generate(text, list(self.history))
        self.history.append({"role": "user", "content": text})
        self.history.append({"role": "assistant", "content": reply})
        self._trim()
        return reply

    def reset(self) -> None:
        """Forget the current conversation."""
        self.history.clear()

    def _trim(self) -> None:
        # Each turn is two messages: the user's and PARKER's. Drop the oldest.
        excess = len(self.history) - self.max_turns * 2
        if excess > 0:
            del self.history[:excess]
