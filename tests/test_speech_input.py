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


# ---- hands-free listening ---------------------------------------------------

from backend.speech_input import BLOCK_SECONDS, VAD_BLOCK, Endpointer  # noqa: E402


def scripted_vad(probs):
    """A fake voice detector that scores each new block from a list."""
    scores = iter(probs)
    seen = []

    def prob(window):
        assert len(window) % VAD_BLOCK == 0
        seen.append(len(window))
        return np.full(len(window) // VAD_BLOCK, next(scores), dtype=np.float32)

    return prob, seen


def blocks(n):
    return int(round(n / BLOCK_SECONDS))


def run(endpointer, count):
    result = None
    for i in range(count):
        result = endpointer.feed(np.full(VAD_BLOCK, i, dtype=np.float32))
        if result:
            return result, i + 1
    return result, count


def test_stops_after_a_pause_once_speech_has_started():
    probs = [0.0] * blocks(1) + [0.9] * blocks(2) + [0.1] * blocks(5)
    vad, seen = scripted_vad(probs)
    endpointer = Endpointer(vad, wait_seconds=8, end_silence=1.2)
    result, fed = run(endpointer, len(probs))
    assert result == "done"
    assert fed == blocks(1) + blocks(2) + blocks(1.2)  # stops 1.2 s into the pause
    audio = endpointer.audio()
    # Speech plus ~0.5 s lead-in, not the whole second of silence before it.
    assert len(audio) == (blocks(2) + blocks(1.2) + blocks(0.5)) * VAD_BLOCK
    assert max(seen) <= 16 * VAD_BLOCK  # the detector only sees a short recent window


def test_short_pauses_and_unsure_blocks_do_not_end_the_message():
    probs = [0.9] * 10 + [0.1] * blocks(0.8) + [0.4] * 5 + [0.9] * 10 + [0.1] * blocks(1.2)
    vad, _ = scripted_vad(probs)
    result, fed = run(Endpointer(vad, end_silence=1.2), len(probs))
    assert (result, fed) == ("done", len(probs))


def test_a_click_is_not_speech():
    probs = [0.9] * 3 + [0.0] * blocks(3)  # ~0.1 s blip
    vad, _ = scripted_vad(probs)
    endpointer = Endpointer(vad, wait_seconds=2)
    result, _ = run(endpointer, len(probs))
    assert result == "timeout"
    assert len(endpointer.audio()) == 0


def test_gives_up_when_nobody_speaks():
    vad, _ = scripted_vad([0.0] * blocks(10))
    result, fed = run(Endpointer(vad, wait_seconds=3), blocks(10))
    assert (result, fed) == ("timeout", blocks(3))


def test_long_speech_is_cut_at_the_safety_limit():
    vad, _ = scripted_vad([0.9] * blocks(40))
    result, fed = run(Endpointer(vad, max_seconds=30), blocks(40))
    assert result == "done" and fed == blocks(30)


def test_manual_stop_keeps_everything_for_whisper_to_judge():
    vad, _ = scripted_vad([0.0] * 20)
    endpointer = Endpointer(vad)
    run(endpointer, 20)
    assert len(endpointer.audio()) == 0
    assert len(endpointer.audio(everything=True)) == 20 * VAD_BLOCK


def test_listener_hands_free_uses_the_silence_recorder():
    model = FakeWhisper(texts=(" What's on today?",))
    calls = []

    def record_auto(should_stop, wait_seconds):
        calls.append((should_stop(), wait_seconds))
        return seconds(1.5)

    listener = Listener(load_model=lambda: model, record=lambda: seconds(0), record_auto=record_auto)
    assert listener.listen_until_silence(lambda: False, 6) == "What's on today?"
    assert calls == [(False, 6)]


def test_real_voice_detector_scores_silence_as_not_speech():
    pytest = __import__("pytest")
    pytest.importorskip("faster_whisper")
    pytest.importorskip("onnxruntime")
    from backend.speech_input import load_vad

    vad = load_vad()
    scores = vad(np.zeros(VAD_BLOCK * 16, dtype=np.float32))
    assert len(scores) == 16 and float(scores[-1]) < 0.2
