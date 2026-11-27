# Roadmap

| Milestone | Scope | Done when | Status |
|---|---|---|---|
| **M1 – Voice Foundation** | Local model, text chat, speech input and output | You can speak to PARKER and it replies aloud | Complete |
| **M2 – Personality & Memory** | Refined personality, persistent memory in SQLite | Memories survive a restart and can be reviewed and edited | Complete |
| **M3 – Desktop Experience** | PySide6 window, transcript, status indicators, voice visualiser | A usable Windows app with a clearly visible listening state | Complete |
| **M4 – Skills & Actions** | Allowlisted tools: open apps, files, reminders, research, Google Calendar sync for the agenda, email | Every action is permissioned and tested | Complete (research and email later) |
| **M5 – Android Companion** | Mobile UI with a secure connection to the laptop | Authenticated access and reliable reconnect | Complete |
| **M6 – Advanced Features** | Hands-free conversation, wake word, proactive notifications, smart home | Opt-in triggers, privacy controls, safe failure | Complete (hands-free conversation, wake word); the rest moves to Phase 2 |

## Phase 2

Phase 1 (M1–M6 core) is done. The plan for version 2 (faster voice, phone reminders, new
skills, a smarter memory and polish) is in [PHASE_2.md](PHASE_2.md).

## Possible improvements noted during M1 (status in Phase 2)

- Run Whisper on the GPU, or try `medium.en`, if transcription accuracy needs to improve. → P2-01
- Keep the audio output open during a session so no lead-in silence is needed. → Done (smoother voice)
- Stream replies so PARKER starts speaking before the whole answer is generated. → P2-02
- Support audio playback on platforms other than Windows.

## Principles

- Local first: inference and storage stay on the owner's machine.
- Visible recording state and an obvious way to stop.
- Allowlisted actions only, with confirmation for anything consequential.
- Credentials, recordings and personal memory never go to GitHub.
