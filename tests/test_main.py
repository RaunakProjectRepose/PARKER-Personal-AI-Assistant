"""Tests for the terminal chat loop, with scripted input and a fake brain."""

from backend.assistant import Assistant
from backend.brain import BrainError
from backend.main import run


def chat(lines, generate=lambda message, history: f"echo: {message}", speak_fn=None):
    """Run the loop with scripted input; return (printed lines, assistant)."""
    inputs = iter(lines)

    def fake_input(_prompt):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    out = []
    assistant = Assistant(generate=generate)
    run(
        assistant,
        input_fn=fake_input,
        print_fn=lambda *a: out.append(" ".join(map(str, a))),
        speak_fn=speak_fn,
    )
    return out, assistant


def test_replies_are_printed():
    out, _ = chat(["Hello", "/quit"])
    assert "PARKER: echo: Hello\n" in out
    assert out[-1] == "PARKER: Goodbye."


def test_blank_lines_are_ignored():
    out, a = chat(["", "   ", "/quit"])
    assert a.history == []


def test_reset_command_clears_history():
    out, a = chat(["Hello", "/reset", "/quit"])
    assert a.history == []
    assert "PARKER: Conversation cleared.\n" in out


def test_end_of_input_exits_cleanly():
    out, _ = chat(["Hello"])  # then EOFError, like Ctrl+Z / Ctrl+D
    assert out[-1] == "\nPARKER: Goodbye."


def test_brain_error_is_shown_and_loop_continues():
    def flaky(message, history):
        if message == "bad":
            raise BrainError("Ollama is not running")
        return "fine"

    out, _ = chat(["bad", "good", "/quit"], generate=flaky)
    assert "[error] Ollama is not running\n" in out
    assert "PARKER: fine\n" in out


def test_replies_are_spoken_when_voice_is_on():
    spoken = []
    out, _ = chat(["Hello", "/reset", "/quit"], speak_fn=spoken.append)
    assert spoken == ["echo: Hello"]  # only real replies, not command messages
    assert "Voice is on." in out[0]


def test_voice_failure_does_not_end_the_chat():
    def broken_speaker(text):
        raise RuntimeError("speakers unplugged")

    out, a = chat(["one", "two", "/quit"], speak_fn=broken_speaker)
    assert out.count("[voice error] speakers unplugged\n") == 2
    assert len(a.history) == 4
