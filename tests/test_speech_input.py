"""Tests for backend.speech_input with a fake Whisper model and fake microphone."""

from types import SimpleNamespace

import numpy as np

from backend.speech_input import SAMPLE_RATE, Listener


class FakeWhisper:
    def __init__(self, texts=(" Hello", " PARKER. ")):
        self.texts = texts
        self.calls = []

    def transcribe(self, audio, **options):
        self.calls.append((audio, options))
        return (SimpleNamespace(text=t) for t in self.texts), SimpleNamespace()


def seconds(n):
    return np.zeros(int(SAMPLE_RATE * n), dtype=np.float32)


def make_listener(model=None, audio=None):
    model = model or FakeWhisper()
    loads = []

    def load():
        loads.append(1)
        return model

    listener = Listener(load_model=load, record=lambda: audio if audio is not None else seconds(2))
    return listener, model, loads


def test_segments_are_joined_into_one_clean_sentence():
    listener, _, _ = make_listener()
    assert listener.transcribe(seconds(2)) == "Hello PARKER."


def test_whisper_is_asked_for_english_with_silence_filtering():
    listener, model, _ = make_listener()
    listener.transcribe(seconds(2))
    options = model.calls[0][1]
    assert options["language"] == "en"
    assert options["vad_filter"] is True


def test_very_short_recordings_are_ignored_without_calling_whisper():
    listener, model, _ = make_listener()
    assert listener.transcribe(seconds(0.1)) == ""
    assert model.calls == []


def test_listen_records_then_transcribes():
    listener, model, _ = make_listener(audio=seconds(1))
    assert listener.listen() == "Hello PARKER."
    assert len(model.calls[0][0]) == SAMPLE_RATE


def test_model_is_loaded_once():
    listener, _, loads = make_listener()
    listener.listen()
    listener.listen()
    assert loads == [1]


def test_silence_gives_empty_text():
    listener, _, _ = make_listener(model=FakeWhisper(texts=()))
    assert listener.listen() == ""


def test_model_load_failure_becomes_a_friendly_error(monkeypatch):
    import faster_whisper
    import pytest

    from backend import speech_input

    def offline(*args, **kwargs):
        raise OSError("network unreachable")

    monkeypatch.setattr(faster_whisper, "WhisperModel", offline)
    with pytest.raises(speech_input.SpeechInputError, match="needs internet"):
        speech_input.load_whisper()
