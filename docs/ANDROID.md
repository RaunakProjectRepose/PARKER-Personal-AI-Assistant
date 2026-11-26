# PARKER on Android

PARKER's brain, memory and voice run on your laptop. The Android app is a remote control for
it: it chats, records your voice, plays PARKER's replies and shows your day, all through the
**phone companion** built into the desktop app.

## Status

| Part | Status |
|---|---|
| Laptop side: companion API, pairing, encryption | Done (Milestone 5, phase 1) |
| Android app (Kotlin, Jetpack Compose) | Version 0.1: pairing, chat, push-to-talk, spoken replies, Today |
| Using it away from home (Tailscale) | Phase 3 |

## Installing the app

**Option A: the ready-made file.** Copy `PARKER-0.1.0.apk` to the phone, open it, and allow
"Install unknown apps" for the app you opened it with (Files or Chrome) when Android asks. It is a
debug build signed on the build machine; Android may show a Play Protect warning for apps not from
the Play Store; choose "Install anyway".

**Option B: build it yourself in Android Studio.**

1. Android Studio → **Open** → the `android` folder of this repository. Let it sync (first time
   downloads a lot).
2. On the phone: **Settings → About phone → tap "Build number" 7 times** (unlocks Developer
   options), then **Settings → System → Developer options → USB debugging: on**.
3. Connect the phone by USB and allow debugging when it asks.
4. In Android Studio pick the phone at the top and press **Run ▶**.

The project targets Android 17 (API 37) and runs on Android 8 and newer.

## Using the app

1. Laptop: PARKER running, **Settings → Phone companion** on.
2. Phone on the same Wi-Fi: open PARKER → **Pair with laptop** → scan the code from
   **Settings → Pair phone…** (allow the camera).
3. Type, or tap the golden mic, speak, and tap ✓. PARKER answers aloud (switch off "Speak
   replies" in **Today** if you prefer silence). Tap ■ to stop it speaking.
4. **Today** shows the greeting, plans, the next 7 days (incl. Google Calendar), reminders and
   memories, and has **Unpair this phone**.

## Switching it on (laptop)

1. In the PARKER window: **Settings → Phone companion** (tick it).
2. If Windows Firewall asks about Python, allow **Private networks** only.
3. **Settings → Pair phone…** shows a QR code. The Android app scans it once.

Keep the QR code private: it contains the pairing token. **Unpair all phones** in the same window
issues a new one, and phones paired earlier stop working.

## If the phone can't connect

The app's error lists each address it tried. Check, in order:

1. **The address.** The Pair phone window lists the laptop's addresses, home Wi-Fi (192.168.x.x)
   first. If the right one is missing, set it by hand before starting PARKER:
   `$env:PARKER_COMPANION_HOSTS = "192.168.1.48"`, then pair again.
2. **Network profile.** Windows blocks incoming connections on **Public** networks. For your home
   Wi-Fi: **Settings → Network & internet → Wi-Fi → (your network) → Network profile type →
   Private**. Check with `Get-NetConnectionProfile`.
3. **Firewall rule.** In PowerShell **run as Administrator**:
   `New-NetFirewallRule -DisplayName "PARKER companion" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow -Profile Private`
4. **Guest Wi-Fi or a VPN** on the phone can stop devices from seeing each other.

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
