"""PARKER terminal chat: the first end-to-end way to talk to PARKER.

Run from the project folder (with Ollama running):

    python -m backend.main            # text replies
    python -m backend.main --speak    # text replies, also spoken aloud
    python -m backend.main --listen   # press Enter on an empty line to talk
    python -m backend.main --voice    # both: a full spoken conversation

Commands:  /reset  forget the conversation    /quit  leave (or Ctrl+C)
"""

from __future__ import annotations

import argparse

from backend.assistant import Assistant
from backend.brain import MODEL, BrainError

QUIT_COMMANDS = {"/quit", "/exit", "quit", "exit"}
RESET_COMMAND = "/reset"


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
    notes = []
    if speak_fn:
        notes.append("Voice is on.")
    if listen_fn:
        notes.append("Press Enter on an empty line to talk.")
    note = (" " + " ".join(notes)) if notes else ""
    print_fn(
        f"PARKER is online (model: {MODEL}).{note} "
        "Type /reset to start over, /quit to leave.\n"
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
            print_fn("PARKER: Conversation cleared.\n")
            continue

        try:
            reply = assistant.ask(message)
        except BrainError as err:
            print_fn(f"[error] {err}\n")
            continue
        # Print first so the text appears immediately, then speak it.
        print_fn(f"PARKER: {reply}\n")
        if speak_fn:
            try:
                speak_fn(reply)
            except Exception as err:  # A voice problem must never end the chat.
                print_fn(f"[voice error] {err}\n")


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

    run(speak_fn=speak_fn, listen_fn=listen_fn)


if __name__ == "__main__":
    main()
