"""PARKER terminal chat: the first end-to-end way to talk to PARKER.

Run from the project folder (with Ollama running):

    python -m backend.main

Commands:  /reset  forget the conversation    /quit  leave (or Ctrl+C)
"""

from __future__ import annotations

from backend.assistant import Assistant
from backend.brain import MODEL, BrainError

QUIT_COMMANDS = {"/quit", "/exit", "quit", "exit"}
RESET_COMMAND = "/reset"


def run(assistant: Assistant | None = None, input_fn=input, print_fn=print) -> None:
    """Read messages, print PARKER's replies, until the user quits."""
    assistant = assistant or Assistant()
    print_fn(f"PARKER is online (model: {MODEL}). Type /reset to start over, /quit to leave.\n")

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
        print_fn(f"PARKER: {reply}\n")


if __name__ == "__main__":
    run()
