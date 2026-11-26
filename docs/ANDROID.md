# PARKER on Android

PARKER's brain, memory and voice run on your laptop. The Android app is a remote control for
it: it chats, records your voice, plays PARKER's replies and shows your day, all through the
**phone companion** built into the desktop app.

## Status

| Part | Status |
|---|---|
| Laptop side: companion API, pairing, encryption | Done (Milestone 5, phase 1) |
| Android app (Kotlin, Jetpack Compose) | Phase 2: next |
| Using it away from home (Tailscale) | Phase 3 |

## Switching it on (laptop)

1. In the PARKER window: **Settings → Phone companion** (tick it).
2. If Windows Firewall asks about Python, allow **Private networks** only.
3. **Settings → Pair phone…** shows a QR code. The Android app scans it once.

Keep the QR code private: it contains the pairing token. **Unpair all phones** in the same window
issues a new one, and phones paired earlier stop working.

## How it's protected

- **Off by default**, and only while the desktop app is running.
- **Encrypted**: HTTPS with a certificate created on your laptop. The QR code carries its SHA-256
  fingerprint and the app accepts only that certificate (pinning), so another device on the Wi-Fi
  can't read the traffic or pretend to be PARKER.
- **Paired**: every request needs the 256-bit token from the QR code; anything else gets 401.
- **Laptop-only actions**: opening apps or files and `/forget all` don't work from the phone.
  Adding a Google Calendar event from the phone needs a confirmation.
- Token, certificate and key are in `memory/`, which Git ignores.

## API (for the Android app)

All requests: `https://<laptop>:8765`, header `Authorization: Bearer <token>`.

| Request | Body | Response |
|---|---|---|
| `GET /api/status` | | `{app, model, owner, voice_in, voice_out}` |
| `GET /api/today` | | `{greeting, plans[], events[{text, when, source}], reminders[{text, when}], memories[]}` |
| `POST /api/message` | `{"text": "..."}` | `{messages[{kind, text}], confirm?{id, question}}` |
| `POST /api/confirm` | `{"id": "...", "yes": true}` | `{messages[...]}` |
| `POST /api/voice` | WAV, 16-bit PCM (any rate/channels) | `{heard, messages[...], confirm?}` |
| `POST /api/speak` | `{"text": "..."}` | `audio/wav` in PARKER's voice |

`kind` is `parker`, `note` or `error`. QR code contents (JSON):
`{"app":"parker","v":1,"hosts":["192.168.1.20"],"port":8765,"token":"…","fp":"<sha256 hex>","name":"Raunak"}`.
