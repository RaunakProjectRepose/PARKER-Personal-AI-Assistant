# PARKER – Personal AI Assistant

PARKER is a local-first, voice-powered personal AI assistant. It listens through your microphone,
thinks with a language model running on your own laptop, and answers out loud — no cloud APIs,
no subscriptions, and nothing you say leaves the machine.

## What works today (Milestones 1–2)

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
| `/reset` | Forget the current conversation; saved memories stay |
| `/help`, `/quit` | Show commands, leave (or Ctrl+C) |

Each part can also be tried on its own:

```powershell
python -m backend.brain "Who are you?"
python -m backend.speech_output "Good evening. All systems are ready."
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
  greeting.py        # startup greeting built from the agenda
  speech_input.py    # microphone recording + speech-to-text
  speech_output.py   # text-to-speech + playback
  main.py            # terminal chat that ties it together
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
