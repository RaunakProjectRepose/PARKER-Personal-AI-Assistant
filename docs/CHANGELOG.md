# Changelog

All notable changes to PARKER. Dates are when the change reached `main`.

## Unreleased – Milestone 4: reminders

### Added
- "remind me …" (typed or spoken) with relative times ("in 20 minutes", "in half an hour", "in
  1.5 hours", number words), clock times ("at 6 pm", "at 18:30", "at 3" meaning the next 3
  o'clock, "noon") and days ("tomorrow", "tonight", "on Friday").
- The desktop app checks every 5 seconds and speaks due reminders, with a tray notification,
  even while hidden; the terminal announces them between messages. Missed reminders are
  mentioned on the next start.
- `/reminders`, `/reminder cancel <id>`, and a Reminders list in the Agenda drawer (Delete to
  cancel).
- PARKER's own reminder pop-up: a golden card in the bottom-right corner, on top of every app
  without taking keyboard focus, with Done and Snooze 10 min; it stays until answered. Added
  after the first laptop test showed no Windows notification (notifications were switched off).
  The card replaces the Windows notification so a reminder never shows twice; the taskbar button
  also flashes.
- Questions such as "remind me what my exam date is" still go to the model; the model is told it
  cannot set reminders itself.

## Unreleased – Milestone 4: opening apps

### Added
- "open …", "launch …", "start …" (typed or spoken) open apps from the Start Menu, built-in
  Windows tools (Notepad, Calculator, File Explorer, Settings…), standard folders (Documents,
  Downloads… including OneDrive-moved ones) and entries added with `/app add`.
- Nicknames ("VS Code", "Chrome") and small transcription slips are understood; uninstallers and
  help/docs shortcuts are never offered.
- `/apps [search]`, `/apps refresh`, `/app add <name> = <path or URL>`, `/app remove <name>`.
- Requests are recognised in code and opened like a double-click; an "open …" that matches
  nothing goes to the model, which is told it can't open anything itself.

## Unreleased – Milestone 4: PARKER from any app

### Added
- System tray: closing the window hides PARKER instead of quitting; the tray icon glows while
  listening or speaking. "Quit PARKER" in the tray menu exits completely.
- Global shortcut **Ctrl+Alt+P** to talk from any app, using Windows' `RegisterHotKey` (only
  that combination is reported; no keyboard hook). Changeable in settings and remembered. If the
  default is taken, a free alternative is chosen automatically and announced; a shortcut that
  can't be registered is reported in the chat and the tray. `python -m frontend.hotkey --test`
  checks a shortcut on its own.
- First laptop test: Ctrl+Alt+Space did nothing, most likely because the Claude desktop app uses
  the same combination, so the default changed to Ctrl+Alt+P.
- Optional "Start with Windows" (adds/removes one entry under the current user's Run key) and a
  `--background` mode that starts hidden and keeps the greeting silent.
- `parker.pyw` launcher to run PARKER without a console window.

## Unreleased – Premium, less cluttered design

### Changed
- Agenda and Memories moved into a drawer that slides in from the right (calendar and sparkle
  icons, Ctrl+1 / Ctrl+2, Esc to close); the conversation gets the whole window by default.
- One rounded message bar with a send arrow and a gold mic button that becomes "done" while
  listening and "stop" while PARKER speaks; separate Send, Talk and Stop buttons removed.
- "Speak replies", "Clear conversation" and the model name moved to a settings menu.
- Message bubbles without "You"/"PARKER" labels: soft gold pills for you, white cards with a
  gentle shadow for PARKER; spoken messages get a quiet "spoken" tag.
- Small gold wordmark, larger orb as the centrepiece, spaced-out status text, a centred reading
  column and a soft radial glow behind everything. Icons are drawn in code.

## Unreleased – Milestone 3: desktop app

### Added
- PySide6 desktop app (`python -m frontend.app`) in a warm "heavenly gold" theme.
- Animated status orb: breathes when ready, rings when listening, a circling arc when thinking,
  pulses when speaking.
- Chat transcript with message bubbles; Talk button and Ctrl+Space for push-to-talk; Stop button
  and Esc to stop speaking mid-sentence; "Speak replies" toggle.
- Agenda panel (plans with tick-to-complete, next 7 days of events, add/remove) and Memories
  panel (add/forget).
- Spoken greeting on startup, and every chat command works in the message box.
- Model, microphone and voice run on a background thread so the window never freezes.

### Changed
- Memory and agenda stores are thread-safe (shared connection with a lock).
- Speech can be stopped mid-reply.

### Fixed
- An invalid event time such as "25:99" is now rejected instead of becoming part of the title.
- The app froze ("Not Responding") and opened a blank extra window: replies and the greeting were
  built on the background thread. All worker signals are now queued onto window slots, and the
  chat refuses to build bubbles off the window thread.
- The 30-second recording limit never fired, because its stop request queued behind the
  recording itself.

## 2026-11-25 – Smoother voice

### Changed
- Speech now plays through one always-open audio stream (`sounddevice`) instead of a new
  `winsound` playback per reply: the device stays awake, so the lead-in drops from 1 s to 0.2 s.
- Piper speaks sentence by sentence and the first sentence plays while the rest is generated.
- Larger audio buffers to stop choppy playback on Bluetooth and busy CPUs.

### Added
- `PARKER_VOICE_SPEED` and `PARKER_VOICE_VARIATION` to tune pace and rhythm, and
  `python -m backend.speech_output --compare` to pick by ear. Rhythm variation 0.8 is now the
  default (chosen by ear).
- Name pronunciation: the voice says a respelling of the owner's name ("Rawnak" for Raunak, picked by ear)
  while the screen keeps the real spelling. `PARKER_OWNER_SPOKEN` sets it and
  `python -m backend.speech_output --names` plays options.
- `--timing` shows thinking and speaking times per reply.
- `PARKER_AUDIO=winsound` to fall back to the old playback; used automatically if the stream
  can't open.

### Fixed
- PARKER referred to "what we said earlier" about things never discussed.

## 2026-11-25 – Milestone 2: personality, memory and agenda

### Added
- Warm, friendly, motivating personality that calls the owner by name (`PARKER_OWNER_NAME`)
  and keeps replies to two to four sentences.
- Startup greeting by time of day with the plans for this session and today's events, spoken
  aloud when voice is on. Built from the agenda in code, so it never invents anything.
- Agenda (`backend/agenda.py`): `/plan`, `/plans`, `/done`, `/event`, `/events`, `/cancel`.
- PARKER knows the current date and the next 7 days of the agenda when answering.
- Long-term memory in SQLite (`backend/memory.py`): say or type "remember that…" to save a fact.
- `/remember`, `/memories`, `/edit`, `/forget`, `/forget all` and `/help` commands.
- Saved memories are added to PARKER's instructions, so it knows them in every session.

## 2026-11-25 – Licence

### Added
- GPL-3.0-or-later licence (`LICENSE`), matching the Piper TTS dependency.

## 2026-11-25 – Milestone 1 core: PARKER can listen, think and speak

### Added
- Push-to-talk speech input with Faster-Whisper `small.en` (`--listen`, `--voice`).
- Spoken replies with Piper TTS and the `en_GB-alba-medium` voice (`--speak`).
- Terminal chat (`python -m backend.main`) with `/reset` and `/quit`.
- Conversation memory for the last ten exchanges.
- `brain.py`: local Qwen 3.5 4B through Ollama, thinking mode off.
- Offline test suite (55 tests) using fake model, voice, microphone and speakers.
- Project docs: architecture, roadmap, changelog, credits, `.env.example`.

### Fixed
- PARKER said it couldn't hear spoken messages; the system prompt now explains transcription.
- The first second of speech was cut off on Windows; a 1 s silent lead-in was added.
- PARKER guessed facts about the user (a favourite colour) instead of saying it didn't know.
- PARKER claimed to be made by Google; the system prompt now names Qwen.
- Failing to download the speech model crashed the chat; it now falls back to typing.

## 2026-11-23 – Project created
- README and `.gitignore`.
