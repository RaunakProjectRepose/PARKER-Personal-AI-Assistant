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
import time
from datetime import date, datetime, timedelta

from backend.agenda import Agenda, AgendaError, parse_event
from backend.apps import AppError, AppLauncher, parse_open_request
from backend.assistant import Assistant
from backend.brain import MODEL, OWNER_NAME, BrainError
from backend.greeting import build_greeting
from backend.memory import Memory, MemoryStoreError, parse_remember_request

QUIT_COMMANDS = {"/quit", "/exit", "quit", "exit"}
RESET_COMMAND = "/reset"

HELP_TEXT = """Commands:
  /remember <fact>     save something about you (or say "remember that ...")
  /memories            list everything PARKER remembers
  /edit <id> <fact>    change a saved memory
  /forget <id>         delete one memory
  /forget all          delete every memory (asks first)
  /plan <task>         add a task for the next session (read out at startup)
  /plans               list open plans
  /done <id>           mark a plan as done
  /event <day> [HH:MM] <what>   add an event, e.g. /event today 18:00 Gym
                       (day: today, tomorrow, friday, 2026-12-03 or 3/12)
  /events              list events for the next 7 days
  /cancel <id>         delete an event
  open <app or folder> e.g. "open VS Code", "open my Downloads" (typed or spoken)
  /apps [search]       list apps PARKER can open
  /app add <name> = <path or web address>   teach PARKER a new one
  /app remove <name>   forget one you added
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


def handle_apps(message: str, apps: AppLauncher | None, say, print_fn) -> bool:
    """Handle "open X" requests and the /apps and /app commands. True if handled.

    An "open X" request that matches nothing is NOT handled here, so it goes to
    the model as a normal message (it may not have been about an app at all).
    """
    command, _, rest = message.partition(" ")
    command = command.lower()
    rest = rest.strip()
    if command in ("/apps", "/app"):
        if apps is None:
            print_fn("PARKER: Opening apps isn't available right now.\n")
            return True
        sub, _, args = rest.partition(" ")
        try:
            if command == "/app" and sub.lower() == "add":
                name, sep, target = args.partition("=")
                if not sep:
                    raise AppError("Usage: /app add <name> = <path or web address>")
                entry = apps.add(name, target)
                say(f"Got it. Say \"open {entry.name}\" whenever you need it.")
            elif command == "/app" and sub.lower() == "remove":
                if apps.remove(args):
                    say(f"Removed {args.strip()}.")
                else:
                    print_fn(f"PARKER: You haven't added an app called '{args.strip()}'.\n")
            elif command == "/apps":
                if rest.lower() == "refresh":
                    apps.refresh()
                entries = apps.entries()
                if rest and rest.lower() != "refresh":
                    entries = [e for e in entries if rest.lower() in e.name.lower()]
                names = sorted({e.name for e in entries}, key=str.lower)
                if not names:
                    print_fn(f"PARKER: Nothing matches '{rest}'.\n")
                else:
                    shown = ", ".join(names[:60]) + (f" … and {len(names) - 60} more" if len(names) > 60 else "")
                    print_fn(f"PARKER: I can open: {shown}\n")
            else:
                print_fn("Usage: /app add <name> = <path>  ·  /app remove <name>  ·  /apps [search]\n")
        except AppError as err:
            print_fn(f"PARKER: {err}\n")
        return True

    spoken = parse_open_request(message)
    if not spoken or apps is None:
        return False
    if apps.find(spoken) is None:
        return False  # let the model answer; it may not have been about an app
    try:
        entry = apps.open(spoken)
    except AppError as err:
        print_fn(f"PARKER: {err}\n")
        return True
    say(f"Opening {entry.name}.")
    return True


def handle_agenda(message: str, agenda: Agenda | None, say, print_fn, today: date) -> bool:
    """Handle /plan, /plans, /done, /event, /events and /cancel. True if handled."""
    command, _, rest = message.partition(" ")
    command = command.lower()
    rest = rest.strip()
    if command not in {"/plan", "/plans", "/done", "/event", "/events", "/cancel"}:
        return False
    if agenda is None:
        say("Sorry, my agenda isn't available right now.")
        return True

    try:
        if command == "/plan":
            if not rest:
                print_fn("Usage: /plan <task>\n")
            else:
                plan = agenda.add_plan(rest)
                say(f"Added to the plan for next session: {plan.text}")
        elif command == "/plans":
            plans = agenda.open_plans()
            if not plans:
                print_fn("PARKER: No open plans. Add one with /plan <task>.\n")
            else:
                lines = "\n".join(f"  [{p.id}] {p.text}" for p in plans)
                print_fn(f"PARKER: Open plans:\n{lines}\n")
        elif command == "/done":
            if not rest.isdigit():
                print_fn("Usage: /done <id>   (see /plans for ids)\n")
            elif agenda.complete_plan(int(rest)):
                say("Nicely done. That's ticked off.")
            else:
                print_fn(f"PARKER: There's no open plan with id {rest}.\n")
        elif command == "/event":
            day, time, text = parse_event(rest, today)
            event = agenda.add_event(day, time, text)
            say(f"Added: {event.describe(today)}.")
        elif command == "/events":
            events = agenda.events_between(today, today + timedelta(days=7))
            if not events:
                print_fn("PARKER: Nothing in the next 7 days.\n")
            else:
                lines = "\n".join(f"  [{e.id}] {e.describe(today)}" for e in events)
                print_fn(f"PARKER: Coming up:\n{lines}\n")
        elif command == "/cancel":
            if not rest.isdigit():
                print_fn("Usage: /cancel <id>   (see /events for ids)\n")
            elif agenda.delete_event(int(rest)):
                say("Event removed.")
            else:
                print_fn(f"PARKER: There's no event with id {rest}.\n")
    except AgendaError as err:
        print_fn(f"PARKER: {err}\n")
    return True


def run(
    assistant: Assistant | None = None,
    input_fn=input,
    print_fn=print,
    speak_fn=None,
    listen_fn=None,
    now=datetime.now,
    timing_fn=None,
    apps: AppLauncher | None = None,
) -> None:
    """Read messages, print (and optionally speak) PARKER's replies, until the user quits.

    `speak_fn`, if given, is called with each reply's text and should say it aloud.
    `listen_fn`, if given, is called when the user presses Enter on an empty
    line; it records speech and returns it as text.
    `timing_fn`, if given, is called with how long thinking and speaking took.
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
    agenda = assistant.agenda
    if agenda is not None:
        today = now().date()
        say(build_greeting(OWNER_NAME, agenda.open_plans(), agenda.events_on(today), now()))

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
            if handle_agenda(message, assistant.agenda, say, print_fn, now().date()):
                continue
            if handle_apps(message, apps, say, print_fn):
                continue
        except (EOFError, KeyboardInterrupt):
            print_fn("\nPARKER: Goodbye.")
            return
        if message.startswith("/"):
            # A mistyped command like "/memory" must not be sent to the model.
            print_fn(f"Unknown command {message.split()[0]}. Type /help for commands.\n")
            continue

        started = time.monotonic()
        try:
            reply = assistant.ask(message)
        except BrainError as err:
            print_fn(f"[error] {err}\n")
            continue
        thought = time.monotonic() - started
        say(reply)
        if timing_fn:
            timing_fn(thought, time.monotonic() - started - thought)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Chat with PARKER in the terminal.")
    parser.add_argument("--speak", action="store_true", help="speak PARKER's replies aloud")
    parser.add_argument("--listen", action="store_true", help="talk to PARKER with your microphone")
    parser.add_argument("--voice", action="store_true", help="same as --speak --listen")
    parser.add_argument("--timing", action="store_true", help="show how long each step takes")
    args = parser.parse_args(argv)
    if args.voice:
        args.speak = args.listen = True

    speak_fn = speaker = None
    if args.speak:
        from backend.speech_output import Speaker, SpeechError

        try:
            speaker = Speaker()
            speak_fn = speaker.speak
            if speaker.fallback_note:
                print(f"[voice] {speaker.fallback_note}")
        except SpeechError as err:
            print(f"[voice error] {err}\nContinuing with text only.\n")

    timing_fn = None
    if args.timing:

        def timing_fn(thought: float, spoke: float) -> None:
            parts = [f"thinking {thought:.1f} s"]
            if speaker is not None and speaker.last_first_audio_s is not None:
                parts.append(f"voice ready {speaker.last_first_audio_s:.1f} s")
                parts.append(f"speaking {spoke:.1f} s")
            print(f"[timing] {' · '.join(parts)}\n")

    listen_fn = None
    if args.listen:
        from backend.speech_input import Listener, SpeechInputError

        print("Loading speech recognition (the first run downloads ~480 MB)...")
        try:
            listen_fn = Listener().listen
        except SpeechInputError as err:
            print(f"[microphone error] {err}\nContinuing with typing only.\n")

    memory = agenda = None
    try:
        memory = Memory()
        agenda = Agenda()
    except Exception as err:  # e.g. a locked or unreadable database file
        print(f"[memory error] {err}\nContinuing without saved memories or agenda.\n")
    apps = None
    try:
        apps = AppLauncher()
    except Exception as err:
        print(f"[apps error] {err}\nContinuing without opening apps.\n")

    try:
        run(
            Assistant(memory=memory, agenda=agenda),
            speak_fn=speak_fn,
            listen_fn=listen_fn,
            timing_fn=timing_fn,
            apps=apps,
        )
    finally:
        for store in (memory, agenda, apps, speaker):
            if store is not None:
                store.close()


if __name__ == "__main__":
    main()
