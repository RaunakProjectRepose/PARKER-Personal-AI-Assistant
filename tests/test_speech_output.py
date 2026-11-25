"""Tests for backend.speech_output with a fake voice and fake speakers."""

import io
import wave

import pytest

from backend.speech_output import Speaker, SpeechError

VOICE = "en_GB-test-medium"


class FakeVoice:
    """Writes 0.1 s of silence per call, like Piper's synthesize_wav()."""

    def __init__(self):
        self.texts = []

    def synthesize_wav(self, text, wav_file):
        self.texts.append(text)
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x00\x00" * 2205)


@pytest.fixture
def voices_dir(tmp_path):
    (tmp_path / f"{VOICE}.onnx").write_bytes(b"model")
    (tmp_path / f"{VOICE}.onnx.json").write_text("{}")
    return tmp_path


def make_speaker(voices_dir, played=None, voice=None, lead_in=0.0):
    voice = voice or FakeVoice()
    played = played if played is not None else []
    loaded = []

    def load(path):
        loaded.append(path)
        return voice

    speaker = Speaker(
        VOICE, voices_dir, load_voice=load, play=played.append, lead_in_seconds=lead_in
    )
    return speaker, voice, played, loaded


def test_voice_is_loaded_once_from_the_voices_folder(voices_dir):
    speaker, _, _, loaded = make_speaker(voices_dir)
    speaker.speak("One")
    speaker.speak("Two")
    assert loaded == [voices_dir / f"{VOICE}.onnx"]


def test_synthesize_returns_a_valid_wav(voices_dir):
    speaker, voice, _, _ = make_speaker(voices_dir)
    wav_bytes = speaker.synthesize("  Hello.  ")
    with wave.open(io.BytesIO(wav_bytes)) as wav:
        assert wav.getframerate() == 22050
        assert wav.getnframes() == 2205
    assert voice.texts == ["Hello."]


def test_speak_plays_the_audio(voices_dir):
    played = []
    speaker, _, _, _ = make_speaker(voices_dir, played=played)
    speaker.speak("Hello.")
    assert len(played) == 1
    assert played[0][:4] == b"RIFF"  # WAV files start with "RIFF"


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_text_is_rejected(voices_dir, bad):
    speaker, _, _, _ = make_speaker(voices_dir)
    with pytest.raises(ValueError):
        speaker.synthesize(bad)


def test_missing_voice_files_give_download_instructions(tmp_path):
    with pytest.raises(SpeechError, match="download_voices en_GB-test-medium"):
        Speaker(VOICE, tmp_path, load_voice=lambda p: FakeVoice(), play=lambda b: None)


def test_missing_config_file_is_reported(voices_dir):
    (voices_dir / f"{VOICE}.onnx.json").unlink()
    with pytest.raises(SpeechError, match=r"\.onnx\.json"):
        make_speaker(voices_dir)


def test_lead_in_silence_is_added_before_speech(voices_dir):
    speaker, _, _, _ = make_speaker(voices_dir, lead_in=0.5)
    with wave.open(io.BytesIO(speaker.synthesize("Hello."))) as wav:
        assert wav.getnframes() == 2205 + 11025  # speech + 0.5 s of silence
        assert wav.getframerate() == 22050
        assert wav.readframes(11025) == b"\x00\x00" * 11025


def test_negative_lead_in_is_rejected(voices_dir):
    with pytest.raises(ValueError):
        make_speaker(voices_dir, lead_in=-1)
