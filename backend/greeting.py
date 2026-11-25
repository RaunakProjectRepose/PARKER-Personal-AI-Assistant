"""PARKER's startup greeting, built from real data rather than by the model.

Example: "Good evening, Raunak. Planned for this session: finish the desktop
UI. Today: Gym at 18:00. Let's make it a good one."
"""

from __future__ import annotations

from datetime import datetime

from backend.agenda import Event, Plan


def time_of_day(now: datetime) -> str:
    if 5 <= now.hour < 12:
        return "morning"
    if 12 <= now.hour < 17:
        return "afternoon"
    return "evening"


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def build_greeting(name: str, plans: list[Plan], events: list[Event], now: datetime) -> str:
    parts = [f"Good {time_of_day(now)}, {name}."]
    if plans:
        parts.append(f"Planned for this session: {_join([p.text for p in plans])}.")
    if events:
        described = [f"{e.text} at {e.time}" if e.time else e.text for e in events]
        parts.append(f"Today: {_join(described)}.")
    if plans or events:
        parts.append("Let's make it a good one.")
    else:
        parts.append("Nothing's planned yet, so what shall we tackle today?")
    return " ".join(parts)
