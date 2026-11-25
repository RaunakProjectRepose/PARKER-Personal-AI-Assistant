"""PARKER's brain: a small adapter around the local Ollama chat API.

Everything model-specific lives in this file. The rest of PARKER only calls
``generate_response()``, so the model or runtime can be swapped later without
touching the conversation code.

Quick manual test (Ollama must be running), from the project folder:

    python -m backend.brain "Introduce yourself in one sentence."
"""

from __future__ import annotations

import os
import sys

import requests

# Settings can be overridden with environment variables, so nothing personal
# or machine-specific has to be hard-coded or committed.
OLLAMA_URL = os.environ.get("PARKER_OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("PARKER_MODEL", "qwen3.5:4b")
TIMEOUT_SECONDS = 120  # The first request may need to load the model onto the GPU.

SYSTEM_PROMPT = (
    "You are PARKER, a calm, composed and thoughtful personal AI assistant. "
    "You run locally on your owner's Windows laptop as part of a personal "
    "project; the underlying language model is Qwen. "
    "Speak in natural British English. Keep replies brief and conversational, "
    "usually one to three sentences, because they may be read aloud. "
    "Do not use markdown, bullet points or emoji. "
    "If you are unsure of something, say so plainly rather than guessing. "
    "Never invent facts about the user: if they ask about their own "
    "preferences, plans or details that they have not told you in this "
    "conversation, say that you don't know and invite them to tell you."
)


class BrainError(Exception):
    """Raised when PARKER cannot get a reply from the language model."""


def build_messages(user_message: str, history: list[dict] | None = None) -> list[dict]:
    """Return the full message list: system prompt, earlier turns, new message."""
    if not user_message or not user_message.strip():
        raise ValueError("user_message must not be empty")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user_message.strip()})
    return messages


def generate_response(
    user_message: str,
    history: list[dict] | None = None,
    *,
    model: str = MODEL,
    base_url: str = OLLAMA_URL,
    timeout: float = TIMEOUT_SECONDS,
) -> str:
    """Send a message to the local model and return PARKER's reply as text.

    ``history`` is a list of earlier turns, each ``{"role": "user" | "assistant",
    "content": "..."}``. It is not modified.
    """
    payload = {
        "model": model,
        "messages": build_messages(user_message, history),
        "stream": False,  # One complete reply; streaming comes later for voice.
        "think": False,  # Thinking mode took ~34 s per reply; off takes < 1 s.
    }

    try:
        response = requests.post(f"{base_url}/api/chat", json=payload, timeout=timeout)
    except requests.ConnectionError as exc:
        raise BrainError(
            f"Cannot reach Ollama at {base_url}. Is the Ollama app running?"
        ) from exc
    except requests.Timeout as exc:
        raise BrainError(f"Ollama did not reply within {timeout} seconds.") from exc

    if response.status_code == 404:
        raise BrainError(
            f"Model '{model}' was not found. Check `ollama list`, "
            f"or download it with `ollama pull {model}`."
        )
    if not response.ok:
        raise BrainError(f"Ollama returned HTTP {response.status_code}: {response.text[:200]}")

    try:
        reply = response.json()["message"]["content"].strip()
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise BrainError("Ollama sent a reply in an unexpected format.") from exc

    if not reply:
        raise BrainError("The model returned an empty reply.")
    return reply


if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) or "Introduce yourself in one sentence."
    try:
        print(generate_response(prompt))
    except BrainError as err:
        print(f"PARKER error: {err}", file=sys.stderr)
        sys.exit(1)
