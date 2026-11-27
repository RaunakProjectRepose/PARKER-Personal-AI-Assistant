"""Tests for backend.wake_word with a fake microphone, voice detector and Whisper."""

import numpy as np
import pytest

from backend.speech_input import BLOCK_SECONDS, VAD_BLOCK
from backend.wake_word import WakeWordDetector, find_wake_word


@pytest.mark.parametrize("heard, rest", [
    ("Hey Parker.", ""),
    ("Hey, Parker!", ""),
    ("Parker?", ""),
    ("Okay Parker, what's on today?", "what's on today?"),
    ("Hey Parker what's the time", "what's the time"),
    ("Parker, remind me in 5 minutes to stretch.", "remind me in 5 minutes to stretch."),
    ("Hey Parka.", ""),  # how Whisper often writes a quick "Parker"
    ("Hi Barker, open Spotify", "open Spotify"),
    ("Hey park her.", ""),
])
def test_calling_parker_wakes_it(heard, rest):
    assert find_wake_word(heard) == rest


@pytest.mark.parametrize("heard", [
    "I told Parker about it.",
    "Peter Parker is Spider-Man.",
    "Let's go to the park.",
    "Hey, how are you?",
    "",
])
def test_ordinary_speech_does_not(heard):
    assert find_wake_word(heard) is None


# ---- the listening loop -------------------------------------------------------

def blocks(seconds, level):
    return [np.full(VAD_BLOCK, level, dtype=np.float32) for _ in range(round(seconds / BLOCK_SECONDS))]


class FakeMicrophone:
    """Plays scripted blocks, then stops the detector so the loop ends."""

    def __init__(self, script, detector_ref):
        self.script = list(script)
        self.detector_ref = detector_ref
        self.opened = 0

    def __call__(self):
        self.opened += 1
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, timeout):
        if self.script:
            return self.script.pop(0)
        self.detector_ref[0]._stopped.set()
        return None


def speech_prob(window):
    """Blocks filled with 1.0 count as speech, 0.0 as silence."""
    return window.reshape(-1, VAD_BLOCK)[:, 0]


def make_detector(script, transcripts):
    woke, heard_audio = [], []
    ref = [None]
    texts = list(transcripts)

    def transcribe(audio):
        heard_audio.append(len(audio))
        return texts.pop(0)

    mic = FakeMicrophone(script, ref)
    detector = WakeWordDetector(woke.append, transcribe=transcribe, speech_prob=speech_prob,
                                open_stream=mic)
    ref[0] = detector
    return detector, woke, heard_audio, mic


def test_wakes_on_the_name_and_passes_on_the_request():
    script = blocks(1, 0.0) + blocks(1.5, 1.0) + blocks(1, 0.0)
    detector, woke, heard, _ = make_detector(script, ["Hey Parker, what's on today?"])
    detector._listen_until_paused()
    assert woke == ["what's on today?"]
    assert detector.paused  # stops listening for the name while PARKER answers
    assert len(heard) == 1 and heard[0] < 2.5 * 16000  # only the speech is transcribed


def test_other_speech_is_dropped_and_listening_continues():
    script = (blocks(1, 1.0) + blocks(1, 0.0)  # someone talking
              + blocks(0.6, 1.0) + blocks(1, 0.0))  # then the name
    detector, woke, heard, _ = make_detector(script, ["Is the kettle on?", "Hey Parker."])
    detector._listen_until_paused()
    assert woke == [""] and len(heard) == 2


def test_silence_and_clicks_are_never_transcribed():
    script = blocks(3, 0.0) + blocks(0.1, 1.0) + blocks(6, 0.0)
    detector, woke, heard, _ = make_detector(script, [])
    detector._listen_until_paused()
    assert woke == [] and heard == []


def test_long_speech_is_checked_but_capped():
    script = blocks(14, 1.0) + blocks(1, 0.0)
    detector, woke, heard, _ = make_detector(script, ["a long story", "about something"])
    detector._listen_until_paused()
    assert woke == [] and heard and max(heard) <= 10.1 * 16000


def test_paused_detector_releases_the_microphone():
    detector, woke, heard, mic = make_detector(blocks(2, 1.0), ["Hey Parker"])
    detector.pause()
    detector._listen_until_paused()  # returns at once without reading
    assert mic.script and woke == []


def test_load_failure_is_reported_not_raised():
    from backend.speech_input import SpeechInputError

    errors = []
    detector = WakeWordDetector(lambda rest: None, on_error=errors.append,
                                speech_prob=speech_prob, transcribe=None)

    def broken_load():
        raise SpeechInputError("no model")

    detector.load = broken_load
    detector.start()
    detector._thread.join(2)
    assert errors == ["no model"] and not detector.running
