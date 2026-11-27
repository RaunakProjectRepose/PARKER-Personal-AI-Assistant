"""PARKER's ears: recording and speech-to-text.

Two ways to record: push-to-talk (until a key or button says stop) and
hands-free (until you stop talking, detected with the Silero voice-activity
model that ships inside Faster-Whisper).

Recording uses `sounddevice` (microphone access); transcription uses
Faster-Whisper (MIT licence) running locally. Nothing is sent online and no
recording is saved to disk: audio lives in memory only until it is transcribed.

The Whisper model (~480 MB for small.en) downloads automatically the first
time it is used, then works offline.

Quick manual test, from the project folder:

    python -m backend.speech_input               (press Enter to stop)
    python -m backend.speech_input --hands-free  (stops when you pause)
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

# Hands-free listening. Silero VAD scores speech in 512-sample (32 ms) blocks.
VAD_BLOCK = 512
BLOCK_SECONDS = VAD_BLOCK / SAMPLE_RATE
END_SILENCE = float(os.environ.get("PARKER_END_SILENCE", "1.2"))  # pause that ends a message
LISTEN_WAIT = float(os.environ.get("PARKER_LISTEN_WAIT", "8"))  # give up if nobody speaks


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


class Endpointer:
    """Decides, block by block, when someone started and finished speaking.

    `speech_prob` maps a 1-D float32 window (a multiple of VAD_BLOCK samples) to
    one speech probability per block; only the newest block's score is used, the
    rest of the window is context.  feed() returns None to keep listening,
    "done" once speech was followed by `end_silence` seconds of quiet, or
    "timeout" if nobody spoke within `wait_seconds`.
    """

    def __init__(
        self,
        speech_prob: Callable,
        *,
        wait_seconds: float = LISTEN_WAIT,
        end_silence: float = END_SILENCE,
        min_speech: float = 0.25,
        max_seconds: float = MAX_SECONDS,
        start_threshold: float = 0.5,
        end_threshold: float = 0.35,
        context_blocks: int = 16,
        preroll: float = 0.5,
    ) -> None:
        self._prob = speech_prob
        self._wait = wait_seconds / BLOCK_SECONDS
        self._end = end_silence / BLOCK_SECONDS
        self._min_speech = max(1, round(min_speech / BLOCK_SECONDS))
        self._max = max_seconds / BLOCK_SECONDS
        self._start_threshold = start_threshold
        self._end_threshold = end_threshold
        self._context = context_blocks
        self._preroll = round(preroll / BLOCK_SECONDS)
        self.blocks: list = []
        self.start: int | None = None  # block where speech began
        self._speech_run = 0
        self._silence_run = 0
        self.result: str | None = None

    @property
    def started(self) -> bool:
        return self.start is not None

    def feed(self, block) -> str | None:
        import numpy as np

        if self.result is not None:
            return self.result
        self.blocks.append(np.asarray(block, dtype=np.float32).reshape(-1))
        window = np.concatenate(self.blocks[-self._context:])
        prob = float(np.asarray(self._prob(window)).reshape(-1)[-1])
        count = len(self.blocks)

        if not self.started:
            self._speech_run = self._speech_run + 1 if prob >= self._start_threshold else 0
            if self._speech_run >= self._min_speech:
                self.start = count - self._speech_run
            elif count >= self._wait or count >= self._max:
                self.result = "timeout"
        else:
            self._silence_run = self._silence_run + 1 if prob < self._end_threshold else 0
            if self._silence_run >= self._end or count >= self._max:
                self.result = "done"
        return self.result

    def audio(self, everything: bool = False):
        """The speech, with a little lead-in so the first word is never clipped.

        With `everything`, return all of it even if no speech was detected (a
        manual stop: let Whisper decide whether anything was said).
        """
        import numpy as np

        if not self.blocks or (not self.started and not everything):
            return np.zeros(0, dtype=np.float32)
        first = max(0, self.start - self._preroll) if self.started else 0
        return np.concatenate(self.blocks[first:])


def load_vad() -> Callable:
    """Silero VAD from Faster-Whisper: window -> speech probability per block."""
    try:
        from faster_whisper.vad import get_vad_model

        model = get_vad_model()  # cached: loaded once, takes a fraction of a second
    except Exception as exc:
        raise SpeechInputError(f"Hands-free listening is unavailable: {exc}") from exc
    return lambda window: model(window, num_samples=VAD_BLOCK)


def record_until_silence(
    should_stop: Callable[[], bool] = lambda: False,
    wait_seconds: float = LISTEN_WAIT,
    end_silence: float = END_SILENCE,
    speech_prob: Callable | None = None,
):
    """Record until the speaker pauses (or `should_stop()` turns true).

    Returns 16 kHz float32 audio, empty if nobody spoke within `wait_seconds`.
    """
    import queue

    try:
        import numpy as np
        import sounddevice as sd
    except (ImportError, OSError) as exc:
        raise SpeechInputError(
            "Microphone support is not installed. Run: "
            "python -m pip install -r requirements.txt"
        ) from exc

    endpointer = Endpointer(speech_prob or load_vad(), wait_seconds=wait_seconds,
                            end_silence=end_silence)
    incoming: queue.Queue = queue.Queue()

    def collect(indata, frames, time_info, status):
        incoming.put(indata[:, 0].copy())

    pending = np.zeros(0, dtype=np.float32)
    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                            blocksize=VAD_BLOCK, callback=collect):
            while not should_stop():
                try:
                    pending = np.concatenate([pending, incoming.get(timeout=0.1)])
                except queue.Empty:
                    continue
                while len(pending) >= VAD_BLOCK:
                    if endpointer.feed(pending[:VAD_BLOCK]):
                        return endpointer.audio()
                    pending = pending[VAD_BLOCK:]
    except sd.PortAudioError as exc:
        raise SpeechInputError(f"Could not use the microphone: {exc}") from exc
    return endpointer.audio(everything=True)  # stopped by hand: "done talking"


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
        record_auto: Callable = record_until_silence,
    ) -> None:
        self._model = load_model()  # Slow part: done once, not per message.
        self._record = record
        self._record_auto = record_auto

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

    def listen_until_silence(self, should_stop: Callable[[], bool], wait_seconds: float = LISTEN_WAIT) -> str:
        """Hands-free: record until the speaker pauses; '' if nobody spoke."""
        return self.transcribe(self._record_auto(should_stop, wait_seconds))


if __name__ == "__main__":
    try:
        print(f"Loading speech model '{STT_MODEL}' on {STT_DEVICE} (first run downloads it)...")
        listener = Listener()
        if "--hands-free" in sys.argv:
            print("Speak now; I'll stop when you pause.")
            audio = record_until_silence()
        else:
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
