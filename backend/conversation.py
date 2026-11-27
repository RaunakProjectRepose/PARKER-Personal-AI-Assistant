"""Hands-free conversation: knowing when the owner is finished talking to PARKER.

In hands-free mode PARKER listens again after every reply.  The conversation
ends when nobody speaks for a few seconds, when the owner presses Esc, or when
they say something that clearly means "that's all" -- checked here, in code,
so "stop the timer" or "thanks for the help with X" still reach PARKER.
"""

from __future__ import annotations

import re

THANKS = {
    "thanks", "thank you", "thanks a lot", "thank you so much", "cheers", "ta",
    "thanks thats all", "thank you thats all", "thats all thanks", "thats all thank you",
    "thats it thanks", "thats it thank you", "great thanks", "perfect thanks",
}
GOODNIGHT = {"good night", "goodnight", "night"}
GOODBYE = {
    "stop", "stop listening", "thats all", "that is all", "thats it", "that is it",
    "that will be all", "thatll be all", "goodbye", "bye", "bye bye", "see you",
    "see you later", "see ya", "later", "never mind", "nevermind", "nothing",
    "nothing else", "no thanks", "no thank you", "cancel", "im done", "i am done",
    "all done", "were done", "we are done", "go to sleep", "sleep", "dismiss",
}
FILLERS = ("okay ", "ok ", "alright ", "all right ", "right ", "um ", "uh ", "well ", "no ")


def _normalise(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^a-z' ]+", " ", text).replace("'", "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*\b(parker|for now|then)$", "", text).strip()
    changed = True
    while changed:
        changed = False
        for filler in FILLERS:
            if text.startswith(filler):
                text, changed = text[len(filler):].strip(), True
    return text


def ending(text: str) -> str | None:
    """Return "thanks", "goodnight" or "goodbye" if `text` ends the conversation."""
    said = _normalise(text)
    if said in THANKS:
        return "thanks"
    if said in GOODNIGHT:
        return "goodnight"
    if said in GOODBYE:
        return "goodbye"
    return None


def farewell(kind: str, owner: str) -> str:
    """PARKER's short sign-off; it then stops listening."""
    if kind == "thanks":
        return f"Anytime, {owner}."
    if kind == "goodnight":
        return f"Good night, {owner}. Rest well."
    return f"Alright, {owner}. I'm here when you need me."
