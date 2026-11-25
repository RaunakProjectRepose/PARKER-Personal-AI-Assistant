# Architecture

PARKER is a set of small modules, each with one job, connected by the terminal chat in
`backend/main.py`. Any module can be replaced without changing the others.

## Data flow

```
 microphone                                                    speakers
     │                                                             ▲
     ▼                                                             │
speech_input.py ──text──► assistant.py ──messages──► brain.py      │
 (Faster-Whisper)          (recent history)          (Ollama)      │
                                 ▲                       │         │
                                 └────────reply──────────┘         │
                                 │                                 │
                                 └──────────reply──► speech_output.py
                                                       (Piper TTS)
```

1. **Hearing** – `speech_input.Listener` records from the default microphone until Enter is
   pressed, then transcribes the audio locally with Faster-Whisper (`small.en`, CPU, int8).
   Audio stays in memory and is discarded after transcription.
2. **Remembering** – `assistant.Assistant` keeps the last ten exchanges and passes them with
   each new message. A message whose reply failed is not remembered.
3. **Thinking** – `brain.generate_response()` sends the system prompt, history and new message
   to Ollama's `/api/chat` endpoint with thinking mode off, and returns the reply text.
4. **Speaking** – `speech_output.Speaker` turns the reply into a WAV in memory with Piper,
   adds a short silent lead-in so Windows audio devices wake in time, and plays it.

## Design decisions

| Decision | Reason |
|---|---|
| Everything runs locally | Privacy and zero running cost. |
| Model access only through `brain.py` | The model or runtime can be swapped in one place. |
| Thinking mode off | 34 s per reply with it on vs. under 1 s off (measured on the RTX 4060). |
| System prompt names PARKER and Qwen | Without it the model claimed to be made by Google. |
| System prompt forbids guessing user facts | After `/reset`, the model once invented a favourite colour. |
| Ten-turn history limit | Qwen is loaded with a 4096-token context window. |
| Push-to-talk, no wake word yet | Simpler, reliable, and the recording state is always obvious. |
| Whisper on CPU first | Works without extra NVIDIA libraries; a 3.5 s clip transcribes in ~1.1 s. |
| `winsound` for playback | Built into Python on Windows; no extra audio dependency. |
| Voice and microphone load lazily | Text-only mode needs no voice files or speech models. |
| Errors become `BrainError` / `SpeechError` / `SpeechInputError` | The chat reports problems and keeps running instead of crashing. |
| Dependencies are injected (`generate=`, `load_voice=`, `play=`, `record=`) | Tests use fakes, so they run offline in under a second. |

## Configuration

All settings come from environment variables with safe defaults; see `.env.example`.

## Planned additions

Persistent memory (SQLite) in Milestone 2, a PySide6 desktop UI in Milestone 3, and
permission-controlled actions in Milestone 4. See [ROADMAP.md](ROADMAP.md).
