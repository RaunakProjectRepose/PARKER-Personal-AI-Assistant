"""Wake word: start talking to PARKER by saying "Hey Parker".

How it works, all on the laptop:

1. The Silero voice-activity model (bundled with Faster-Whisper) watches the
   microphone in 32 ms blocks. Silence and background noise cost almost
   nothing and are thrown away straight away.
2. When someone speaks, that short stretch of speech (up to 10 s) is
   transcribed by a small, fast Whisper model (tiny.en by default).
3. If it starts with "Hey Parker" (or "Parker, ..."), PARKER wakes up. Anything
   said after the name in the same breath ("Hey Parker, what's on today?") is
   treated as the request itself.

Nothing is saved or sent anywhere: audio and text that don't contain the wake
word are dropped immediately. Off by default; switch it on in settings.

Quick manual test, from the project folder:

    python -m backend.wake_word
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from typing import Callable

from backend.speech_input import (
    SAMPLE_RATE,
    STT_COMPUTE,
    STT_DEVICE,
    VAD_BLOCK,
    Endpointer,
    SpeechInputError,
    load_vad,
    load_whisper,
)

WAKE_MODEL = os.environ.get("PARKER_WAKE_MODEL", "tiny.en")
WAKE_NAME = "parker"

# What Whisper writes when it hears "Parker" said quickly or in a noisy room.
NAME_SOUNDS = {"parker", "parka", "parkers", "packer", "barker", "parkar", "parcker", "pakar", "porker"}
GREETINGS = {"hey", "hi", "hello", "ok", "okay", "yo", "hay", "a", "eh"}

# One stretch of speech checked for the wake word.
SEGMENT_PAUSE = 0.7  # seconds of quiet that end a stretch of speech
SEGMENT_MAX = 10.0  # longer speech is someone talking, not calling PARKER


def find_wake_word(text: str) -> str | None:
    """If `text` starts by calling PARKER, return what follows ('' if nothing).

    "Hey Parker."                      -> ""
    "Hey Parker, what's on today?"     -> "what's on today?"
    "Parker remind me in 5 minutes"    -> "remind me in 5 minutes"
    "I told Parker about it"           -> None (not said at the start)
    """
    words = text.strip().split()
    for index, word in enumerate(words[:3]):
        bare = re.sub(r"[^a-z]", "", word.lower())
        if bare in NAME_SOUNDS or (bare == "park" and index + 1 < len(words)
                                   and re.sub(r"[^a-z]", "", words[index + 1].lower()) == "her"):
            before = [re.sub(r"[^a-z]", "", w.lower()) for w in words[:index]]
            if all(w in GREETINGS for w in before):
                skip = index + (2 if bare == "park" else 1)
                rest = " ".join(words[skip:])
                return rest.lstrip(" ,.!?-:;").strip()
            return None
    return None


class WakeWordDetector:
    """Listens on its own thread and calls `on_wake(rest_of_sentence)`.

    pause() releases the microphone (while PARKER listens or speaks);
    resume() picks it up again.
    """

    def __init__(
        self,
        on_wake: Callable[[str], None],
        *,
        transcribe: Callable | None = None,
        speech_prob: Callable | None = None,
        open_stream: Callable | None = None,
        on_error: Callable[[str], None] = lambda message: None,
    ) -> None:
        self._on_wake = on_wake
        self._on_error = on_error
        self._transcribe = transcribe
        self._prob = speech_prob
        self._open_stream = open_stream or _open_microphone
        self._paused = threading.Event()
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def load(self) -> None:
        """Load the voice detector and the small Whisper model (slow, do it once)."""
        if self._prob is None:
            self._prob = load_vad()
        if self._transcribe is None:
            model = load_whisper(WAKE_MODEL, STT_DEVICE, STT_COMPUTE)

            def transcribe(audio) -> str:
                segments, _ = model.transcribe(
                    audio, language="en", beam_size=1, vad_filter=False,
                    initial_prompt="Hey Parker.",  # nudges Whisper towards the name
                    condition_on_previous_text=False,
                )
                return " ".join(seg.text.strip() for seg in segments).strip()

            self._transcribe = transcribe

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stopped.clear()
        self._thread = threading.Thread(target=self._run, name="parker-wake-word", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopped.set()
        if self._thread is not None:
            self._thread.join(3)

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ---- the listening loop (its own thread) ----------------------------------
    def _run(self) -> None:
        try:
            self.load()
        except SpeechInputError as err:
            self._on_error(str(err))
            return
        while not self._stopped.is_set():
            if self._paused.is_set():
                time.sleep(0.05)
                continue
            try:
                self._listen_until_paused()
            except Exception as err:  # e.g. the microphone was unplugged
                self._on_error(f"Wake word stopped listening: {err}")
                self._stopped.wait(5)  # try again in a moment

    def _listen_until_paused(self) -> None:
        import numpy as np

        with self._open_stream() as blocks:
            endpointer = self._new_segment()
            pending = np.zeros(0, dtype=np.float32)
            while not (self._stopped.is_set() or self._paused.is_set()):
                chunk = blocks.read(timeout=0.1)
                if chunk is None:
                    continue
                pending = np.concatenate([pending, chunk])
                while len(pending) >= VAD_BLOCK:
                    result = endpointer.feed(pending[:VAD_BLOCK])
                    pending = pending[VAD_BLOCK:]
                    if result == "done":
                        audio = endpointer.audio()
                        if self._check(audio):
                            return  # woke up: the app pauses us while it listens
                    if result is not None:
                        endpointer = self._new_segment()

    def _new_segment(self) -> Endpointer:
        return Endpointer(self._prob, wait_seconds=5, end_silence=SEGMENT_PAUSE,
                          max_seconds=SEGMENT_MAX, min_speech=0.2, preroll=0.3)

    def _check(self, audio) -> bool:
        if self._paused.is_set() or len(audio) < SAMPLE_RATE * 0.3:
            return False
        rest = find_wake_word(self._transcribe(audio))
        if rest is None or self._paused.is_set():
            return False
        self._paused.set()  # stop listening for the name until PARKER is done
        self._on_wake(rest)
        return True


class _MicrophoneBlocks:
    """The default microphone as a queue of 16 kHz float32 blocks."""

    def __init__(self) -> None:
        import queue

        import sounddevice as sd

        self._queue: queue.Queue = queue.Queue()
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=VAD_BLOCK,
            callback=lambda indata, frames, t, status: self._queue.put(indata[:, 0].copy()),
        )

    def __enter__(self):
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stream.stop()
        self._stream.close()

    def read(self, timeout: float):
        import queue

        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None


def _open_microphone() -> _MicrophoneBlocks:
    try:
        return _MicrophoneBlocks()
    except (ImportError, OSError) as exc:
        raise SpeechInputError(f"Could not use the microphone: {exc}") from exc


if __name__ == "__main__":
    print(f"Loading the wake word detector ({WAKE_MODEL}; the first run downloads it)...")
    woke = threading.Event()

    def on_wake(rest: str) -> None:
        print(f"  ✓ Woke up!{'  Request: ' + rest if rest else ''}")
        woke.set()

    detector = WakeWordDetector(on_wake, on_error=lambda m: print(f"Problem: {m}", file=sys.stderr))
    detector.start()
    print('Say "Hey Parker" (Ctrl+C to quit).')
    try:
        while True:
            if woke.wait(0.2):
                woke.clear()
                time.sleep(1)
                detector.resume()
                print('Listening again: say "Hey Parker".')
    except KeyboardInterrupt:
        detector.stop()
