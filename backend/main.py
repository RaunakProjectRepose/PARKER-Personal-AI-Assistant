"""PARKER terminal chat: the first end-to-end way to talk to PARKER.

Run from the project folder (with Ollama running):

    python -m backend.main            # text replies
    python -m backend.main --speak    # text replies, also spoken aloud
    python -m backend.main --listen   # press Enter on an empty line to talk
    python -m backend.main --voice    # both: a full spoken conversation

Type /help in the chat for the list of commands.
"""

from __future__ import annotations

import argparse

from backend.assistant import Assistant
from backend.brain import MODEL, BrainError
from backend.memory import Memory, MemoryStoreError, parse_remember_request

QUIT_COMMANDS = {"/quit", "/exit", "quit", "exit"}
RESET_COMMAND = "/reset"

HELP_TEXT = """Commands:
  /remember <fact>     save something about you (or say "remember that ...")
  /memories            list everything PARKER remembers
  /edit <id> <fact>    change a saved memory
  /forget <id>         delete one memory
  /forget all          delete every memory (asks first)
  /reset               forget this conversation (saved memories stay)
  /quit                leave
"""


def handle_memory(message: str, memory: Memory | None, say, print_fn, input_fn) -> bool:
    """Handle memory commands and "remember that ..." requests.

    Returns True if the message was dealt with here (so it is not sent to the
    model). `say` prints a PARKER reply and speaks it when voice is on.
    """
    lowered = message.lower()
    command, _, rest = message.partition(" ")
    command = command.lower()
    rest = rest.strip()

    natural_fact = parse_remember_request(message)
    is_memory_command = command in {"/remember", "/memories", "/forget", "/edit"}
    if not (is_memory_command or natural_fact):
        return False
    if memory is None:
        say("Sorry, my long-term memory isn't available right now.")
        return True

    try:
        if command == "/remember" or natural_fact:
            fact_text = rest if command == "/remember" else natural_fact
            if not fact_text:
                print_fn("Usage: /remember <fact>\n")
                return True
            fact, created = memory.add(fact_text)
            if created:
                say(f"Noted. I'll remember that: {fact.text}")
            else:
                say(f"I already remember that: {fact.text}")

        elif lowered == "/memories":
            facts = memory.all()
            if not facts:
                print_fn("PARKER: I don't have any saved memories yet.\n")
            else:
                lines = "\n".join(f"  [{f.id}] {f.text}" for f in facts)
                print_fn(f"PARKER: Here's what I remember:\n{lines}\n")

        elif command == "/forget" and rest.lower() == "all":
            count = len(memory.all())
            if count == 0:
                print_fn("PARKER: There's nothing to forget.\n")
                return True
            what = "your 1 memory" if count == 1 else f"all {count} memories"
            answer = input_fn(f"Delete {what}? This can't be undone. Type yes: ")
            if answer.strip().lower() == "yes":
                memory.clear()
                say("Done. I've forgotten everything you asked me to remember.")
            else:
                print_fn("PARKER: Cancelled. Your memories are safe.\n")

        elif command == "/forget":
            if not rest.isdigit():
                print_fn("Usage: /forget <id>   (see /memories for ids)\n")
            elif memory.delete(int(rest)):
                say("Forgotten.")
            else:
                print_fn(f"PARKER: There's no memory with id {rest}.\n")

        elif command == "/edit":
            fact_id, _, new_text = rest.partition(" ")
            if not fact_id.isdigit() or not new_text.strip():
                print_fn("Usage: /edit <id> <new fact>\n")
            elif memory.update(int(fact_id), new_text):
                say(f"Updated. I'll remember that: {' '.join(new_text.split())}")
            else:
                print_fn(f"PARKER: There's no memory with id {fact_id}.\n")

        else:  # e.g. "/memories extra words"
            print_fn(HELP_TEXT)
    except MemoryStoreError as err:
        print_fn(f"PARKER: {err}\n")
    return True


def run(
    assistant: Assistant | None = None,
    input_fn=input,
    print_fn=print,
    speak_fn=None,
    listen_fn=None,
) -> None:
    """Read messages, print (and optionally speak) PARKER's replies, until the user quits.

    `speak_fn`, if given, is called with each reply's text and should say it aloud.
    `listen_fn`, if given, is called when the user presses Enter on an empty
    line; it records speech and returns it as text.
    """
    assistant = assistant or Assistant()

    def say(text: str) -> None:
        # Print first so the text appears immediately, then speak it.
        print_fn(f"PARKER: {text}\n")
        if speak_fn:
            try:
                speak_fn(text)
            except Exception as err:  # A voice problem must never end the chat.
                print_fn(f"[voice error] {err}\n")

    notes = []
    if speak_fn:
        notes.append("Voice is on.")
    if listen_fn:
        notes.append("Press Enter on an empty line to talk.")
    if assistant.memory is not None:
        count = len(assistant.memory.all())
        notes.append(f"{count} saved {'memory' if count == 1 else 'memories'}.")
    note = (" " + " ".join(notes)) if notes else ""
    print_fn(
        f"PARKER is online (model: {MODEL}).{note} "
        "Type /help for commands, /quit to leave.\n"
    )

    while True:
        try:
            message = input_fn("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print_fn("\nPARKER: Goodbye.")
            return

        if not message and listen_fn:
            try:
                message = listen_fn().strip()
            except KeyboardInterrupt:
                print_fn("\nPARKER: Goodbye.")
                return
            except Exception as err:  # A microphone problem must never end the chat.
                print_fn(f"[microphone error] {err}\n")
                continue
            if not message:
                print_fn("PARKER: Sorry, I didn't catch that.\n")
                continue
            print_fn(f"You (spoken): {message}")
        if not message:
            continue
        if message.lower() in QUIT_COMMANDS:
            print_fn("PARKER: Goodbye.")
            return
        if message.lower() == RESET_COMMAND:
            assistant.reset()
            print_fn("PARKER: Conversation cleared. Saved memories are kept.\n")
            continue
        if message.lower() == "/help":
            print_fn(HELP_TEXT)
            continue
        try:
            if handle_memory(message, assistant.memory, say, print_fn, input_fn):
                continue
        except (EOFError, KeyboardInterrupt):
            print_fn("\nPARKER: Goodbye.")
            return

        try:
            reply = assistant.ask(message)
        except BrainError as err:
            print_fn(f"[error] {err}\n")
            continue
        say(reply)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Chat with PARKER in the terminal.")
    parser.add_argument("--speak", action="store_true", help="speak PARKER's replies aloud")
    parser.add_argument("--listen", action="store_true", help="talk to PARKER with your microphone")
    parser.add_argument("--voice", action="store_true", help="same as --speak --listen")
    args = parser.parse_args(argv)
    if args.voice:
        args.speak = args.listen = True

    speak_fn = None
    if args.speak:
        from backend.speech_output import Speaker, SpeechError

        try:
            speak_fn = Speaker().speak
        except SpeechError as err:
            print(f"[voice error] {err}\nContinuing with text only.\n")

    listen_fn = None
    if args.listen:
        from backend.speech_input import Listener, SpeechInputError

        print("Loading speech recognition (the first run downloads ~480 MB)...")
        try:
            listen_fn = Listener().listen
        except SpeechInputError as err:
            print(f"[microphone error] {err}\nContinuing with typing only.\n")

    memory = None
    try:
        memory = Memory()
    except Exception as err:  # e.g. a locked or unreadable database file
        print(f"[memory error] {err}\nContinuing without saved memories.\n")

    try:
        run(Assistant(memory=memory), speak_fn=speak_fn, listen_fn=listen_fn)
    finally:
        if memory is not None:
            memory.close()


if __name__ == "__main__":
    main()
