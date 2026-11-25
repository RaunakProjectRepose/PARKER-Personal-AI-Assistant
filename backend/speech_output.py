"""PARKER's voice: turns reply text into speech with Piper TTS.

Voice: en_GB-alba-medium (dataset licence CC BY 4.0, see docs/CREDITS.md).
Voice files live in the `voices/` folder, which Git ignores. To fetch them:

    python -m piper.download_voices en_GB-alba-medium --data-dir voices

Quick manual tests, from the project folder:

    python -m backend.speech_output "Good evening. All systems are ready."
    python -m backend.speech_output --compare     # hear speed/rhythm options
    python -m backend.speech_output --names       # hear ways to say your name

How playback works (default, PARKER_AUDIO=stream): one audio stream is opened
when PARKER starts and kept open, so the sound device never falls asleep
between replies. Piper produces the reply one sentence at a time; the first
sentence starts playing while the next ones are still being generated.
PARKER_AUDIO=winsound uses the older whole-reply playback instead.
"""

from __future__ import annotations

import io
import os
import queue
import re
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VOICE_NAME = os.environ.get("PARKER_VOICE", "en_GB-alba-medium")
VOICES_DIR = Path(os.environ.get("PARKER_VOICES_DIR", PROJECT_ROOT / "voices"))
AUDIO_BACKEND = os.environ.get("PARKER_AUDIO", "stream")  # "stream" or "winsound"
# 1.0 = the voice's normal pace; 0.9 is a little slower, 1.1 a little faster.
SPEED = float(os.environ.get("PARKER_VOICE_SPEED", "1.0"))
# Rhythm variation between words (Piper's noise_w). 0.8 was picked by ear as
# the most natural for Alba; higher sounds uneven, lower more robotic.
VARIATION = float(os.environ.get("PARKER_VOICE_VARIATION", "0.8"))
# British pronunciation rules misread some names, so the voice is given a
# respelling while the screen keeps the real spelling. Pick one by ear with:
#     python -m backend.speech_output --names
OWNER_NAME = os.environ.get("PARKER_OWNER_NAME", "Raunak")
OWNER_SPOKEN = os.environ.get("PARKER_OWNER_SPOKEN") or (
    "Rawnak" if OWNER_NAME == "Raunak" else OWNER_NAME
)
DEFAULT_PRONUNCIATIONS = {OWNER_NAME: OWNER_SPOKEN} if OWNER_SPOKEN != OWNER_NAME else {}
# Silence before each reply so the audio device is awake for the first word.
# Whole-reply playback needs about 1 s; the always-open stream needs very little.
_lead_in = os.environ.get("PARKER_VOICE_LEAD_IN")
LEAD_IN_SECONDS = float(_lead_in) if _lead_in else None
DEFAULT_LEAD_IN = {"stream": 0.2, "winsound": 1.0}


class SpeechError(Exception):
    """Raised when PARKER cannot speak."""


def play_wav_windows(wav_bytes: bytes) -> None:
    """Play a whole WAV through the speakers with `winsound` (built into Python on Windows)."""
    try:
        import winsound
    except ImportError as exc:  # Not on Windows.
        raise SpeechError("winsound playback is only available on Windows.") from exc
    winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)


class StreamPlayer:
    """An always-open audio output stream that plays 16-bit mono audio chunks.

    A background thread writes audio to the sound card while the caller is
    still generating the next sentence, so speech flows without gaps.
    """

    def __init__(self, sample_rate: int) -> None:
        try:
            import numpy as np
            import sounddevice as sd
        except (ImportError, OSError) as exc:
            raise SpeechError(f"Streaming audio is unavailable: {exc}") from exc
        self._np = np
        self._stop = threading.Event()
        try:
            # "high" latency = bigger buffers: smoother on Bluetooth and busy CPUs.
            self._stream = sd.OutputStream(
                samplerate=sample_rate, channels=1, dtype="int16", latency="high"
            )
            self._stream.start()
        except Exception as exc:
            raise SpeechError(f"Could not open the speakers: {exc}") from exc

    # Audio is written in small slices so a stop request takes effect quickly.
    SLICE_SAMPLES = 2048

    def play(self, chunks: Iterable[bytes]) -> None:
        """Play the chunks in order; returns when the audio has finished or was stopped."""
        self._stop.clear()
        pending: queue.Queue = queue.Queue(maxsize=16)
        errors: list[Exception] = []

        def writer() -> None:
            while True:
                data = pending.get()
                if data is None:
                    return
                if errors or self._stop.is_set():
                    continue  # Drain the queue after a failure or a stop.
                samples = self._np.frombuffer(data, dtype=self._np.int16)
                try:
                    for start in range(0, len(samples), self.SLICE_SAMPLES):
                        if self._stop.is_set():
                            break
                        self._stream.write(samples[start : start + self.SLICE_SAMPLES])
                except Exception as exc:
                    errors.append(exc)

        thread = threading.Thread(target=writer, daemon=True)
        thread.start()
        try:
            for chunk in chunks:  # Generating the next sentence overlaps with playback.
                if self._stop.is_set():
                    break
                pending.put(chunk)
        finally:
            pending.put(None)
            thread.join()
        if errors:
            raise SpeechError(f"Audio playback failed: {errors[0]}")
        if not self._stop.is_set():
            time.sleep(self._stream.latency)  # Let the last buffered audio reach the speakers.

    def stop(self) -> None:
        """Stop the current reply within a fraction of a second. Safe from any thread."""
        self._stop.set()

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


def load_piper_voice(model_path: Path):
    """Load a Piper voice. Imported lazily so text-only PARKER never needs Piper."""
    try:
        from piper import PiperVoice
    except ImportError as exc:
        raise SpeechError(
            "Piper is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc
    return PiperVoice.load(model_path)


def piper_synthesis_config(length_scale: float | None, noise_w_scale: float | None):
    from piper.config import SynthesisConfig

    return SynthesisConfig(length_scale=length_scale, noise_w_scale=noise_w_scale)


def _silence(seconds: float, sample_rate: int) -> bytes:
    return b"\x00\x00" * int(sample_rate * seconds)


def _with_lead_in(wav_bytes: bytes, seconds: float) -> bytes:
    """Return the same WAV audio with `seconds` of silence added at the start."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as src:
        params = src.getparams()
        frames = src.readframes(params.nframes)
    silent_frames = int(params.framerate * seconds)
    silence = b"\x00" * (silent_frames * params.sampwidth * params.nchannels)
    out = io.BytesIO()
    with wave.open(out, "wb") as dst:
        dst.setnchannels(params.nchannels)
        dst.setsampwidth(params.sampwidth)
        dst.setframerate(params.framerate)
        dst.writeframes(silence + frames)
    return out.getvalue()


class Speaker:
    """Speaks text aloud with one Piper voice, loaded once and reused."""

    def __init__(
        self,
        voice_name: str = VOICE_NAME,
        voices_dir: Path = VOICES_DIR,
        *,
        load_voice: Callable = load_piper_voice,
        play: Callable[[bytes], None] | None = None,
        stream_player=None,
        open_stream: Callable[[int], object] = StreamPlayer,
        audio: str = AUDIO_BACKEND,
        lead_in_seconds: float | None = LEAD_IN_SECONDS,
        speed: float = SPEED,
        variation: float | None = VARIATION,
        make_config: Callable = piper_synthesis_config,
        pronunciations: dict[str, str] | None = None,
    ) -> None:
        if lead_in_seconds is not None and lead_in_seconds < 0:
            raise ValueError("lead_in_seconds must not be negative")
        if speed <= 0:
            raise ValueError("speed must be positive")
        model_path = Path(voices_dir) / f"{voice_name}.onnx"
        config_path = model_path.with_name(model_path.name + ".json")
        missing = [p.name for p in (model_path, config_path) if not p.exists()]
        if missing:
            raise SpeechError(
                f"Voice files not found in {voices_dir}: {', '.join(missing)}. "
                f"Download them with: python -m piper.download_voices "
                f"{voice_name} --data-dir voices"
            )
        self.voice_name = voice_name
        self.pronunciations = (
            DEFAULT_PRONUNCIATIONS if pronunciations is None else pronunciations
        )
        self._voice = load_voice(model_path)  # Slow part: done once, not per reply.
        voice_config = getattr(self._voice, "config", None)
        self.sample_rate = getattr(voice_config, "sample_rate", 22050)

        # Speed and rhythm. None means "use the voice's own default".
        self._syn_config = None
        if speed != 1.0 or variation is not None:
            base = getattr(voice_config, "length_scale", None) or 1.0
            self._syn_config = make_config(
                base / speed if speed != 1.0 else None, variation
            )

        # Choose how to play audio.
        self.fallback_note = ""
        self._play = play
        self._stream = stream_player
        mode = "winsound" if (play is not None or audio == "winsound") else "stream"
        if mode == "stream" and self._stream is None:
            try:
                self._stream = open_stream(self.sample_rate)
            except SpeechError as err:
                mode = "winsound"
                self.fallback_note = f"{err} Using whole-reply playback instead."
        if mode == "winsound" and self._play is None:
            self._play = play_wav_windows
        self.mode = mode
        self.lead_in_seconds = (
            DEFAULT_LEAD_IN[mode] if lead_in_seconds is None else lead_in_seconds
        )
        self.last_first_audio_s: float | None = None  # For --timing.

    def synthesize(self, text: str) -> bytes:
        """Return `text` spoken as a complete WAV file, in memory."""
        text = self._check(text)
        speech = io.BytesIO()
        with wave.open(speech, "wb") as wav_file:
            self._voice.synthesize_wav(text, wav_file, syn_config=self._syn_config)
        if self.lead_in_seconds == 0:
            return speech.getvalue()
        return _with_lead_in(speech.getvalue(), self.lead_in_seconds)

    def sentences(self, text: str) -> Iterable[bytes]:
        """Yield `text` as raw 16-bit audio, one sentence at a time, lead-in first."""
        text = self._check(text)
        start = time.monotonic()
        self.last_first_audio_s = None
        if self.lead_in_seconds:
            yield _silence(self.lead_in_seconds, self.sample_rate)
        for chunk in self._voice.synthesize(text, syn_config=self._syn_config):
            if self.last_first_audio_s is None:
                self.last_first_audio_s = time.monotonic() - start
            yield chunk.audio_int16_bytes

    def speak(self, text: str) -> None:
        """Say `text` out loud. Returns when PARKER has finished speaking."""
        if self.mode == "stream":
            self._stream.play(self.sentences(text))
        else:
            start = time.monotonic()
            wav = self.synthesize(text)
            self.last_first_audio_s = time.monotonic() - start
            self._play(wav)

    def stop(self) -> None:
        """Stop speaking (stream playback only). Safe to call from another thread."""
        if self._stream is not None and hasattr(self._stream, "stop"):
            self._stream.stop()

    def close(self) -> None:
        if self._stream is not None and hasattr(self._stream, "close"):
            self._stream.close()

    def _check(self, text: str) -> str:
        if not text or not text.strip():
            raise ValueError("text must not be empty")
        return self.respell(text.strip())

    def respell(self, text: str) -> str:
        """Swap words the voice mispronounces for respellings ("Raunak" -> "Rawnak")."""
        for word, spoken in self.pronunciations.items():
            text = re.sub(rf"\b{re.escape(word)}\b", spoken, text, flags=re.IGNORECASE)
        return text


COMPARE_SENTENCE = (
    "Good evening, Raunak. You made real progress today. "
    "Shall we pick up the desktop app next?"
)
COMPARE_SETTINGS = [
    ("1  normal", 1.0, None),
    ("2  slightly slower", 0.9, None),
    ("3  more natural rhythm", 1.0, 0.8),
    ("4  slower + natural rhythm", 0.9, 0.8),
]


NAME_CANDIDATES = ["Raunak", "Rawnak", "Rawnuck", "Rownuck", "Raw-nuk", "Ronuck"]


def compare_names() -> None:
    """Say the owner's name several ways so the closest can be chosen."""
    speaker = Speaker(pronunciations={})
    for number, spelling in enumerate(NAME_CANDIDATES, start=1):
        print(f"Option {number}: {spelling}   (PARKER_OWNER_SPOKEN={spelling})")
        speaker.speak(f"Good evening, {spelling}. Nice to see you.")
        time.sleep(0.6)
    speaker.close()


def compare() -> None:
    """Play the same sentence with a few settings so you can pick by ear."""
    for label, speed, variation in COMPARE_SETTINGS:
        print(f"Option {label}  (PARKER_VOICE_SPEED={speed}"
              + (f", PARKER_VOICE_VARIATION={variation})" if variation else ")"))
        speaker = Speaker(speed=speed, variation=variation)
        speaker.speak(COMPARE_SENTENCE)
        speaker.close()
        time.sleep(0.5)


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--compare"]:
            compare()
        elif sys.argv[1:] == ["--names"]:
            compare_names()
        else:
            sentence = " ".join(sys.argv[1:]) or "Good evening. I'm PARKER. All systems are ready."
            speaker = Speaker()
            if speaker.fallback_note:
                print(f"[voice] {speaker.fallback_note}")
            print(f"[voice] playback: {speaker.mode}")
            speaker.speak(sentence)
            print(f"[voice] first audio ready after {speaker.last_first_audio_s:.2f} s")
            speaker.close()
    except SpeechError as err:
        print(f"PARKER voice error: {err}", file=sys.stderr)
        sys.exit(1)
