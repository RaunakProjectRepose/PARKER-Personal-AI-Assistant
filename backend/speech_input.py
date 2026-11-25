"""PARKER's ears: push-to-talk recording and speech-to-text.

Recording uses `sounddevice` (microphone access); transcription uses
Faster-Whisper (MIT licence) running locally. Nothing is sent online and no
recording is saved to disk: audio lives in memory only until it is transcribed.

The Whisper model (~480 MB for small.en) downloads automatically the first
time it is used, then works offline.

Quick manual test, from the project folder:

    python -m backend.speech_input
"""

from __future__ import annotations

import os
import sys
import time
from typing import Callable

SAMPLE_RATE = 16_000  # Whisper expects 16 kHz mono audio.
MAX_SECONDS = 30  # Safety limit: recording always stops by itself.
MIN_SECONDS = 0.3  # Shorter than this is almost certainly an accidental tap.

# CPU first: it works on every Windows laptop with no extra NVIDIA libraries.
# GPU ("cuda", "float16") is a later speed-up once this works.
STT_MODEL = os.environ.get("PARKER_STT_MODEL", "small.en")
STT_DEVICE = os.environ.get("PARKER_STT_DEVICE", "cpu")
STT_COMPUTE = os.environ.get("PARKER_STT_COMPUTE", "int8")


class SpeechInputError(Exception):
    """Raised when PARKER cannot record or understand speech."""


def record_until_enter(
    wait_for_enter: Callable[[str], object] = input,
    max_seconds: float = MAX_SECONDS,
):
    """Record from the default microphone until Enter is pressed.

    Returns the audio as a 1-D float32 NumPy array at 16 kHz.
    """
    try:
        import numpy as np
        import sounddevice as sd
    except (ImportError, OSError) as exc:
        raise SpeechInputError(
            "Microphone support is not installed. Run: "
            "python -m pip install -r requirements.txt"
        ) from exc

    chunks = []
    started = time.monotonic()

    def collect(indata, frames, time_info, status):
        if time.monotonic() - started < max_seconds:
            chunks.append(indata.copy())

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=collect
        ):
            wait_for_enter("  ● Recording... press Enter to stop. ")
    except sd.PortAudioError as exc:
        raise SpeechInputError(f"Could not use the microphone: {exc}") from exc

    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).reshape(-1)


def load_whisper(model: str = STT_MODEL, device: str = STT_DEVICE, compute: str = STT_COMPUTE):
    """Load a Faster-Whisper model. Imported lazily so text-only PARKER never needs it."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SpeechInputError(
            "Faster-Whisper is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc
    try:
        return WhisperModel(model, device=device, compute_type=compute)
    except Exception as exc:  # Download, disk or GPU problems all end up here.
        raise SpeechInputError(
            f"Could not load speech model '{model}' on {device}: {exc}. "
            "The first run needs internet to download the model."
        ) from exc


class Listener:
    """Records one spoken message and turns it into text."""

    def __init__(
        self,
        *,
        load_model: Callable = load_whisper,
        record: Callable = record_until_enter,
    ) -> None:
        self._model = load_model()  # Slow part: done once, not per message.
        self._record = record

    def transcribe(self, audio) -> str:
        """Return the text spoken in `audio` (16 kHz float32), or '' if none."""
        if len(audio) < SAMPLE_RATE * MIN_SECONDS:
            return ""
        segments, _info = self._model.transcribe(
            audio,
            language="en",
            beam_size=5,
            vad_filter=True,  # Skips silence, which stops Whisper inventing words.
        )
        return " ".join(seg.text.strip() for seg in segments).strip()

    def listen(self) -> str:
        """Record until Enter, then return what was said ('' if nothing)."""
        return self.transcribe(self._record())


if __name__ == "__main__":
    try:
        print(f"Loading speech model '{STT_MODEL}' on {STT_DEVICE} (first run downloads it)...")
        listener = Listener()
        input("Press Enter, then speak. ")
        audio = record_until_enter()
        print(f"Recorded {len(audio) / SAMPLE_RATE:.1f} s. Transcribing...")
        start = time.monotonic()
        text = listener.transcribe(audio)
        print(f"Heard: {text or '(nothing)'}")
        print(f"Transcription took {time.monotonic() - start:.1f} s.")
    except SpeechInputError as err:
        print(f"PARKER microphone error: {err}", file=sys.stderr)
        sys.exit(1)
