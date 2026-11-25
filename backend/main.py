"""PARKER terminal chat: the first end-to-end way to talk to PARKER.

Run from the project folder (with Ollama running):

    python -m backend.main            # text replies
    python -m backend.main --speak    # text replies, also spoken aloud

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
) -> None:
    """Read messages, print (and optionally speak) PARKER's replies, until the user quits.

    `speak_fn`, if given, is called with each reply's text and should say it aloud.
    """
    assistant = assistant or Assistant()
    voice_note = " Voice is on." if speak_fn else ""
    print_fn(
        f"PARKER is online (model: {MODEL}).{voice_note} "
        "Type /reset to start over, /quit to leave.\n"
    )

    while True:
        try:
            message = input_fn("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print_fn("\nPARKER: Goodbye.")
            return

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
    args = parser.parse_args(argv)

    speak_fn = None
    if args.speak:
        from backend.speech_output import Speaker, SpeechError

        try:
            speak_fn = Speaker().speak
        except SpeechError as err:
            print(f"[voice error] {err}\nContinuing with text only.\n")

    run(speak_fn=speak_fn)


if __name__ == "__main__":
    main()
