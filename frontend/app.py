"""PARKER desktop app (Milestone 3).

Run from the project folder, with Ollama running:

    python -m frontend.app              # with voice and microphone
    python -m frontend.app --no-voice   # text only

Shortcuts: Ctrl+Space talk / stop listening · Esc stop speaking · Enter send.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListView,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from backend.agenda import Agenda, AgendaError, parse_time
from backend.assistant import Assistant
from backend.brain import MODEL, OWNER_NAME
from backend.greeting import build_greeting, time_of_day
from backend.main import HELP_TEXT, QUIT_COMMANDS, RESET_COMMAND, handle_agenda, handle_memory
from backend.memory import Memory, MemoryStoreError
from frontend import theme
from frontend.orb import StatusOrb
from frontend.worker import Worker, default_listener, default_speaker

MAX_RECORDING_MS = 30_000  # Recording always stops by itself after 30 s.
BUBBLE_MAX_WIDTH = 520


# ---- chat transcript --------------------------------------------------------

class ChatView(QScrollArea):
    """The conversation, as message bubbles that scroll."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("chat")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("chatBody")
        self._layout = QVBoxLayout(body)
        self._layout.setContentsMargins(24, 12, 24, 12)
        self._layout.setSpacing(10)
        self._layout.addStretch(1)
        self.setWidget(body)
        self.messages: list[tuple[str, str]] = []  # (kind, text), handy for tests
        self.verticalScrollBar().rangeChanged.connect(
            lambda _min, mx: self.verticalScrollBar().setValue(mx)
        )

    def add(self, kind: str, text: str, meta: str = "") -> None:
        """kind: 'user', 'parker', 'note' or 'error'. Must run on the window thread."""
        if QThread.currentThread() is not self.thread():
            raise RuntimeError("ChatView.add called from a background thread")
        self.messages.append((kind, text))
        row = QHBoxLayout()
        if kind in ("note", "error"):
            label = QLabel(text)
            label.setObjectName(kind)
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(label)
        else:
            bubble = QFrame()
            bubble.setObjectName("userBubble" if kind == "user" else "parkerBubble")
            inner = QVBoxLayout(bubble)
            inner.setContentsMargins(14, 10, 14, 10)
            inner.setSpacing(2)
            who = QLabel(meta or ("You" if kind == "user" else "PARKER"))
            who.setObjectName("bubbleMeta")
            words = QLabel(text)
            words.setObjectName("bubbleText")
            words.setWordWrap(True)
            words.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            inner.addWidget(who)
            inner.addWidget(words)
            # Size the bubble to its text: short messages stay compact, long ones
            # wrap at a comfortable reading width.
            longest = max(
                words.fontMetrics().horizontalAdvance(line) for line in text.splitlines() or [""]
            )
            bubble.setMinimumWidth(min(int(longest * 1.1) + 40, BUBBLE_MAX_WIDTH))
            bubble.setMaximumWidth(BUBBLE_MAX_WIDTH)
            bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
            if kind == "user":
                row.addStretch(1)
                row.addWidget(bubble)
            else:
                row.addWidget(bubble)
                row.addStretch(1)
        self._layout.insertLayout(self._layout.count() - 1, row)


# ---- sidebar panels ---------------------------------------------------------

def _section(title: str) -> QLabel:
    label = QLabel(title.upper())
    label.setObjectName("sectionTitle")
    return label


def _secondary(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("secondary")
    return button


class MemoriesPanel(QWidget):
    changed = Signal()

    def __init__(self, memory: Memory | None) -> None:
        super().__init__()
        self.memory = memory
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.addWidget(_section("What PARKER remembers"))
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        layout.addWidget(self.list, 1)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("e.g. My favourite colour is blue")
        self.entry.returnPressed.connect(self.add)
        layout.addWidget(self.entry)
        buttons = QHBoxLayout()
        add = QPushButton("Remember")
        add.clicked.connect(self.add)
        delete = _secondary("Forget selected")
        delete.clicked.connect(self.delete_selected)
        buttons.addWidget(add)
        buttons.addWidget(delete)
        layout.addLayout(buttons)
        self.setEnabled(memory is not None)
        self.refresh()

    def refresh(self) -> None:
        self.list.clear()
        if self.memory is None:
            return
        for fact in self.memory.all():
            item = QListWidgetItem(fact.text)
            item.setData(Qt.ItemDataRole.UserRole, fact.id)
            self.list.addItem(item)

    def add(self) -> None:
        text = self.entry.text().strip()
        if not text or self.memory is None:
            return
        try:
            self.memory.add(text)
        except MemoryStoreError as err:
            QMessageBox.information(self, "PARKER", str(err))
            return
        self.entry.clear()
        self.refresh()
        self.changed.emit()

    def delete_selected(self) -> None:
        for item in self.list.selectedItems():
            self.memory.delete(item.data(Qt.ItemDataRole.UserRole))
        self.refresh()
        self.changed.emit()


class AgendaPanel(QWidget):
    changed = Signal()

    def __init__(self, agenda: Agenda | None, today=date.today) -> None:
        super().__init__()
        self.agenda = agenda
        self._today = today
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)

        layout.addWidget(_section("Plans for next session"))
        self.plans = QListWidget()
        self.plans.setWordWrap(True)
        self.plans.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.plans.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.plans.setResizeMode(QListView.ResizeMode.Adjust)
        self.plans.itemChanged.connect(self._plan_ticked)
        layout.addWidget(self.plans, 1)
        self.plan_entry = QLineEdit()
        self.plan_entry.setPlaceholderText("Add a plan, then press Enter")
        self.plan_entry.returnPressed.connect(self.add_plan)
        layout.addWidget(self.plan_entry)

        layout.addSpacing(8)
        layout.addWidget(_section("Next 7 days"))
        self.events = QListWidget()
        self.events.setWordWrap(True)
        self.events.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.events.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.events.setResizeMode(QListView.ResizeMode.Adjust)
        layout.addWidget(self.events, 1)
        when = QHBoxLayout()
        self.event_day = QDateEdit()
        self.event_day.setCalendarPopup(True)
        self.event_day.setDisplayFormat("ddd d MMM")
        self.event_time = QLineEdit()
        self.event_time.setPlaceholderText("18:00 (optional)")
        when.addWidget(self.event_day, 3)
        when.addWidget(self.event_time, 2)
        layout.addLayout(when)
        self.event_text = QLineEdit()
        self.event_text.setPlaceholderText("What's happening?")
        self.event_text.returnPressed.connect(self.add_event)
        layout.addWidget(self.event_text)
        buttons = QHBoxLayout()
        add = QPushButton("Add event")
        add.clicked.connect(self.add_event)
        cancel = _secondary("Remove selected")
        cancel.clicked.connect(self.delete_selected_event)
        buttons.addWidget(add)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self.setEnabled(agenda is not None)
        self.refresh()

    def refresh(self) -> None:
        today = self._today()
        self.event_day.setDate(QDate(today.year, today.month, today.day))
        self.plans.blockSignals(True)
        self.plans.clear()
        self.events.clear()
        if self.agenda is not None:
            for plan in self.agenda.open_plans():
                item = QListWidgetItem(plan.text)
                item.setData(Qt.ItemDataRole.UserRole, plan.id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                item.setToolTip("Tick when done")
                self.plans.addItem(item)
            for event in self.agenda.events_between(today, today + timedelta(days=7)):
                item = QListWidgetItem(f"{event.text}\n{event.when(today)}")
                item.setData(Qt.ItemDataRole.UserRole, event.id)
                self.events.addItem(item)
        self.plans.blockSignals(False)

    def add_plan(self) -> None:
        text = self.plan_entry.text().strip()
        if not text:
            return
        try:
            self.agenda.add_plan(text)
        except AgendaError as err:
            QMessageBox.information(self, "PARKER", str(err))
            return
        self.plan_entry.clear()
        self.refresh()
        self.changed.emit()

    def _plan_ticked(self, item: QListWidgetItem) -> None:
        if item.checkState() == Qt.CheckState.Checked:
            self.agenda.complete_plan(item.data(Qt.ItemDataRole.UserRole))
            QTimer.singleShot(250, self.refresh)  # let the tick show briefly
            self.changed.emit()

    def add_event(self) -> None:
        text = self.event_text.text().strip()
        if not text:
            return
        day = self.event_day.date().toPython()
        try:
            self.agenda.add_event(day, parse_time(self.event_time.text()), text)
        except AgendaError as err:
            QMessageBox.information(self, "PARKER", str(err))
            return
        self.event_text.clear()
        self.event_time.clear()
        self.refresh()
        self.changed.emit()

    def delete_selected_event(self) -> None:
        for item in self.events.selectedItems():
            self.agenda.delete_event(item.data(Qt.ItemDataRole.UserRole))
        self.refresh()
        self.changed.emit()


# ---- main window ------------------------------------------------------------

class MainWindow(QMainWindow):
    ask_requested = Signal(str)
    say_requested = Signal(str)
    listen_requested = Signal()
    load_requested = Signal()

    def __init__(
        self,
        assistant: Assistant,
        *,
        make_speaker=default_speaker,
        make_listener=default_listener,
        threaded: bool = True,
        now=datetime.now,
    ) -> None:
        super().__init__()
        self.assistant = assistant
        self._now = now
        self.state = "loading"
        self.voice_ready = self.mic_ready = False
        self.setWindowTitle("PARKER")
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Left: header, orb, chat, controls.
        main = QVBoxLayout()
        main.setContentsMargins(0, 18, 0, 18)
        main.setSpacing(6)
        title = QLabel("PARKER")
        title.setObjectName("title")
        title.setFont(theme.font(theme.SERIF, 30, QFont.Weight.DemiBold, spacing=8))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle = QLabel("Your personal assistant")
        subtitle.setObjectName("subtitle")
        subtitle.setFont(theme.font(theme.SERIF, 12))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.orb = StatusOrb(130)
        self.status_label = QLabel(theme.STATUS_TEXT["loading"])
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main.addWidget(title)
        main.addWidget(subtitle)
        main.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignHCenter)
        main.addWidget(self.status_label)

        self.chat = ChatView()
        main.addWidget(self.chat, 1)

        controls = QHBoxLayout()
        controls.setContentsMargins(24, 6, 24, 0)
        controls.setSpacing(10)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Message PARKER, or press Ctrl+Space to talk…")
        self.entry.returnPressed.connect(self.send_typed)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send_typed)
        self.talk_button = QPushButton("Talk")
        self.talk_button.setObjectName("talk")
        self.talk_button.setToolTip("Talk to PARKER (Ctrl+Space). Click again to stop.")
        self.talk_button.clicked.connect(self.toggle_listening)
        self.stop_button = _secondary("Stop")
        self.stop_button.setToolTip("Stop speaking (Esc)")
        self.stop_button.clicked.connect(self.stop_speaking)
        controls.addWidget(self.entry, 1)
        controls.addWidget(self.send_button)
        controls.addWidget(self.talk_button)
        controls.addWidget(self.stop_button)
        main.addLayout(controls)

        footer = QHBoxLayout()
        footer.setContentsMargins(26, 2, 24, 0)
        self.voice_toggle = QCheckBox("Speak replies")
        self.voice_toggle.setChecked(True)
        self.voice_toggle.toggled.connect(self._voice_toggled)
        self.model_label = QLabel(f"Running locally · {MODEL}")
        self.model_label.setObjectName("subtitle")
        footer.addWidget(self.voice_toggle)
        footer.addStretch(1)
        footer.addWidget(self.model_label)
        main.addLayout(footer)
        outer.addLayout(main, 1)

        # Right: memories and agenda.
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(330)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 18, 0, 0)
        tabs = QTabWidget()
        self.memories_panel = MemoriesPanel(assistant.memory)
        self.agenda_panel = AgendaPanel(assistant.agenda, today=lambda: self._now().date())
        tabs.addTab(self.agenda_panel, "Agenda")
        tabs.addTab(self.memories_panel, "Memories")
        side.addWidget(tabs)
        outer.addWidget(sidebar)

        QShortcut(QKeySequence("Ctrl+Space"), self, activated=self.toggle_listening)
        QShortcut(QKeySequence("Esc"), self, activated=self.stop_speaking)

        # Worker: slow work happens off the window thread.
        self.worker = Worker(assistant, make_speaker, make_listener)
        self._thread = None
        if threaded:
            self._thread = QThread(self)
            self.worker.moveToThread(self._thread)
            self._thread.start()
        self.ask_requested.connect(self.worker.ask)
        self.say_requested.connect(self.worker.say)
        self.listen_requested.connect(self.worker.listen)
        self.load_requested.connect(self.worker.load)
        # Everything the worker reports must run on the window's thread: Qt
        # widgets may only be created and changed there. QueuedConnection plus
        # slots on this window (not lambdas) guarantees that.
        queued = (
            Qt.ConnectionType.QueuedConnection if threaded else Qt.ConnectionType.DirectConnection
        )
        self.worker.status_changed.connect(self.set_state, queued)
        self.worker.loaded.connect(self._loaded, queued)
        self.worker.heard.connect(self._heard, queued)
        self.worker.replied.connect(self._replied, queued)
        self.worker.failed.connect(self._failed, queued)
        self._recording_limit = QTimer(self)
        self._recording_limit.setSingleShot(True)
        # stop_listening is thread-safe, so call it directly from this thread; a
        # queued call would wait behind the recording it is meant to stop.
        self._recording_limit.timeout.connect(self._stop_listening_now)

        self.set_state("loading")
        self.load_requested.emit()

    # ---- state ---------------------------------------------------------------
    @Slot(str)
    def set_state(self, state: str) -> None:
        self.state = state
        self.orb.set_state(state)
        self.status_label.setText(theme.STATUS_TEXT.get(state, ""))
        listening = state == "listening"
        self.talk_button.setText("Done" if listening else "Talk")
        self.talk_button.setProperty("listening", listening)
        self.talk_button.style().unpolish(self.talk_button)
        self.talk_button.style().polish(self.talk_button)
        self.talk_button.setEnabled(self.mic_ready and state in ("idle", "listening", "speaking"))
        self.stop_button.setEnabled(state == "speaking")
        if not listening:
            self._recording_limit.stop()

    @Slot(bool, bool, str)
    def _loaded(self, voice_ok: bool, mic_ok: bool, notes: str) -> None:
        self.voice_ready, self.mic_ready = voice_ok, mic_ok
        self.voice_toggle.setEnabled(voice_ok)
        if not voice_ok:
            self.voice_toggle.setChecked(False)
        if notes:
            self.chat.add("note", notes)
        self.set_state(self.state)
        self.greet()

    def greet(self) -> None:
        agenda = self.assistant.agenda
        if agenda is None:
            text = f"Good {time_of_day(self._now())}, {OWNER_NAME}. What shall we tackle today?"
        else:
            today = self._now().date()
            text = build_greeting(OWNER_NAME, agenda.open_plans(), agenda.events_on(today), self._now())
        self.chat.add("parker", text)
        self.say_requested.emit(text)

    # ---- actions -------------------------------------------------------------
    def send_typed(self) -> None:
        text = self.entry.text().strip()
        if not text:
            return
        self.entry.clear()
        self.process(text)

    def toggle_listening(self) -> None:
        if not self.mic_ready:
            return
        if self.state == "listening":
            self.worker.stop_listening()
            return
        if self.state == "speaking":
            self.worker.stop_speaking()
        self._recording_limit.start(MAX_RECORDING_MS)
        self.listen_requested.emit()

    def stop_speaking(self) -> None:
        self.worker.stop_speaking()

    def _voice_toggled(self, on: bool) -> None:
        self.worker.voice_enabled = on
        if not on:
            self.worker.stop_speaking()

    @Slot(str)
    def _replied(self, text: str) -> None:
        self.chat.add("parker", text)

    @Slot(str)
    def _failed(self, text: str) -> None:
        self.chat.add("error", text)

    @Slot()
    def _stop_listening_now(self) -> None:
        self.worker.stop_listening()

    @Slot(str)
    def _heard(self, text: str) -> None:
        if not text:
            self.chat.add("note", "Sorry, I didn't catch that.")
            return
        self.process(text, spoken=True)

    def process(self, text: str, spoken: bool = False) -> None:
        """Handle one message, typed or spoken, exactly like the terminal chat does."""
        self.chat.add("user", text, meta="You (spoken)" if spoken else "You")
        lowered = text.lower()
        if lowered in QUIT_COMMANDS:
            self.close()
            return
        if lowered == RESET_COMMAND:
            self.assistant.reset()
            self.chat.add("note", "Conversation cleared. Saved memories are kept.")
            return
        if lowered == "/help":
            self.chat.add("note", HELP_TEXT.strip())
            return
        if handle_memory(text, self.assistant.memory, self._say, self._print, self._confirm):
            self.memories_panel.refresh()
            return
        if handle_agenda(text, self.assistant.agenda, self._say, self._print, self._now().date()):
            self.agenda_panel.refresh()
            return
        if text.startswith("/"):
            self.chat.add("note", f"Unknown command {text.split()[0]}. Type /help for commands.")
            return
        self.ask_requested.emit(text)

    # Bridges so the terminal's command handlers can talk to the window.
    def _say(self, text: str) -> None:
        self.chat.add("parker", text)
        self.say_requested.emit(text)

    def _print(self, text: str) -> None:
        text = text.strip()
        if text.startswith("PARKER: "):
            self.chat.add("parker", text[len("PARKER: "):])
        else:
            self.chat.add("note", text)

    def _confirm(self, question: str) -> str:
        answer = QMessageBox.question(self, "PARKER", question.replace(" Type yes:", ""))
        return "yes" if answer == QMessageBox.StandardButton.Yes else "no"

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self.worker.stop_listening()
        self.worker.stop_speaking()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(3000)
        speaker = self.worker.speaker
        if speaker is not None and hasattr(speaker, "close"):
            speaker.close()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PARKER desktop app")
    parser.add_argument("--no-voice", action="store_true", help="text only: no speech in or out")
    args = parser.parse_args(argv)

    app = QApplication(sys.argv[:1])
    app.setApplicationName("PARKER")
    app.setStyleSheet(theme.STYLESHEET)
    app.setFont(theme.font(theme.SANS, 10))

    memory = agenda = None
    try:
        memory, agenda = Memory(), Agenda()
    except Exception as err:  # e.g. a locked database file
        QMessageBox.warning(None, "PARKER", f"Memory unavailable: {err}")

    window = MainWindow(
        Assistant(memory=memory, agenda=agenda),
        make_speaker=None if args.no_voice else default_speaker,
        make_listener=None if args.no_voice else default_listener,
    )
    window.show()
    code = app.exec()
    for store in (memory, agenda):
        if store is not None:
            store.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
