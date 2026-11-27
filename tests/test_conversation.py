"""Tests for backend.conversation: when a hands-free conversation should end."""

import pytest

from backend.conversation import ending, farewell


@pytest.mark.parametrize("said, kind", [
    ("Thanks.", "thanks"),
    ("Thank you, Parker!", "thanks"),
    ("Okay, thanks, that's all.", "thanks"),
    ("That's all.", "goodbye"),
    ("That’s it for now.", "goodbye"),
    ("Stop.", "goodbye"),
    ("Never mind.", "goodbye"),
    ("No, that's all.", "goodbye"),
    ("Bye Parker.", "goodbye"),
    ("Good night.", "goodnight"),
    ("Goodnight, Parker.", "goodnight"),
])
def test_clear_sign_offs_end_the_conversation(said, kind):
    assert ending(said) == kind


@pytest.mark.parametrize("said", [
    "Stop the timer.",
    "Thanks for the help with my notes, what's next?",
    "Remind me to say thank you to Sam.",
    "What did I say that's all about?",
    "No.",
    "Tell me a joke.",
    "",
])
def test_ordinary_messages_keep_the_conversation_going(said):
    assert ending(said) is None


def test_farewells_use_the_owners_name():
    assert farewell("thanks", "Raunak") == "Anytime, Raunak."
    assert farewell("goodnight", "Raunak").startswith("Good night, Raunak.")
    assert farewell("goodbye", "Raunak") == "Alright, Raunak. I'm here when you need me."
