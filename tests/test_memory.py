"""Tests for backend.memory: the SQLite fact store and "remember that" parsing."""

import pytest

from backend.memory import MAX_FACT_LENGTH, Memory, MemoryStoreError, parse_remember_request


@pytest.fixture
def memory(tmp_path):
    m = Memory(tmp_path / "parker.db")
    yield m
    m.close()


# ---- storing facts ----------------------------------------------------------

def test_add_and_list(memory):
    fact, created = memory.add("  My favourite   colour is blue ")
    assert created
    assert fact.text == "My favourite colour is blue"
    assert [f.text for f in memory.all()] == ["My favourite colour is blue"]


def test_memories_survive_a_restart(tmp_path):
    path = tmp_path / "parker.db"
    first = Memory(path)
    first.add("My name is Raunak")
    first.close()
    second = Memory(path)
    assert [f.text for f in second.all()] == ["My name is Raunak"]
    second.close()


def test_database_folder_is_created(tmp_path):
    m = Memory(tmp_path / "new" / "folder" / "parker.db")
    m.add("x")
    assert (tmp_path / "new" / "folder" / "parker.db").exists()
    m.close()


def test_duplicates_are_not_stored_twice(memory):
    memory.add("I like cricket")
    fact, created = memory.add("i like CRICKET")
    assert not created
    assert len(memory.all()) == 1


def test_update(memory):
    fact, _ = memory.add("I live in Mumbai")
    assert memory.update(fact.id, "I live in Pune")
    assert memory.all()[0].text == "I live in Pune"
    assert not memory.update(999, "nothing")


def test_delete(memory):
    a, _ = memory.add("one")
    b, _ = memory.add("two")
    assert memory.delete(a.id)
    assert [f.text for f in memory.all()] == ["two"]
    assert not memory.delete(a.id)


def test_clear(memory):
    memory.add("one")
    memory.add("two")
    assert memory.clear() == 2
    assert memory.all() == []


@pytest.mark.parametrize("bad", ["", "   ", "x" * (MAX_FACT_LENGTH + 1)])
def test_empty_or_huge_facts_are_rejected(memory, bad):
    with pytest.raises(MemoryStoreError):
        memory.add(bad)


def test_texts_returns_most_recent_facts_oldest_first(memory):
    for i in range(5):
        memory.add(f"fact {i}")
    assert memory.texts(limit=3) == ["fact 2", "fact 3", "fact 4"]


# ---- understanding "remember that ..." --------------------------------------

@pytest.mark.parametrize(
    "message, fact",
    [
        ("Remember that my favourite colour is blue.", "my favourite colour is blue"),
        ("remember my birthday is 4 March", "my birthday is 4 March"),
        ("Please remember that I'm vegetarian!", "I'm vegetarian"),
        ("Parker, remember I prefer tea", "I prefer tea"),
        ("Hey Parker remember that I study at night", "I study at night"),
        # Phrasings from the first laptop test (Whisper adds punctuation):
        ("My favorite color is blue, do remember that.", "My favorite color is blue"),
        ("Remember, my favorite color is blue.", "my favorite color is blue"),
        ("Can you remember that I study at night", "I study at night"),
        ("Don't forget that I'm allergic to nuts", "I'm allergic to nuts"),
        ("I live in Pune, remember this", "I live in Pune"),
        ("I'm vegetarian. Please remember that", "I'm vegetarian"),
        ("Make a note that my exam is on Friday", "my exam is on Friday"),
        ("My dog is called Max. Remember that, Parker.", "My dog is called Max"),
    ],
)
def test_remember_requests_are_understood(message, fact):
    assert parse_remember_request(message) == fact


@pytest.mark.parametrize(
    "message",
    [
        "Do you remember my name?",
        "Remember what I told you?",
        "remember when we talked about Python",
        "remember to buy milk",
        "I can't remember the password",
        "What's the weather like?",
        "remember",
        "I need to remember my keys",
        "Help me remember",
        "Can you remember things",
        "Note that",
        "Remember me",
        "I want you to remember",
        "That is hard to remember",
    ],
)
def test_other_messages_are_not_remember_requests(message):
    assert parse_remember_request(message) is None
