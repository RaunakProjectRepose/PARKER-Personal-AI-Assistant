"""Tests for backend.speech_output with a fake voice and fake speakers."""

import io
import wave
from types import SimpleNamespace

import pytest

from backend.speech_output import Speaker, SpeechError

VOICE = "en_GB-test-medium"


class FakeVoice:
    """Mimics Piper: whole-WAV synthesis and sentence-by-sentence chunks."""

    def __init__(self):
        self.texts = []
        self.configs = []
        self.config = SimpleNamespace(sample_rate=22050, length_scale=1.0)

    def synthesize_wav(self, text, wav_file, syn_config=None):
        self.texts.append(text)
        self.configs.append(syn_config)
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x00\x00" * 2205)

    def synthesize(self, text, syn_config=None):
        self.texts.append(text)
        self.configs.append(syn_config)
        for sentence in text.split(". "):
            yield SimpleNamespace(audio_int16_bytes=sentence.encode())


class FakeStream:
    def __init__(self):
        self.played = []
        self.closed = False

    def play(self, chunks):
        self.played.append(list(chunks))

    def close(self):
        self.closed = True


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


# ---- streaming playback ------------------------------------------------------

def stream_speaker(voices_dir, **kwargs):
    voice, stream = FakeVoice(), FakeStream()
    speaker = Speaker(
        VOICE, voices_dir, load_voice=lambda p: voice, stream_player=stream, audio="stream", **kwargs
    )
    return speaker, voice, stream


def test_stream_mode_plays_sentence_by_sentence_after_a_short_lead_in(voices_dir):
    speaker, voice, stream = stream_speaker(voices_dir)
    speaker.speak("First sentence. Second one")
    chunks = stream.played[0]
    assert speaker.mode == "stream"
    assert speaker.lead_in_seconds == 0.2  # default for the always-open stream
    assert chunks[0] == b"\x00\x00" * int(22050 * 0.2)
    assert chunks[1:] == [b"First sentence", b"Second one"]
    assert speaker.last_first_audio_s is not None


def test_stream_mode_without_lead_in(voices_dir):
    speaker, _, stream = stream_speaker(voices_dir, lead_in_seconds=0)
    speaker.speak("Hi")
    assert stream.played[0] == [b"Hi"]


def test_stream_is_opened_with_the_voice_sample_rate_and_closed(voices_dir):
    opened = []

    def open_stream(rate):
        opened.append(rate)
        return FakeStream()

    speaker = Speaker(VOICE, voices_dir, load_voice=lambda p: FakeVoice(), open_stream=open_stream, audio="stream")
    assert opened == [22050]
    speaker.close()
    assert speaker._stream.closed


def test_falls_back_to_whole_reply_playback_if_the_stream_fails(voices_dir):
    def broken(rate):
        raise SpeechError("PortAudio library not found")

    speaker = Speaker(VOICE, voices_dir, load_voice=lambda p: FakeVoice(), open_stream=broken, audio="stream")
    assert speaker.mode == "winsound"
    assert speaker.lead_in_seconds == 1.0
    assert "PortAudio library not found" in speaker.fallback_note


def test_winsound_mode_can_be_chosen(voices_dir):
    played = []
    speaker = Speaker(VOICE, voices_dir, load_voice=lambda p: FakeVoice(), play=played.append, audio="winsound")
    speaker.speak("Hello.")
    assert speaker.mode == "winsound" and played[0][:4] == b"RIFF"


# ---- speed and rhythm --------------------------------------------------------

def test_default_settings_leave_the_voice_untouched(voices_dir):
    speaker, voice, _ = stream_speaker(voices_dir)
    speaker.speak("Hi")
    assert voice.configs == [None]


def test_speed_and_variation_reach_piper(voices_dir):
    made = []

    def make_config(length_scale, noise_w_scale):
        made.append((length_scale, noise_w_scale))
        return "CONFIG"

    speaker, voice, _ = stream_speaker(voices_dir, speed=0.8, variation=0.7, make_config=make_config)
    speaker.speak("Hi")
    assert made == [(1.25, 0.7)]  # slower speed = longer length_scale
    assert voice.configs == ["CONFIG"]


def test_speed_must_be_positive(voices_dir):
    with pytest.raises(ValueError):
        stream_speaker(voices_dir, speed=0)


def test_stream_player_writes_every_chunk_in_order(monkeypatch):
    """Exercise the real StreamPlayer threading with a fake sound card."""
    import sys
    import types

    import numpy as np

    from backend.speech_output import StreamPlayer

    written = []

    class FakeOutputStream:
        latency = 0.0

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            pass

        def write(self, data):
            written.append(data.tobytes())

        def stop(self):
            pass

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(OutputStream=FakeOutputStream))
    player = StreamPlayer(22050)
    assert player._stream.kwargs == {"samplerate": 22050, "channels": 1, "dtype": "int16", "latency": "high"}
    chunks = [np.array([i, i], dtype=np.int16).tobytes() for i in range(40)]
    player.play(iter(chunks))
    assert written == chunks
    player.close()


def test_stream_player_reports_playback_errors(monkeypatch):
    import sys
    import types

    from backend.speech_output import StreamPlayer

    class BrokenStream:
        latency = 0.0

        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

        def write(self, data):
            raise RuntimeError("device unplugged")

    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(OutputStream=BrokenStream))
    player = StreamPlayer(22050)
    with pytest.raises(SpeechError, match="device unplugged"):
        player.play([b"\x00\x00"] * 5)
