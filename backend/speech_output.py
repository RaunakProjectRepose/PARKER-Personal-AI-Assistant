"""PARKER's voice: turns reply text into speech with Piper TTS.

Voice: en_GB-alba-medium (dataset licence CC BY 4.0, see docs/CREDITS.md).
Voice files live in the `voices/` folder, which Git ignores. To fetch them:

    python -m piper.download_voices en_GB-alba-medium --data-dir voices

Quick manual test, from the project folder:

    python -m backend.speech_output "Good evening. All systems are ready."
"""

from __future__ import annotations

import io
import os
import sys
import wave
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VOICE_NAME = os.environ.get("PARKER_VOICE", "en_GB-alba-medium")
VOICES_DIR = Path(os.environ.get("PARKER_VOICES_DIR", PROJECT_ROOT / "voices"))
# Windows audio devices (especially Bluetooth) sleep when idle and need a
# moment to wake up, which cuts off the first words. Silence played before
# each reply gives them that moment. Tune with PARKER_VOICE_LEAD_IN (seconds).
LEAD_IN_SECONDS = float(os.environ.get("PARKER_VOICE_LEAD_IN", "1.0"))


class SpeechError(Exception):
    """Raised when PARKER cannot speak."""


def play_wav_windows(wav_bytes: bytes) -> None:
    """Play WAV audio through the speakers and wait until it finishes.

    Uses `winsound`, which ships with Python on Windows, so no extra
    audio library is needed.
    """
    try:
        import winsound
    except ImportError as exc:  # Not on Windows.
        raise SpeechError("Audio playback is only set up for Windows so far.") from exc
    winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)


def load_piper_voice(model_path: Path):
    """Load a Piper voice. Imported lazily so text-only PARKER never needs Piper."""
    try:
        from piper import PiperVoice
    except ImportError as exc:
        raise SpeechError(
            "Piper is not installed. Run: python -m pip install -r requirements.txt"
        ) from exc
    return PiperVoice.load(model_path)


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
        play: Callable[[bytes], None] = play_wav_windows,
        lead_in_seconds: float = LEAD_IN_SECONDS,
    ) -> None:
        if lead_in_seconds < 0:
            raise ValueError("lead_in_seconds must not be negative")
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
        self._voice = load_voice(model_path)  # Slow part: done once, not per reply.
        self._play = play
        self.lead_in_seconds = lead_in_seconds

    def synthesize(self, text: str) -> bytes:
        """Return `text` spoken as a complete WAV file, in memory."""
        if not text or not text.strip():
            raise ValueError("text must not be empty")
        speech = io.BytesIO()
        with wave.open(speech, "wb") as wav_file:
            self._voice.synthesize_wav(text.strip(), wav_file)
        if self.lead_in_seconds == 0:
            return speech.getvalue()
        return _with_lead_in(speech.getvalue(), self.lead_in_seconds)

    def speak(self, text: str) -> None:
        """Say `text` out loud. Returns when PARKER has finished speaking."""
        self._play(self.synthesize(text))


if __name__ == "__main__":
    sentence = " ".join(sys.argv[1:]) or "Good evening. I'm PARKER. All systems are ready."
    try:
        Speaker().speak(sentence)
    except SpeechError as err:
        print(f"PARKER voice error: {err}", file=sys.stderr)
        sys.exit(1)
