"""Tests for backend.agenda: plans, events and date parsing."""

from datetime import date

import pytest

from backend.agenda import Agenda, AgendaError, Event, parse_day, parse_event

WED = date(2026, 11, 25)  # a Wednesday


@pytest.fixture
def agenda():
    a = Agenda(":memory:")
    yield a
    a.close()


# ---- dates ------------------------------------------------------------------

@pytest.mark.parametrize(
    "word, expected",
    [
        ("today", WED),
        ("Tomorrow", date(2026, 11, 26)),
        ("friday", date(2026, 11, 27)),
        ("wednesday", date(2026, 12, 2)),  # same weekday means next week
        ("2026-12-03", date(2026, 12, 3)),
        ("3/12", date(2026, 12, 3)),  # day/month
        ("3-1", date(2027, 1, 3)),  # already past this year, so next year
        ("3/1/2026", date(2026, 1, 3)),
    ],
)
def test_parse_day(word, expected):
    assert parse_day(word, WED) == expected


@pytest.mark.parametrize("bad", ["someday", "31/2", "2026-13-01"])
def test_bad_dates_are_rejected(bad):
    with pytest.raises(AgendaError):
        parse_day(bad, WED)


def test_parse_event_with_time():
    assert parse_event("today 18:00 Gym session", WED) == (WED, "18:00", "Gym session")


def test_parse_event_with_short_time_and_dot():
    assert parse_event("tomorrow 9.30 Lecture", WED) == (date(2026, 11, 26), "09:30", "Lecture")


def test_parse_event_all_day():
    assert parse_event("friday Hackathon", WED) == (date(2026, 11, 27), None, "Hackathon")


@pytest.mark.parametrize("bad", ["", "today", "today 18:00"])
def test_incomplete_events_are_rejected(bad):
    with pytest.raises(AgendaError):
        parse_event(bad, WED)


# ---- storage ----------------------------------------------------------------

def test_plans_can_be_added_and_completed(agenda):
    a = agenda.add_plan("Build the desktop UI")
    agenda.add_plan("Write tests")
    assert agenda.complete_plan(a.id)
    assert [p.text for p in agenda.open_plans()] == ["Write tests"]
    assert not agenda.complete_plan(a.id)  # already done


def test_plans_and_events_survive_a_restart(tmp_path):
    path = tmp_path / "parker.db"
    first = Agenda(path)
    first.add_plan("Refine personality")
    first.add_event(WED, "18:00", "Gym")
    first.close()
    second = Agenda(path)
    assert [p.text for p in second.open_plans()] == ["Refine personality"]
    assert [e.text for e in second.events_on(WED)] == ["Gym"]
    second.close()


def test_events_are_ordered_all_day_first_then_by_time(agenda):
    agenda.add_event(WED, "18:00", "Gym")
    agenda.add_event(WED, "09:00", "Lecture")
    agenda.add_event(WED, None, "Assignment due")
    agenda.add_event(date(2026, 11, 26), "08:00", "Tomorrow thing")
    assert [e.text for e in agenda.events_on(WED)] == ["Assignment due", "Lecture", "Gym"]


def test_events_between_and_delete(agenda):
    e = agenda.add_event(WED, None, "One")
    agenda.add_event(date(2026, 12, 10), None, "Far away")
    assert [x.text for x in agenda.events_between(WED, date(2026, 12, 2))] == ["One"]
    assert agenda.delete_event(e.id)
    assert not agenda.delete_event(e.id)


def test_memory_and_agenda_share_one_database(tmp_path):
    from backend.memory import Memory

    path = tmp_path / "parker.db"
    m, a = Memory(path), Agenda(path)
    m.add("I like tea")
    a.add_plan("Plan something")
    assert len(m.all()) == 1 and len(a.open_plans()) == 1
    m.close()
    a.close()


@pytest.mark.parametrize("bad", ["", "   ", "x" * 201])
def test_empty_or_huge_text_is_rejected(agenda, bad):
    with pytest.raises(AgendaError):
        agenda.add_plan(bad)


def test_event_description():
    assert Event(1, WED, "18:00", "Gym").describe(WED) == "Gym (today at 18:00)"
    assert Event(1, date(2026, 11, 26), None, "Exam").describe(WED) == "Exam (tomorrow)"
    assert Event(1, date(2026, 11, 30), None, "Trip").describe(WED) == "Trip (Mon 30 Nov)"



@pytest.mark.parametrize("text, expected", [("18:00", "18:00"), ("9.30", "09:30"), ("", None), ("  ", None)])
def test_parse_time(text, expected):
    from backend.agenda import parse_time

    assert parse_time(text) == expected


@pytest.mark.parametrize("bad", ["25:99", "6pm", "18"])
def test_bad_times_are_rejected(bad):
    from backend.agenda import parse_time

    with pytest.raises(AgendaError, match="valid time"):
        parse_time(bad)
