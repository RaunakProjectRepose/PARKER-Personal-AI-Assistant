# Changelog

All notable changes to PARKER. Dates are when the change reached `main`.

## Unreleased – Milestone 6: hands-free conversation

### Added
- **Hands-free conversation** (on by default, "Hands-free conversation" in settings): press the
  mic, Ctrl+Space or Ctrl+Alt+P once and just talk. PARKER stops recording when you pause
  (1.2 s), answers, then listens again by itself.
- The conversation ends when nobody speaks for 8 seconds after a reply (quietly, no "didn't catch
  that"), when you say a clear sign-off ("thanks", "that's all", "stop", "bye", "good night"),
  which PARKER answers briefly without asking the model, when you press **Esc**, or when you type.
  Sign-offs are recognised only as the whole message, so "stop the timer" still works.
- Pressing the mic while PARKER speaks interrupts it and listens straight away; pressing it
  while listening finishes early as before.
- Pauses are detected with the Silero voice-activity model that ships inside Faster-Whisper, so
  nothing new is installed and nothing leaves the laptop. Recording still stops after 30 s.
- `PARKER_END_SILENCE` and `PARKER_LISTEN_WAIT` tune the pause length and the wait;
  `python -m backend.speech_input --hands-free` tests it on its own.

### Changed
- **Esc** while listening now cancels the recording and ends the conversation.

## 2026-11-27 – Milestone 5: away from home (Android app 0.2.0)

### Added
- Use PARKER from anywhere through Tailscale: the pairing code includes the laptop's Tailscale
  address after the home ones, and the app falls back to it automatically.
- The app reconnects by itself when an address stops answering (e.g. leaving home), retrying only
  failures to connect, so a message that reached PARKER is never sent twice.
- `docs/ANDROID.md`: Tailscale setup with a firewall rule limited to Tailscale addresses.

### Verified
- Tested on the phone on mobile data, away from home Wi-Fi: messages reach PARKER on the laptop
  through Tailscale. The first attempt failed because the laptop had no Tailscale and the phone was
  signed in to a different Tailscale account; both must use the same account.

### Fixed (0.1.1)
- Android 17 blocked the app from the home network: it now asks for "Nearby devices"
  (`ACCESS_LOCAL_NETWORK`).

## Unreleased – Milestone 5: Android app 0.1

### Added
- `android/`: Kotlin + Jetpack Compose app (targets Android 17 / API 37, runs on Android 8+) in the
  same golden theme: pair by scanning the laptop's QR code, chat, push-to-talk (16 kHz WAV to the
  laptop's Whisper), spoken replies in PARKER's voice, calendar confirmations, and a Today sheet
  with plans, the next 7 days, reminders and memories.
- Certificate pinning: the app trusts only the SHA-256 fingerprint from the QR code and sends
  nothing, not even the token, to any other server. Pairing stays in app-private storage.
- JVM unit tests for pairing, the WAV format and pinning (against a local TLS server).

## Unreleased – Milestone 5: phone companion (laptop side)

### Added
- HTTPS API for the PARKER Android app (`/api/status`, `/today`, `/message`, `/confirm`,
  `/voice`, `/speak`), sharing the laptop's brain, memory, agenda, reminders and calendar.
- Pairing by QR code (Settings → Pair phone…): a random 256-bit token plus the SHA-256 fingerprint
  of a certificate generated on the laptop, which the phone pins. Requests without the token get
  401; plain HTTP isn't served; "Unpair all phones" issues a new token.
- Off by default ("Phone companion" in settings). Opening apps or files and deleting all memories
  stay laptop-only; calendar additions from the phone need a confirmation.
- Phone voice: the phone's WAV is resampled to 16 kHz for the laptop's Whisper; replies can be
  spoken in PARKER's voice and played on the phone.
- The assistant is now thread-safe for simultaneous laptop and phone use.

## Unreleased – Milestone 4: Google Calendar

### Added
- Google Calendar (permission: events only). The greeting, the Agenda drawer (marked "Google")
  and PARKER's answers include the next 7 days of events, cached for 5 minutes and refreshed on
  the worker thread.
- "add … to my calendar …" / "schedule …" with days, times, "on the 3rd", "on 3 December",
  "on 2/1" and durations ("for an hour", "for 30 minutes"); all-day when no time is given.
  PARKER shows the event and adds it only after you confirm. The model is told it cannot add
  events itself.
- `python -m backend.calendar_connect` for the one-time Google sign-in, and
  `docs/GOOGLE_CALENDAR.md` with the Google Cloud setup.
- `.gitignore` now ignores the whole `memory/` folder, `credentials.json`, `client_secret*.json`
  and token files, so Google keys can never be committed (checked by a test).

## Unreleased – Milestone 4: finding files

### Added
- "find my …", "where is my …", "search my files for …", "where did I save …" search file names
  in Documents, Downloads, Desktop, Pictures, Music and Videos (including OneDrive ones) and any
  folders in `PARKER_SEARCH_FOLDERS`. Contents are never read.
- Matching ignores spacing and punctuation ("AIML303" finds "aiml_303"), understands plurals and
  folder names, ranks recent files higher, and narrows by type words (PDF, slides, spreadsheet,
  photo, video, code…). Hidden, program, `.git`, `node_modules` and virtual-environment folders
  and Office lock files are skipped; a search never runs longer than 4 seconds.
- Results card in the app (click to open, folder icon to show in File Explorer) and numbered
  results in the terminal; follow-ups "open the first one", "open number 2", "open it",
  "show it in the folder". In the app the search runs on the worker thread.
- The model is told it cannot see or search files itself.

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
