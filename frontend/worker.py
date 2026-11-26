"""Runs PARKER's slow work (model, microphone, voice) off the window's thread,
so the window never freezes. The window talks to it only through Qt signals,
and it handles one job at a time, in order."""

from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import QObject, Signal, Slot

from backend.assistant import Assistant
from backend.brain import BrainError


def default_speaker():
    from backend.speech_output import Speaker

    return Speaker()


def default_listener(wait_for_stop: Callable[[str], object]):
    from backend.speech_input import Listener, record_until_enter

    return Listener(record=lambda: record_until_enter(wait_for_enter=wait_for_stop))


class Worker(QObject):
    status_changed = Signal(str)  # loading / idle / listening / thinking / speaking
    loaded = Signal(bool, bool, str)  # voice ready, microphone ready, notes
    heard = Signal(str)  # what the microphone picked up ("" if nothing)
    replied = Signal(str)  # PARKER's answer from the model
    failed = Signal(str)  # a readable error message
    files_found = Signal(str, list)  # the query, a list of FoundFile
    calendar_updated = Signal()  # Google Calendar cache refreshed or changed

    def __init__(
        self,
        assistant: Assistant,
        make_speaker: Callable[[], object] | None = default_speaker,
        make_listener: Callable[[Callable], object] | None = default_listener,
        finder=None,
        calendar=None,
    ) -> None:
        super().__init__()
        self.assistant = assistant
        self.finder = finder
        self.calendar = calendar
        self._make_speaker = make_speaker
        self._make_listener = make_listener
        self.speaker = None
        self.listener = None
        self.voice_enabled = True
        self._stop_listening = threading.Event()

    # ---- called through signals (run on the worker thread) -------------------
    @Slot()
    def load(self) -> None:
        """Load the voice and speech recognition once; they are slow to start."""
        self.status_changed.emit("loading")
        notes = []
        if self._make_speaker is not None:
            try:
                self.speaker = self._make_speaker()
                note = getattr(self.speaker, "fallback_note", "")
                if note:
                    notes.append(note)
            except Exception as err:
                notes.append(f"Voice unavailable: {err}")
        if self._make_listener is not None:
            try:
                self.listener = self._make_listener(self._wait_for_stop)
            except Exception as err:
                notes.append(f"Microphone unavailable: {err}")
        if self.calendar is not None:
            try:
                self.calendar.refresh()  # so the greeting can include today's events
            except Exception as err:
                notes.append(f"Google Calendar unavailable: {err}")
        self.status_changed.emit("idle")
        self.loaded.emit(self.speaker is not None, self.listener is not None, " ".join(notes))

    @Slot(str)
    def ask(self, text: str) -> None:
        self.status_changed.emit("thinking")
        try:
            reply = self.assistant.ask(text)
        except BrainError as err:
            self.failed.emit(str(err))
            self.status_changed.emit("idle")
            return
        self.replied.emit(reply)
        self._speak(reply)

    @Slot(str)
    def find_files(self, query: str) -> None:
        """Search file names off the window thread (it can take a few seconds)."""
        self.status_changed.emit("thinking")
        try:
            results = self.finder.search(query) if self.finder is not None else []
        except Exception as err:  # e.g. a drive disappearing mid-search
            self.failed.emit(f"File search problem: {err}")
            results = []
        self.status_changed.emit("idle")
        self.files_found.emit(query, results)

    @Slot()
    def refresh_calendar(self) -> None:
        if self.calendar is None:
            return
        try:
            self.calendar.refresh()
        except Exception:
            return  # offline for a moment: keep the old events, try again later
        self.calendar_updated.emit()

    @Slot(str, str, str, bool)
    def add_calendar_event(self, title: str, start: str, end: str, all_day: bool) -> None:
        """Create an event the owner has already confirmed."""
        from datetime import datetime

        from backend.google_calendar import EventRequest

        request = EventRequest(title, datetime.fromisoformat(start), datetime.fromisoformat(end), all_day)
        self.status_changed.emit("thinking")
        try:
            self.calendar.add(title, request.start, request.end, all_day)
        except Exception as err:
            self.failed.emit(str(err))
            self.status_changed.emit("idle")
            return
        self.calendar_updated.emit()
        text = f"Added to your calendar: {request.describe()}."
        self.replied.emit(text)
        self._speak(text)

    @Slot(str)
    def say(self, text: str) -> None:
        """Speak a fixed line (greeting, confirmations) without asking the model."""
        self._speak(text)

    @Slot()
    def listen(self) -> None:
        if self.listener is None:
            self.failed.emit("The microphone isn't available.")
            return
        self._stop_listening.clear()
        self.status_changed.emit("listening")
        try:
            text = self.listener.listen()
        except Exception as err:
            self.failed.emit(f"Microphone problem: {err}")
            text = None
        self.status_changed.emit("idle")
        if text is not None:
            self.heard.emit(text.strip())

    # ---- called directly from the window thread (thread-safe) ---------------
    def stop_listening(self) -> None:
        self._stop_listening.set()

    def stop_speaking(self) -> None:
        if self.speaker is not None and hasattr(self.speaker, "stop"):
            self.speaker.stop()

    # ---- helpers -------------------------------------------------------------
    def _wait_for_stop(self, _prompt: str = "") -> None:
        self._stop_listening.wait()

    def _speak(self, text: str) -> None:
        if self.voice_enabled and self.speaker is not None and text.strip():
            self.status_changed.emit("speaking")
            try:
                self.speaker.speak(text)
            except Exception as err:  # A voice problem must never break the app.
                self.failed.emit(f"Voice problem: {err}")
        self.status_changed.emit("idle")
