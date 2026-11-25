"""Tests for the terminal chat loop, with scripted input and a fake brain."""

from backend.assistant import Assistant
from backend.brain import BrainError
from backend.main import run


def chat(lines, generate=lambda message, history, **kw: f"echo: {message}", speak_fn=None, listen_fn=None):
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
        listen_fn=listen_fn,
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
    assert "PARKER: Conversation cleared. Saved memories are kept.\n" in out


def test_end_of_input_exits_cleanly():
    out, _ = chat(["Hello"])  # then EOFError, like Ctrl+Z / Ctrl+D
    assert out[-1] == "\nPARKER: Goodbye."


def test_brain_error_is_shown_and_loop_continues():
    def flaky(message, history, **kw):
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


def test_empty_line_starts_listening_when_microphone_is_on():
    out, a = chat(["", "/quit"], listen_fn=lambda: "What time is it?")
    assert "You (spoken): What time is it?" in out
    assert "PARKER: echo: What time is it?\n" in out


def test_nothing_heard_is_reported_and_not_sent_to_the_brain():
    out, a = chat(["", "/quit"], listen_fn=lambda: "  ")
    assert "PARKER: Sorry, I didn't catch that.\n" in out
    assert a.history == []


def test_microphone_failure_does_not_end_the_chat():
    def broken_mic():
        raise RuntimeError("no microphone found")

    out, a = chat(["", "typed", "/quit"], listen_fn=broken_mic)
    assert "[microphone error] no microphone found\n" in out
    assert "PARKER: echo: typed\n" in out


def test_spoken_commands_work_too():
    out, a = chat([""], listen_fn=lambda: "/quit")
    assert out[-1] == "PARKER: Goodbye."


def test_empty_line_is_still_ignored_without_microphone():
    out, a = chat(["", "/quit"])
    assert a.history == []


# ---- memory commands --------------------------------------------------------

def memory_chat(lines, memory=None, speak_fn=None):
    from backend.memory import Memory

    memory = memory if memory is not None else Memory(":memory:")
    inputs = iter(lines)

    def fake_input(_prompt):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    out, sent = [], []

    def brain(message, history, facts=None):
        sent.append((message, facts))
        return "ok"

    run(
        Assistant(generate=brain, memory=memory),
        input_fn=fake_input,
        print_fn=lambda *a: out.append(" ".join(map(str, a))),
        speak_fn=speak_fn,
    )
    return out, memory, sent


def test_remember_that_saves_without_asking_the_model():
    spoken = []
    out, memory, sent = memory_chat(["Remember that my favourite colour is blue."], speak_fn=spoken.append)
    assert [f.text for f in memory.all()] == ["my favourite colour is blue"]
    assert sent == []
    assert spoken == ["Noted. I'll remember that: my favourite colour is blue"]


def test_remember_command_and_saved_facts_reach_the_model():
    out, memory, sent = memory_chat(["/remember I live in Pune", "Where do I live?"])
    assert sent == [("Where do I live?", ["I live in Pune"])]


def test_memories_lists_ids_and_text():
    out, memory, _ = memory_chat(["/remember one", "/remember two", "/memories"])
    assert "PARKER: Here's what I remember:\n  [1] one\n  [2] two\n" in out


def test_forget_and_edit_by_id():
    out, memory, _ = memory_chat(["/remember one", "/remember two", "/forget 1", "/edit 2 three"])
    assert [f.text for f in memory.all()] == ["three"]


def test_forget_unknown_id_is_reported():
    out, _, _ = memory_chat(["/forget 42"])
    assert "PARKER: There's no memory with id 42.\n" in out


def test_forget_all_needs_a_yes():
    out, memory, _ = memory_chat(["/remember one", "/forget all", "no"])
    assert len(memory.all()) == 1
    out, memory, _ = memory_chat(["/remember one", "/forget all", "yes"])
    assert memory.all() == []


def test_reset_keeps_saved_memories():
    out, memory, _ = memory_chat(["/remember one", "/reset"])
    assert len(memory.all()) == 1


def test_startup_shows_memory_count():
    from backend.memory import Memory

    m = Memory(":memory:")
    m.add("one")
    out, _, _ = memory_chat([], memory=m)
    assert "1 saved memory." in out[0]


def test_memory_commands_without_a_memory_store():
    out, _ = chat(["/memories", "/quit"])
    assert "PARKER: Sorry, my long-term memory isn't available right now.\n" in out


def test_ordinary_messages_still_go_to_the_model():
    out, memory, sent = memory_chat(["Do you remember my name?"])
    assert sent == [("Do you remember my name?", [])]



def test_unknown_commands_are_not_sent_to_the_model():
    out, memory, sent = memory_chat(["/memory"])
    assert sent == []
    assert "Unknown command /memory. Type /help for commands.\n" in out


def test_fact_first_remember_request_from_laptop_test():
    out, memory, sent = memory_chat(["My favorite color is blue, do remember that."])
    assert [f.text for f in memory.all()] == ["My favorite color is blue"]
    assert sent == []
