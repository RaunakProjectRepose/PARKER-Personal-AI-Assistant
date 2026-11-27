# PARKER Phase 2 (version 2)

Phase 1 (v1.0) is complete: voice in and out, memory, personality, agenda, reminders, apps,
file search, Google Calendar, the desktop app with tray and hotkey, the Android app at home and
away, hands-free conversation and the "Hey Parker" wake word.

Phase 2 makes PARKER **faster, more natural and more useful day to day**. The rules don't
change: local first, visible listening, allowlisted actions, confirmation for anything
consequential, nothing private in Git.

**Priority:** High = do first · Medium = next · Low = when there's time.
**Effort:** S = one session · M = two or three sessions · L = a bigger piece of work.

## Suggested order

1. **Groundwork:** v1.0.0 release (P2-24), automatic tests on GitHub (P2-23), start ready to
   listen (P2-06).
2. **Speed:** Whisper on the GPU (P2-01), stream replies into speech (P2-02).
3. **Daily use:** timers and weather (P2-16), reminders on the phone (P2-09), morning briefing
   (P2-07).
4. Then the larger skills: Gmail, web lookup, smart home, a dedicated wake-word model.

## A. Faster, more natural voice

| ID | Item | Why | Priority | Effort |
|---|---|---|---|---|
| P2-01 | Run Whisper on the RTX 4060 (`cuda`, `float16`), with an automatic CPU fallback | Transcription is on the CPU today; the GPU should cut the wait after you stop talking, and makes `medium.en` (more accurate) practical | High | S |
| P2-02 | Stream the model's reply into speech: speak the first sentence while the rest is still being generated | Removes most of the pause before PARKER starts talking on longer answers | High | M |
| P2-03 | Barge-in: interrupt PARKER by voice ("Parker, stop" or just start talking) | Today you press the mic or Esc to interrupt. Needs echo handling so PARKER doesn't hear itself | Medium | L |
| P2-04 | A dedicated "Hey Parker" model (e.g. a custom openWakeWord model), with Whisper as a second check | Lower CPU use than transcribing every burst of speech, and fewer false or missed wakes in a noisy room | Medium | L |
| P2-05 | A soft chime and orb cue when hands-free listening starts and stops | Lets you know PARKER is listening when the window is hidden | Low | S |
| P2-25 | Understand Hinglish and Hindi words (multilingual Whisper, names list) | Indian names, places and mixed-language phrases get misheard by the English-only model | Low | M |

## B. Always there

| ID | Item | Why | Priority | Effort |
|---|---|---|---|---|
| P2-06 | Start with Windows, hidden, with the wake word ready (models loaded at login) | "Hey Parker" works as soon as the laptop is on, without opening anything | High | S |
| P2-07 | Opt-in proactive heads-ups: morning briefing, "your meeting starts in 10 minutes" | PARKER tells you things at the right time instead of waiting to be asked | Medium | M |
| P2-08 | Log file, start-up health check (Ollama, microphone, voice, models) and a "What went wrong?" view | Faster fixes: no more reading PowerShell screenshots to find the cause | Medium | S |

## C. Phone

| ID | Item | Why | Priority | Effort |
|---|---|---|---|---|
| P2-09 | Reminders and heads-ups on the phone | Today reminders appear only on the laptop | High | M |
| P2-10 | Hands-free on the phone, plus a quick-settings tile or home-screen widget | One tap to talk; no button press to finish | Medium | M |
| P2-11 | Signed release build and an "update available" check from the laptop | No more "install anyway" warnings, and the phone knows when a new version is out | Low | S |

## D. New skills (each one allowlisted and tested, with confirmation where it matters)

| ID | Item | Why | Priority | Effort |
|---|---|---|---|---|
| P2-16 | Timers, alarms and weather ("set a timer for 10 minutes", "will it rain today?") | Everyday assistant basics that PARKER doesn't do yet | Medium | S |
| P2-15 | Media control: play, pause, next track, volume | Hands-free music control while working | Low | S |
| P2-12 | Gmail: read and summarise unread mail; draft replies that you approve before they're sent | Was in the original plan; uses the Google sign-in that already exists | Medium | L |
| P2-13 | Web lookup with sources ("look up…"), opt-in | Answers questions the local model can't know | Medium | M |
| P2-14 | Smart home through Home Assistant's local API; allowlisted devices; confirmation for locks and doors | Lights, plugs and so on by voice | Low | L |

## E. A smarter brain and memory

| ID | Item | Why | Priority | Effort |
|---|---|---|---|---|
| P2-17 | "Shall I remember that?" when you mention something worth keeping, plus memory search | Memory grows without you having to say "remember that…" | Medium | M |
| P2-18 | Daily conversation summaries, so PARKER can truthfully recall earlier days | Today it remembers only the current session and saved facts | Medium | M |
| P2-19 | Let the model choose actions through tool calls (checked against the allowlist), alongside today's patterns | Understands more natural phrasing for reminders, calendar and apps | Medium | L |
| P2-20 | Choose the model in settings (e.g. a larger Qwen when plugged in) | Better answers when speed matters less | Low | S |

## F. Polish and engineering

| ID | Item | Why | Priority | Effort |
|---|---|---|---|---|
| P2-24 | Tag **v1.0.0** on GitHub with release notes and the APK | Marks the end of Phase 1; a safe point to return to | High | S |
| P2-23 | GitHub Actions: run the laptop and Android tests on every push; clean up the remaining lint warnings | Catches breakage before it reaches the laptop | High | S |
| P2-21 | A proper Settings window (voice, shortcut, hands-free timing, wake word, phone) | The settings menu is getting long | Medium | M |
| P2-22 | One-click setup: a script or installer that creates the venv, downloads the models and adds a Start Menu shortcut | Setting PARKER up again, or on another PC, takes minutes instead of an evening | Medium | M |

## Known limits carried over from v1

- The phone needs the laptop on, with PARKER running (and Tailscale on both when away).
- The wake word uses some CPU while you talk near the laptop (each burst of speech is checked).
- Hands-free pause length is fixed per session (`PARKER_END_SILENCE`); there's no settings slider yet.
- Three unused imports flagged by the linter (fixed in P2-23).
