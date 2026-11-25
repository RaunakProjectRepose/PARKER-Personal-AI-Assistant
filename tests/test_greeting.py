"""Tests for PARKER's startup greeting."""

from datetime import date, datetime

import pytest

from backend.agenda import Event, Plan
from backend.greeting import build_greeting, time_of_day

DAY = date(2026, 11, 25)


@pytest.mark.parametrize(
    "hour, expected",
    [(5, "morning"), (11, "morning"), (12, "afternoon"), (16, "afternoon"), (17, "evening"), (2, "evening")],
)
def test_time_of_day(hour, expected):
    assert time_of_day(datetime(2026, 11, 25, hour)) == expected


def test_greeting_with_plans_and_events():
    text = build_greeting(
        "Raunak",
        [Plan(1, "refine the personality"), Plan(2, "start the desktop app")],
        [Event(1, DAY, None, "Assignment due"), Event(2, DAY, "18:00", "Gym")],
        datetime(2026, 11, 25, 19, 30),
    )
    assert text == (
        "Good evening, Raunak. "
        "Planned for this session: refine the personality and start the desktop app. "
        "Today: Assignment due and Gym at 18:00. "
        "Let's make it a good one."
    )


def test_greeting_with_nothing_planned():
    text = build_greeting("Raunak", [], [], datetime(2026, 11, 25, 9))
    assert text == "Good morning, Raunak. Nothing's planned yet, so what shall we tackle today?"


def test_three_items_are_listed_naturally():
    plans = [Plan(i, t) for i, t in enumerate(["a", "b", "c"])]
    assert "Planned for this session: a, b and c." in build_greeting("R", plans, [], datetime(2026, 1, 1, 13))
