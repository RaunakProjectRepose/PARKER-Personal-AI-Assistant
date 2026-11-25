# Changelog

All notable changes to PARKER. Dates are when the change reached `main`.

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
