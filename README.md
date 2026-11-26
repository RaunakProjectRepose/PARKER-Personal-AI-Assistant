# PARKER – Personal AI Assistant

PARKER is a local-first, voice-powered personal AI assistant. It listens through your microphone,
thinks with a language model running on your own laptop, and answers out loud — no cloud APIs,
no subscriptions, and nothing you say leaves the machine.

## What works today (Milestones 1–3, M4 in progress)

- **Reminders** — "remind me in 20 minutes to stretch", "remind me at 6 pm to call Mum",
  "remind me tomorrow at 9 to submit the assignment". Spoken aloud on time with a golden pop-up
  (Done / Snooze 10 min), even from the tray; missed ones are shown when PARKER next starts.
- **Finds files** — "find my AIML303 notes", "where is my resume?", "find my latest screenshot".
  Searches file names (never contents) in your own folders, then "open the first one".
- **Opens apps and folders** — "open VS Code", "launch Chrome", "open my Downloads". Only Start
  Menu apps, a few Windows tools, your standard folders and entries you add; the model never
  runs anything.
- **Always available** — closing the window keeps PARKER in the system tray; press
  **Ctrl+Alt+P** in any app to talk, and it answers without switching windows. Optionally
  starts with Windows.

- **Desktop app** — a calm, golden window: a glowing status orb (listening, thinking, speaking),
  a centred conversation, one message bar with a mic button, and Agenda and Memories in a
  drawer that slides in only when you want it.


- **Talk or type** — push-to-talk speech recognition with Faster-Whisper, or plain typing.
- **Local brain** — Qwen 3.5 4B through Ollama, running fully on the GPU (~0.9 s per reply).
- **Spoken replies** — Piper TTS with a British-English voice (`en_GB-alba-medium`).
- **Conversation memory** — remembers the last ten exchanges within a session; `/reset` clears it.
- **Long-term memory** — say "remember that…" and PARKER keeps it across restarts, in a private
  SQLite file that never leaves your laptop. Nothing is saved unless you ask.
- **Warm, motivating personality** — greets you by name with your plans for the session and
  today's events, and keeps replies short enough to listen to.
- **Agenda** — `/plan` tasks for next session and `/event` dates, stored locally.
- **Honest by design** — tells you when it doesn't know something instead of guessing.
- **Private** — recordings are kept in memory only and never written to disk.

## Requirements

- Windows 10/11 (speech playback currently uses Windows' built-in `winsound`)
- Python 3.12
- [Ollama](https://ollama.com) with the model pulled: `ollama pull qwen3.5:4b`
- A microphone and speakers for voice mode
- An NVIDIA GPU is recommended for the language model (tested on an RTX 4060 Laptop, 8 GB)

## Setup

Run these in PowerShell from the project folder:

```powershell
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass   # this window only
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m piper.download_voices en_GB-alba-medium --data-dir voices
```

The speech-recognition model (~480 MB) downloads automatically the first time you use voice input.

## Usage

The desktop app:

```powershell
python -m frontend.app              # voice and microphone on
python -m frontend.app --no-voice   # text only
python -m frontend.app --background # start hidden in the system tray
```

Or double-click **`parker.pyw`** to start PARKER without a terminal window.

**Using PARKER from any app.** Closing the window hides PARKER to the system tray (the icons by
the clock) instead of quitting. Press **Ctrl+Alt+P** anywhere to talk, and again when you've
finished; PARKER answers aloud. Click the tray icon to open the window; right-click it and
choose **Quit PARKER** to exit completely. The shortcut can be changed, and "Start with Windows"
switched on, in the settings menu. The shortcut uses Windows' `RegisterHotKey`, so PARKER is
told only about that one key combination and never sees your other typing. If another app
already uses Ctrl+Alt+P, PARKER picks a free alternative and tells you which. To check that
Windows delivers a shortcut at all, run `python -m frontend.hotkey --test "Ctrl+Alt+P"`.

Shortcuts: **Ctrl+Space** talk (press again when you've finished), **Esc** stop speaking or
close the drawer, **Enter** send, **Ctrl+1** agenda, **Ctrl+2** memories. The mic button turns
into a stop button while PARKER speaks. "Speak replies" and "Clear conversation" are in the
settings menu (top right). Every chat command below also works in the message box.

The terminal version is still available:

```powershell
python -m backend.main            # type to PARKER, read the replies
python -m backend.main --speak    # replies are also spoken aloud
python -m backend.main --listen   # press Enter on an empty line to talk
python -m backend.main --voice    # both: a full spoken conversation
```

In the chat:

| Command | What it does |
|---|---|
| `remember that …` (typed or spoken) | Save a fact about you |
| `/remember <fact>` | Same, as a command |
| `/memories` | List everything PARKER remembers, with ids |
| `/edit <id> <fact>` | Change a memory |
| `/forget <id>` | Delete one memory |
| `/forget all` | Delete every memory (asks first) |
| `/plan <task>` | Add a task for next session (read out at startup) |
| `/plans`, `/done <id>` | List open plans, tick one off |
| `/event <day> [HH:MM] <what>` | Add an event, e.g. `/event today 18:00 Gym` (day: `today`, `tomorrow`, `friday`, `2026-12-03` or `3/12`) |
| `/events`, `/cancel <id>` | List the next 7 days, delete an event |
| `remind me …` (typed or spoken) | e.g. "remind me in 20 minutes to stretch", "remind me on Friday at 10 am about the hackathon" |
| `/reminders`, `/reminder cancel <id>` | List upcoming reminders, cancel one (or select it in the Agenda drawer and press Delete) |
| `find my …` / `where is my …` (typed or spoken) | Search file names in Documents, Downloads, Desktop, Pictures, Music, Videos (incl. OneDrive) |
| `open the first one`, `open number 2`, `open it`, `show it in the folder` | After a search; or click a result |
| `open <app or folder>` (typed or spoken) | e.g. "open VS Code", "open my Downloads folder" |
| `/apps [search]` | List what PARKER can open (`/apps refresh` after installing something) |
| `/app add <name> = <path or web address>` | Teach PARKER a new one, e.g. `/app add Timetable = https://…` |
| `/app remove <name>` | Remove one you added |
| `/reset` | Forget the current conversation; saved memories stay |
| `/help`, `/quit` | Show commands, leave (or Ctrl+C) |

Add `--timing` to see how long thinking and speaking take for each reply.

Each part can also be tried on its own:

```powershell
python -m backend.brain "Who are you?"
python -m backend.speech_output "Good evening. All systems are ready."
python -m backend.speech_output --compare     # hear speed and rhythm options
python -m backend.speech_output --names       # hear ways to pronounce your name
python -m backend.speech_input
```

## Configuration

Settings are read from environment variables. See [`.env.example`](.env.example) for the full
list with defaults. Set one for the current PowerShell window like this:

```powershell
$env:PARKER_VOICE_LEAD_IN = "1.5"
```

## Tests

```powershell
python -m pytest
```

The tests never contact Ollama, a microphone or speakers — those are replaced with fakes — so the
whole suite runs offline in under a second.

## Project layout

```
backend/
  brain.py           # talks to the local model through Ollama
  assistant.py       # keeps the recent conversation
  memory.py          # long-term facts in SQLite
  agenda.py          # plans and events (same database)
  apps.py            # opening apps and folders by name
  reminders.py       # "remind me …": understanding, storing and firing reminders
  files.py           # "find my …": searching file names in your own folders
  greeting.py        # startup greeting built from the agenda
  speech_input.py    # microphone recording + speech-to-text
  speech_output.py   # text-to-speech + playback
  main.py            # terminal chat that ties it together
frontend/
  app.py             # desktop window: chat, controls, memories and agenda panels
  worker.py          # runs the model, microphone and voice off the window thread
  orb.py             # the animated status orb
  icons.py           # line icons drawn in code
  toast.py           # the reminder pop-up
  hotkey.py          # the system-wide talk shortcut (Windows RegisterHotKey)
  autostart.py       # optional "Start with Windows"
parker.pyw           # double-click launcher without a console window
  theme.py           # the golden colour palette and styles
tests/               # one test file per module
docs/                # architecture, roadmap, changelog, credits
voices/              # downloaded voice files (ignored by Git)
memory/              # your private memory database (ignored by Git)
```

More detail: [Architecture](docs/ARCHITECTURE.md) · [Roadmap](docs/ROADMAP.md) ·
[Changelog](docs/CHANGELOG.md) · [Credits](docs/CREDITS.md)

## Security and privacy

Credentials, private conversations, recordings, memory databases, voice files and model weights
must never be committed to this repository; `.gitignore` excludes them.

## License

PARKER is free software, licensed under the [GNU General Public License v3.0](LICENSE)
(GPL-3.0-or-later). You may use, study, share and modify it; if you distribute a modified
version, it must be released under the same licence. This matches PARKER's voice engine, Piper,
which is also GPL-3.0. Third-party components and their licences are listed in
[docs/CREDITS.md](docs/CREDITS.md).
