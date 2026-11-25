# Changelog

All notable changes to PARKER. Dates are when the change reached `main`.

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
