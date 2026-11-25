"""Tests for backend.assistant, using a fake brain instead of Qwen."""

import pytest

from backend.assistant import Assistant
from backend.brain import BrainError


class FakeBrain:
    """Records what it was sent and replies 'reply 1', 'reply 2', ..."""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def __call__(self, message, history, facts=None):
        self.calls.append((message, history))
        self.facts = facts
        if self.fail:
            raise BrainError("offline")
        return f"reply {len(self.calls)}"


def test_ask_returns_brain_reply():
    assert Assistant(generate=FakeBrain()).ask("Hello") == "reply 1"


def test_earlier_turns_are_sent_with_each_new_message():
    fake = FakeBrain()
    a = Assistant(generate=fake)
    a.ask("My name is Raunak.")
    a.ask("What is my name?")
    message, history = fake.calls[1]
    assert message == "What is my name?"
    assert history == [
        {"role": "user", "content": "My name is Raunak."},
        {"role": "assistant", "content": "reply 1"},
    ]


def test_brain_receives_a_copy_of_history():
    fake = FakeBrain()
    a = Assistant(generate=fake)
    a.ask("one")
    a.ask("two")
    assert fake.calls[0][1] == []  # not mutated by the later append


def test_failed_message_is_not_remembered():
    a = Assistant(generate=FakeBrain(fail=True))
    with pytest.raises(BrainError):
        a.ask("Hello")
    assert a.history == []


def test_history_is_trimmed_to_max_turns():
    a = Assistant(generate=FakeBrain(), max_turns=2)
    for word in ["a", "b", "c"]:
        a.ask(word)
    assert [m["content"] for m in a.history] == ["b", "reply 2", "c", "reply 3"]


def test_reset_forgets_everything():
    a = Assistant(generate=FakeBrain())
    a.ask("Hello")
    a.reset()
    assert a.history == []


def test_max_turns_must_be_positive():
    with pytest.raises(ValueError):
        Assistant(generate=FakeBrain(), max_turns=0)


def test_saved_memories_are_sent_with_every_message():
    from backend.memory import Memory

    memory = Memory(":memory:")
    memory.add("My favourite colour is blue")
    fake = FakeBrain()
    Assistant(generate=fake, memory=memory).ask("What's my favourite colour?")
    assert fake.facts == ["My favourite colour is blue"]


def test_no_memory_means_no_facts():
    fake = FakeBrain()
    Assistant(generate=fake).ask("Hello")
    assert fake.facts == []
