"""PARKER desktop app.

Run from the project folder, with Ollama running:

    python -m frontend.app              # with voice and microphone
    python -m frontend.app --no-voice   # text only

    python -m frontend.app --background # start hidden in the system tray

Shortcuts: Ctrl+Alt+P talk from any app (global) · Ctrl+Space talk /
finish talking · Esc stop speaking or close the drawer · Enter send ·
Ctrl+1 agenda · Ctrl+2 memories.

Closing the window keeps PARKER running in the system tray (by the clock);
use "Quit PARKER" from the tray menu to exit completely.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta

from PySide6.QtCore import (
    QDate,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QSettings,
    QSize,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QRadialGradient,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QDateEdit,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QInputDialog,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from backend.agenda import Agenda, AgendaError, parse_time
from backend.assistant import Assistant
from backend.brain import MODEL, OWNER_NAME
from backend.greeting import build_greeting, time_of_day
from backend.apps import AppError, AppLauncher
from backend.main import (
    HELP_TEXT,
    QUIT_COMMANDS,
    RESET_COMMAND,
    handle_agenda,
    handle_apps,
    handle_memory,
    handle_reminders,
    FileResults,
    handle_file_pick,
    connect_calendar_if_set_up,
    events_today,
    is_calendar_request,
    parse_calendar_request,
)
from backend.files import FileFinder, FoundFile, parse_find_request, summary
from backend.reminders import Reminders, announcement
from backend.memory import Memory, MemoryStoreError
from frontend import autostart, theme
from frontend.hotkey import (
    DEFAULT_HOTKEY,
    FALLBACK_HOTKEYS,
    GlobalHotkey,
    HotkeyError,
    parse_hotkey,
)
from frontend.icons import icon
from frontend.orb import StatusOrb
from frontend.toast import ReminderToast
from frontend.worker import Worker, default_listener, default_speaker

MAX_RECORDING_MS = 30_000  # Recording always stops by itself after 30 s.
BUBBLE_MAX_WIDTH = 560
COLUMN_WIDTH = 760  # the chat and message bar share one centred reading column
DRAWER_WIDTH = 360


def tray_icon(state: str) -> QIcon:
    """A small golden orb for the system tray; brighter while listening or speaking."""
    core, halo = theme.ORB_COLOURS.get(state, theme.ORB_COLOURS["idle"])
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QPointF(size / 2, size / 2)
    if state in ("listening", "speaking"):
        glow = QRadialGradient(c, size / 2)
        bright = QColor(halo)
        bright.setAlpha(230)
        glow.setColorAt(0.5, bright)
        bright.setAlpha(0)
        glow.setColorAt(1.0, bright)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(c, size / 2, size / 2)
    g = QRadialGradient(QPointF(c.x() - 7, c.y() - 7), size * 0.45)
    g.setColorAt(0.0, QColor("#FFFFFF"))
    g.setColorAt(0.45, core)
    g.setColorAt(1.0, QColor(theme.GOLD))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    radius = size * (0.36 if state in ("listening", "speaking") else 0.42)
    p.drawEllipse(c, radius, radius)
    p.end()
    return QIcon(pixmap)


def soft_shadow(widget: QWidget, blur: int = 28, alpha: int = 22, y: int = 6) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y)
    effect.setColor(QColor(150, 110, 20, alpha))
    widget.setGraphicsEffect(effect)


def icon_button(name: str, tooltip: str, size: int = 36, colour: str = theme.GOLD_DEEP) -> QToolButton:
    button = QToolButton()
    button.setObjectName("iconButton")
    button.setIcon(icon(name, colour))
    button.setIconSize(QSize(20, 20))
    button.setFixedSize(size, size)
    button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


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
        self._layout.setContentsMargins(8, 8, 8, 16)
        self._layout.setSpacing(14)
        self._layout.addStretch(1)
        self.setWidget(body)
        self.messages: list[tuple[str, str]] = []  # (kind, text), handy for tests
        self.verticalScrollBar().rangeChanged.connect(
            lambda _min, mx: self.verticalScrollBar().setValue(mx)
        )

    def add_files(self, results: list, on_open, on_reveal) -> None:
        """A card listing search results: click a name to open it, the folder icon
        to show it in File Explorer. Must run on the window thread."""
        if QThread.currentThread() is not self.thread():
            raise RuntimeError("ChatView.add_files called from a background thread")
        self.messages.append(("files", [str(f.path) for f in results]))
        card = QFrame()
        card.setObjectName("parkerBubble")
        card.setMaximumWidth(BUBBLE_MAX_WIDTH)
        card.setMinimumWidth(min(BUBBLE_MAX_WIDTH, 420))
        inner = QVBoxLayout(card)
        inner.setContentsMargins(10, 8, 10, 8)
        inner.setSpacing(2)
        self.file_buttons = []
        for number, found in enumerate(results, 1):
            row = QHBoxLayout()
            row.setSpacing(4)
            open_button = QPushButton(f"{number}.  {found.name}")
            open_button.setObjectName("fileLink")
            open_button.setToolTip(f"Open {found.path}")
            open_button.setCursor(Qt.CursorShape.PointingHandCursor)
            open_button.clicked.connect(lambda _=False, f=found: on_open(f))
            where = QLabel(f"{found.folder} · {found.modified:%d %b}")
            where.setObjectName("bubbleMeta")
            reveal = icon_button("folder", "Show in folder", 28, theme.TEXT_MUTED)
            reveal.clicked.connect(lambda _=False, f=found: on_reveal(f))
            row.addWidget(open_button, 1)
            row.addWidget(where)
            row.addWidget(reveal)
            inner.addLayout(row)
            self.file_buttons.append((open_button, reveal))
        soft_shadow(card, blur=24, alpha=18, y=4)
        outer = QHBoxLayout()
        outer.addWidget(card)
        outer.addStretch(1)
        self._layout.insertLayout(self._layout.count() - 1, outer)

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
            inner.setContentsMargins(18, 12, 18, 12)
            inner.setSpacing(2)
            words = QLabel(text)
            words.setObjectName("bubbleText")
            words.setWordWrap(True)
            words.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            inner.addWidget(words)
            if meta:  # e.g. "spoken", shown small and quiet under the words
                tag = QLabel(meta)
                tag.setObjectName("bubbleMeta")
                tag.setAlignment(Qt.AlignmentFlag.AlignRight)
                inner.addWidget(tag)
            # Size the bubble to its text: short messages stay compact, long ones
            # wrap at a comfortable reading width.
            longest = max(
                words.fontMetrics().horizontalAdvance(line) for line in text.splitlines() or [""]
            )
            bubble.setMinimumWidth(min(int(longest * 1.12) + 48, BUBBLE_MAX_WIDTH))
            bubble.setMaximumWidth(BUBBLE_MAX_WIDTH)
            bubble.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
            if kind == "user":
                row.addStretch(1)
                row.addWidget(bubble)
            else:
                soft_shadow(bubble, blur=24, alpha=18, y=4)
                row.addWidget(bubble)
                row.addStretch(1)
        self._layout.insertLayout(self._layout.count() - 1, row)


# ---- drawer panels ----------------------------------------------------------

def _section(title: str) -> QLabel:
    label = QLabel(title.upper())
    label.setObjectName("sectionTitle")
    return label


def _secondary(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName("secondary")
    return button


def _clean_list() -> QListWidget:
    lst = QListWidget()
    lst.setWordWrap(True)
    lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    lst.setTextElideMode(Qt.TextElideMode.ElideNone)
    lst.setResizeMode(QListView.ResizeMode.Adjust)
    lst.setSpacing(0)
    return lst


class MemoriesPanel(QWidget):
    changed = Signal()

    def __init__(self, memory: Memory | None) -> None:
        super().__init__()
        self.memory = memory
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(_section("What PARKER remembers"))
        self.list = _clean_list()
        layout.addWidget(self.list, 1)
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Add a memory, then press Enter")
        self.entry.returnPressed.connect(self.add)
        layout.addWidget(self.entry)
        forget = _secondary("Forget selected")
        forget.clicked.connect(self.delete_selected)
        layout.addWidget(forget)
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

    def __init__(self, agenda: Agenda | None, today=date.today, reminders=None, now=datetime.now,
                 calendar=None) -> None:
        super().__init__()
        self.agenda = agenda
        self.calendar = calendar
        self.reminders = reminders
        self._today = today
        self._now = now
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        layout.addWidget(_section("Plans for next session"))
        self.plans = _clean_list()
        self.plans.itemChanged.connect(self._plan_ticked)
        layout.addWidget(self.plans, 2)
        self.plan_entry = QLineEdit()
        self.plan_entry.setPlaceholderText("Add a plan, then press Enter")
        self.plan_entry.returnPressed.connect(self.add_plan)
        layout.addWidget(self.plan_entry)

        layout.addSpacing(14)
        self.reminders_title = _section("Reminders")
        layout.addWidget(self.reminders_title)
        self.reminder_list = _clean_list()
        self.reminder_list.setToolTip('Say "remind me in 20 minutes to stretch". Select one and press Delete to cancel.')
        self.reminder_list.setMaximumHeight(150)
        layout.addWidget(self.reminder_list)
        QShortcut(QKeySequence.StandardKey.Delete, self.reminder_list, activated=self.cancel_selected_reminder)
        self.reminders_title.setVisible(reminders is not None)
        self.reminder_list.setVisible(reminders is not None)

        layout.addSpacing(14)
        layout.addWidget(_section("Next 7 days"))
        self.events = _clean_list()
        layout.addWidget(self.events, 3)
        when = QHBoxLayout()
        self.event_day = QDateEdit()
        self.event_day.setCalendarPopup(True)
        self.event_day.setDisplayFormat("ddd d MMM")
        self.event_time = QLineEdit()
        self.event_time.setPlaceholderText("Time")
        when.addWidget(self.event_day, 3)
        when.addWidget(self.event_time, 2)
        layout.addLayout(when)
        self.event_text = QLineEdit()
        self.event_text.setPlaceholderText("Add an event, then press Enter")
        self.event_text.returnPressed.connect(self.add_event)
        layout.addWidget(self.event_text)
        remove = _secondary("Remove selected event")
        remove.clicked.connect(self.delete_selected_event)
        layout.addWidget(remove)
        self.setEnabled(agenda is not None)
        self.refresh()

    def refresh(self) -> None:
        today = self._today()
        self.event_day.setDate(QDate(today.year, today.month, today.day))
        self.reminder_list.clear()
        if self.reminders is not None:
            now = self._now()
            upcoming = self.reminders.upcoming()
            for reminder in upcoming:
                item = QListWidgetItem(f"{reminder.text}\n{reminder.when(now)}")
                item.setData(Qt.ItemDataRole.UserRole, reminder.id)
                self.reminder_list.addItem(item)
            if not upcoming:
                hint = QListWidgetItem('None yet. Try "remind me in 20 minutes to stretch".')
                hint.setFlags(Qt.ItemFlag.NoItemFlags)
                self.reminder_list.addItem(hint)
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
            upcoming = [(e, False) for e in self.agenda.events_between(today, today + timedelta(days=7))]
            if self.calendar is not None:
                upcoming += [(e.as_agenda_event(), True)
                             for e in self.calendar.cached(today, today + timedelta(days=7))]
            upcoming.sort(key=lambda pair: (pair[0].day, pair[0].time is not None, pair[0].time or ""))
            for event, from_google in upcoming:
                when = event.when(today) + ("  ·  Google" if from_google else "")
                item = QListWidgetItem(f"{event.text}\n{when}")
                # Google events can't be removed from here (only PARKER's own).
                item.setData(Qt.ItemDataRole.UserRole, None if from_google else event.id)
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

    def cancel_selected_reminder(self) -> None:
        for item in self.reminder_list.selectedItems():
            reminder_id = item.data(Qt.ItemDataRole.UserRole)
            if reminder_id is not None:
                self.reminders.cancel(reminder_id)
        self.refresh()
        self.changed.emit()

    def delete_selected_event(self) -> None:
        for item in self.events.selectedItems():
            event_id = item.data(Qt.ItemDataRole.UserRole)
            if event_id is None:
                QMessageBox.information(self, "PARKER", "Google Calendar events are changed in Google Calendar.")
                continue
            self.agenda.delete_event(event_id)
        self.refresh()
        self.changed.emit()


class Drawer(QFrame):
    """A panel that slides in from the right, holding Agenda or Memories."""

    def __init__(self, pages: dict[str, QWidget]) -> None:
        super().__init__()
        self.setObjectName("drawer")
        self.setMaximumWidth(0)  # closed
        self.setMinimumWidth(0)
        self.current: str | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 22, 22)
        layout.setSpacing(14)
        top = QHBoxLayout()
        self.title = QLabel("")
        self.title.setObjectName("drawerTitle")
        self.title.setFont(theme.font(theme.SERIF, 17, QFont.Weight.DemiBold))
        close = icon_button("close", "Close (Esc)", 32, theme.TEXT_MUTED)
        close.clicked.connect(self.close_drawer)
        top.addWidget(self.title)
        top.addStretch(1)
        top.addWidget(close)
        layout.addLayout(top)
        self.stack = QStackedWidget()
        self.pages = pages
        for page in pages.values():
            self.stack.addWidget(page)
        layout.addWidget(self.stack, 1)
        self._animation = QPropertyAnimation(self, b"maximumWidth", self)
        self._animation.setDuration(220)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    @property
    def is_open(self) -> bool:
        return self.current is not None

    def show_page(self, name: str) -> None:
        """Open on `name`, or close if that page is already showing."""
        if self.current == name:
            self.close_drawer()
            return
        self.current = name
        self.title.setText(name)
        self.stack.setCurrentWidget(self.pages[name])
        self._slide_to(DRAWER_WIDTH)

    def close_drawer(self) -> None:
        self.current = None
        self._slide_to(0)

    def _slide_to(self, width: int) -> None:
        self._animation.stop()
        self._animation.setStartValue(self.maximumWidth())
        self._animation.setEndValue(width)
        self._animation.start()


# ---- main window ------------------------------------------------------------

class MainWindow(QMainWindow):
    ask_requested = Signal(str)
    say_requested = Signal(str)
    listen_requested = Signal()
    load_requested = Signal()
    find_requested = Signal(str)
    add_event_requested = Signal(str, str, str, bool)
    calendar_refresh_requested = Signal()

    def __init__(
        self,
        assistant: Assistant,
        *,
        make_speaker=default_speaker,
        make_listener=default_listener,
        threaded: bool = True,
        now=datetime.now,
        tray_available=QSystemTrayIcon.isSystemTrayAvailable,
        make_hotkey=GlobalHotkey,
        settings: QSettings | None = None,
        start_hidden: bool = False,
        apps: AppLauncher | None = None,
        reminders: Reminders | None = None,
        finder: FileFinder | None = None,
    ) -> None:
        super().__init__()
        self.assistant = assistant
        self.calendar = getattr(assistant, "calendar", None)
        self.finder = finder
        self.file_results = FileResults()
        self.apps = apps
        self.reminders = reminders
        self.toasts: list[ReminderToast] = []
        self.settings = settings or QSettings("PARKER", "PARKER")
        self.start_hidden = start_hidden
        self._quitting = False
        self._told_about_tray = False
        self._told_about_hotkey = False
        self._now = now
        self.state = "loading"
        self.voice_ready = self.mic_ready = False
        self.setWindowTitle("PARKER")
        self.resize(1120, 780)
        self.setMinimumSize(760, 580)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- main area -------------------------------------------------------
        main = QVBoxLayout()
        main.setContentsMargins(28, 18, 28, 40)  # room for the message bar shadow
        main.setSpacing(0)

        header = QHBoxLayout()
        wordmark = QLabel("PARKER")
        wordmark.setObjectName("wordmark")
        wordmark.setFont(theme.font(theme.SERIF, 15, QFont.Weight.DemiBold, spacing=6))
        self.agenda_button = icon_button("calendar", "Agenda (Ctrl+1)")
        self.memories_button = icon_button("memory", "Memories (Ctrl+2)")
        self.settings_button = icon_button("settings", "Settings")
        for button in (self.agenda_button, self.memories_button):
            button.setCheckable(True)
        header.addWidget(wordmark)
        header.addStretch(1)
        header.addWidget(self.agenda_button)
        header.addWidget(self.memories_button)
        header.addWidget(self.settings_button)
        main.addLayout(header)

        self.orb = StatusOrb(150)
        self.status_label = QLabel(theme.STATUS_TEXT["loading"])
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main.addSpacing(4)
        main.addWidget(self.orb, 0, Qt.AlignmentFlag.AlignHCenter)
        main.addWidget(self.status_label)
        main.addSpacing(12)

        # The chat and the message bar share one centred column.
        column = QWidget()
        column.setMaximumWidth(COLUMN_WIDTH)
        col = QVBoxLayout(column)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(14)
        self.chat = ChatView()
        col.addWidget(self.chat, 1)

        composer = QFrame()
        composer.setObjectName("composer")
        composer.setFixedHeight(56)
        soft_shadow(composer, blur=36, alpha=30, y=8)
        bar = QHBoxLayout(composer)
        bar.setContentsMargins(20, 6, 6, 6)
        bar.setSpacing(6)
        self.entry = QLineEdit()
        self.entry.setObjectName("composerInput")
        self.entry.setPlaceholderText("Ask PARKER anything…")
        self.entry.returnPressed.connect(self.send_typed)
        self.send_button = QToolButton()
        self.send_button.setObjectName("sendButton")
        self.send_button.setIcon(icon("send", theme.GOLD_DEEP))
        self.send_button.setIconSize(QSize(20, 20))
        self.send_button.setFixedSize(36, 36)
        self.send_button.setToolTip("Send (Enter)")
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.clicked.connect(self.send_typed)
        self.talk_button = QToolButton()
        self.talk_button.setObjectName("micButton")
        self.talk_button.setIconSize(QSize(22, 22))
        self.talk_button.setFixedSize(44, 44)
        self.talk_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.talk_button.clicked.connect(self.mic_clicked)
        bar.addWidget(self.entry, 1)
        bar.addWidget(self.send_button)
        bar.addWidget(self.talk_button)
        col.addWidget(composer)

        centre = QHBoxLayout()
        centre.addStretch(1)
        centre.addWidget(column, 100)
        centre.addStretch(1)
        main.addLayout(centre, 1)
        outer.addLayout(main, 1)

        # ---- drawer ------------------------------------------------------------
        self.memories_panel = MemoriesPanel(assistant.memory)
        self.agenda_panel = AgendaPanel(
            assistant.agenda, today=lambda: self._now().date(), reminders=reminders,
            now=lambda: self._now(), calendar=self.calendar,
        )
        self.drawer = Drawer({"Agenda": self.agenda_panel, "Memories": self.memories_panel})
        outer.addWidget(self.drawer)
        self.agenda_button.clicked.connect(lambda: self.toggle_drawer("Agenda"))
        self.memories_button.clicked.connect(lambda: self.toggle_drawer("Memories"))
        self.drawer._animation.finished.connect(self._sync_drawer_buttons)

        # ---- settings menu -------------------------------------------------------
        menu = QMenu(self)
        self.voice_toggle = QAction("Speak replies", self, checkable=True, checked=True)
        self.voice_toggle.toggled.connect(self._voice_toggled)
        clear = QAction("Clear conversation", self)
        clear.triggered.connect(lambda: self.process("/reset"))
        about = QAction(f"Running locally · {MODEL}", self)
        about.setEnabled(False)
        self.hotkey_action = QAction("", self)
        self.hotkey_action.triggered.connect(self.change_hotkey)
        self.autostart_action = QAction("Start with Windows", self, checkable=True)
        self.autostart_action.setVisible(autostart.supported())
        if autostart.supported():
            self.autostart_action.setChecked(autostart.is_enabled())
        self.autostart_action.toggled.connect(self._autostart_toggled)
        menu.addAction(self.voice_toggle)
        menu.addAction(clear)
        menu.addSeparator()
        menu.addAction(self.hotkey_action)
        menu.addAction(self.autostart_action)
        menu.addSeparator()
        menu.addAction(about)
        self.settings_button.setMenu(menu)
        self.settings_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        QShortcut(QKeySequence("Ctrl+Space"), self, activated=self.toggle_listening)
        QShortcut(QKeySequence("Esc"), self, activated=self.escape)
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self.toggle_drawer("Agenda"))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self.toggle_drawer("Memories"))

        # ---- worker: slow work happens off the window thread -------------------
        self.worker = Worker(assistant, make_speaker, make_listener, finder=finder,
                             calendar=self.calendar)
        self._thread = None
        if threaded:
            self._thread = QThread(self)
            self.worker.moveToThread(self._thread)
            self._thread.start()
        self.ask_requested.connect(self.worker.ask)
        self.say_requested.connect(self.worker.say)
        self.listen_requested.connect(self.worker.listen)
        self.load_requested.connect(self.worker.load)
        self.find_requested.connect(self.worker.find_files)
        self.add_event_requested.connect(self.worker.add_calendar_event)
        self.calendar_refresh_requested.connect(self.worker.refresh_calendar)
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
        self.worker.files_found.connect(self._files_found, queued)
        self.worker.calendar_updated.connect(self.agenda_panel.refresh, queued)
        self._recording_limit = QTimer(self)
        self._recording_limit.setSingleShot(True)
        # stop_listening is thread-safe, so call it directly from this thread; a
        # queued call would wait behind the recording it is meant to stop.
        self._recording_limit.timeout.connect(self._stop_listening_now)

        # ---- system tray and global hotkey ---------------------------------------
        self.tray = None
        if tray_available():
            self._build_tray()
        self._make_hotkey = make_hotkey
        self.hotkey = None
        chosen = os.environ.get("PARKER_HOTKEY") or self.settings.value("hotkey")
        if make_hotkey is None:  # shortcut switched off (e.g. in tests)
            self.hotkey_text = str(chosen or DEFAULT_HOTKEY)
            self.hotkey_action.setText(f"Talk from any app: {self.hotkey_text}…")
        elif chosen:  # the user picked one: use exactly that, and say if it fails
            self.hotkey_text = str(chosen)
            self._start_hotkey(self.hotkey_text)
        else:  # default: try a few until one is free
            self.hotkey_text = DEFAULT_HOTKEY
            for candidate in FALLBACK_HOTKEYS:
                self.hotkey_text = candidate
                if self._start_hotkey(candidate, report_failure=False):
                    break
            else:
                self._hotkey_failed(
                    "Couldn't set up a talk-from-any-app shortcut: all the usual ones are taken. "
                    "Choose one in the settings menu."
                )
            if self.hotkey_text != DEFAULT_HOTKEY and self.hotkey is not None and self.hotkey.active:
                self.chat.add(
                    "note",
                    f"{DEFAULT_HOTKEY} is used by another app, so the talk shortcut is "
                    f"{self.hotkey_text}. You can change it in settings.",
                )

        # Reminders are checked every few seconds on the window thread, so they
        # are announced on time even while PARKER is hidden in the tray.
        self._reminder_timer = QTimer(self)
        self._reminder_timer.setInterval(5_000)
        self._reminder_timer.timeout.connect(self.check_reminders)
        # Google Calendar is re-read every 5 minutes on the worker thread.
        self._calendar_timer = QTimer(self)
        self._calendar_timer.setInterval(5 * 60_000)
        self._calendar_timer.timeout.connect(self.calendar_refresh_requested.emit)

        self.set_state("loading")
        self.load_requested.emit()

    # ---- state ---------------------------------------------------------------
    @Slot(str)
    def set_state(self, state: str) -> None:
        self.state = state
        self.orb.set_state(state)
        self.status_label.setText(theme.STATUS_TEXT.get(state, ""))
        # One button, three jobs: talk when ready, finish while listening,
        # stop while PARKER is speaking.
        if state == "listening":
            mode, name, tip = "listening", "check", "Done talking (Ctrl+Space)"
        elif state == "speaking":
            mode, name, tip = "speaking", "stop", "Stop speaking (Esc)"
        else:
            mode, name, tip = "talk", "mic", "Talk to PARKER (Ctrl+Space)"
        self.talk_button.setProperty("mode", mode)
        self.talk_button.setIcon(icon(name, theme.GOLD_DEEP if mode == "listening" else "#FFFFFF"))
        self.talk_button.setToolTip(tip)
        self.talk_button.style().unpolish(self.talk_button)
        self.talk_button.style().polish(self.talk_button)
        can_use = (self.mic_ready and state in ("idle", "listening")) or (
            state == "speaking" and self.voice_ready
        )
        self.talk_button.setEnabled(can_use)
        if state != "listening":
            self._recording_limit.stop()
        if self.tray is not None:
            self.tray.setIcon(tray_icon(state))
            self.tray.setToolTip(f"PARKER · {theme.STATUS_TEXT.get(state, '').title()}")

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
        self.check_reminders()  # anything missed while PARKER was closed
        self._reminder_timer.start()
        if self.calendar is not None:
            self.agenda_panel.refresh()
            self._calendar_timer.start()

    def greet(self) -> None:
        agenda = self.assistant.agenda
        if agenda is None:
            text = f"Good {time_of_day(self._now())}, {OWNER_NAME}. What shall we tackle today?"
        else:
            today = self._now().date()
            events = events_today(agenda, self.calendar, today)
            text = build_greeting(OWNER_NAME, agenda.open_plans(), events, self._now())
        self.chat.add("parker", text)
        if not self.start_hidden:  # stay quiet when Windows starts PARKER at login
            self.say_requested.emit(text)

    # ---- reminders --------------------------------------------------------------
    def check_reminders(self) -> None:
        if self.reminders is None:
            return
        now = self._now()
        fired = self.reminders.due(now)
        for reminder in fired:
            text = announcement(reminder, now)
            self.chat.add("parker", text)
            self.say_requested.emit(text)  # spoken even when the window is hidden
            self.show_toast(reminder.text, "" if text.startswith("Reminder:") else
                            f"Missed earlier: due {reminder.when(now).replace('at ', '')}")
            # The golden card replaces Windows' notification (owner's choice, so a
            # reminder never shows twice); the taskbar button still flashes.
            QApplication.alert(self)
        if fired:
            self.agenda_panel.refresh()

    def show_toast(self, text: str, when: str = "") -> ReminderToast:
        """PARKER's own pop-up: works even if Windows notifications are off."""
        toast = ReminderToast(text, when)
        toast.done.connect(self._toast_closed)
        toast.snoozed.connect(self._toast_snoozed)
        self.toasts.append(toast)
        toast.place(len(self.toasts) - 1)
        toast.show()
        return toast

    def _toast_closed(self, toast) -> None:
        if toast in self.toasts:
            self.toasts.remove(toast)
        for index, other in enumerate(self.toasts):
            other.place(index)

    def _toast_snoozed(self, toast, text: str) -> None:
        self._toast_closed(toast)
        if self.reminders is not None:
            due = self._now().replace(microsecond=0) + timedelta(minutes=10)
            self.reminders.add(due, text)
            self.chat.add("note", f"Snoozed: I'll remind you again at {due:%H:%M}.")
            self.agenda_panel.refresh()

    # ---- tray and hotkey -------------------------------------------------------
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(tray_icon("loading"), self)
        self.tray.setToolTip("PARKER")
        menu = QMenu()
        show = QAction("Open PARKER", self)
        show.triggered.connect(self.show_window)
        self.tray_talk = QAction("Talk", self)
        self.tray_talk.triggered.connect(self.toggle_listening)
        quit_action = QAction("Quit PARKER", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show)
        menu.addAction(self.tray_talk)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._tray_menu = menu  # keep a reference: the tray does not own it
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_clicked)
        self.tray.show()

    def _tray_clicked(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _start_hotkey(self, text: str, report_failure: bool = True) -> bool:
        if self.hotkey is not None:
            self.hotkey.stop()
            self.hotkey = None
        self.hotkey_action.setText(f"Talk from any app: {text}…")
        if self._make_hotkey is None:
            return False
        try:
            hotkey = self._make_hotkey(text)
        except HotkeyError as err:
            self.chat.add("error", str(err))
            return False
        # Emitted from the hotkey's own thread: queue it onto the window thread.
        hotkey.pressed.connect(self._hotkey_pressed, Qt.ConnectionType.QueuedConnection)
        if report_failure:
            hotkey.failed.connect(self._hotkey_failed, Qt.ConnectionType.QueuedConnection)
        self.hotkey = hotkey
        if hasattr(self, "tray_talk"):
            self.tray_talk.setText(f"Talk ({text})")
        return hotkey.start()

    @Slot()
    def _hotkey_pressed(self) -> None:
        if not self.mic_ready:
            self.show_window()
            self.chat.add("note", "The microphone isn't ready yet.")
            return
        if self.isHidden() and self.tray is not None and not self._told_about_hotkey:
            self._told_about_hotkey = True
            self.tray.showMessage(
                "PARKER is listening",
                f"Speak, then press {self.hotkey_text} again when you've finished.",
                tray_icon("listening"),
                4000,
            )
        self.toggle_listening()

    @Slot(str)
    def _hotkey_failed(self, message: str) -> None:
        # Make it impossible to miss: a chat note and, if available, a tray notice.
        self.chat.add("error", message)
        if self.tray is not None:
            self.tray.showMessage("PARKER shortcut", message, tray_icon("idle"), 6000)

    def change_hotkey(self) -> None:
        text, ok = QInputDialog.getText(
            self, "Talk from any app",
            "Shortcut (e.g. Ctrl+Alt+P, Ctrl+Shift+Space, Alt+F9):", text=self.hotkey_text,
        )
        if not ok or not text.strip():
            return
        try:
            parse_hotkey(text)
        except HotkeyError as err:
            QMessageBox.information(self, "PARKER", str(err))
            return
        self.hotkey_text = text.strip()
        self.settings.setValue("hotkey", self.hotkey_text)
        if self._start_hotkey(self.hotkey_text):
            self.chat.add("note", f"Press {self.hotkey_text} in any app to talk to PARKER.")

    def _autostart_toggled(self, on: bool) -> None:
        try:
            autostart.enable() if on else autostart.disable()
        except OSError as err:
            QMessageBox.information(self, "PARKER", f"Couldn't change the startup setting: {err}")
            return
        self.chat.add(
            "note",
            "PARKER will start quietly in the tray when you log in."
            if on else "PARKER won't start with Windows any more.",
        )

    def quit_app(self) -> None:
        self._quitting = True
        self.close()
        QApplication.quit()

    # ---- actions -------------------------------------------------------------
    def send_typed(self) -> None:
        text = self.entry.text().strip()
        if not text:
            return
        self.entry.clear()
        self.process(text)

    def mic_clicked(self) -> None:
        if self.state == "speaking":
            self.stop_speaking()
        else:
            self.toggle_listening()

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

    def escape(self) -> None:
        if self.state == "speaking":
            self.stop_speaking()
        elif self.drawer.is_open:
            self.drawer.close_drawer()
            self._sync_drawer_buttons()

    def toggle_drawer(self, name: str) -> None:
        self.drawer.show_page(name)
        self._sync_drawer_buttons()

    def _sync_drawer_buttons(self) -> None:
        self.agenda_button.setChecked(self.drawer.current == "Agenda")
        self.memories_button.setChecked(self.drawer.current == "Memories")

    def _voice_toggled(self, on: bool) -> None:
        self.worker.voice_enabled = on
        if not on:
            self.worker.stop_speaking()

    def add_to_calendar(self, text: str) -> None:
        """Show the event, ask, and only then add it (on the worker thread)."""
        request = parse_calendar_request(text, self.calendar, self._print, self._now())
        if request is None:
            return
        answer = QMessageBox.question(
            self, "Add to Google Calendar?", f"Add {request.describe()} to your Google Calendar?"
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.chat.add("note", "Okay, I haven't added it.")
            return
        self.add_event_requested.emit(
            request.title, request.start.isoformat(), request.end.isoformat(), request.all_day
        )

    @Slot(str, list)
    def _files_found(self, query: str, results: list) -> None:
        self.file_results.query, self.file_results.results = query, results
        self._say(summary(query, results, self.finder))
        if results:
            self.chat.add_files(results, self._open_file, self._reveal_file)

    def _open_file(self, found: FoundFile) -> None:
        try:
            self.finder.open(found)
        except AppError as err:
            self.chat.add("error", str(err))

    def _reveal_file(self, found: FoundFile) -> None:
        try:
            self.finder.reveal(found)
        except AppError as err:
            self.chat.add("error", str(err))

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
        self.chat.add("user", text, meta="spoken" if spoken else "")
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
        if handle_reminders(text, self.reminders, self._say, self._print, self._now()):
            self.agenda_panel.refresh()
            return
        if is_calendar_request(text, self._now()):
            self.add_to_calendar(text)
            return
        if handle_file_pick(text, self.finder, self.file_results, self._say, self._print):
            return
        query = parse_find_request(text)
        if query is not None and self.finder is not None:
            self.find_requested.emit(query)  # searched on the worker thread
            return
        if handle_apps(text, self.apps, self._say, self._print):
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
        if self.tray is not None and not self._quitting:
            # Closing the window hides PARKER to the tray; it keeps running.
            event.ignore()
            self.hide()
            if not self._told_about_tray:
                self._told_about_tray = True
                self.tray.showMessage(
                    "PARKER is still running",
                    f"Press {self.hotkey_text} in any app to talk. "
                    "Right-click the tray icon to quit.",
                    tray_icon("idle"),
                    5000,
                )
            return
        if self.hotkey is not None:
            self.hotkey.stop()
        if self.tray is not None:
            self.tray.hide()
        for toast in list(self.toasts):
            toast.close()
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
    parser.add_argument("--background", action="store_true", help="start hidden in the system tray")
    args = parser.parse_args(argv)

    app = QApplication(sys.argv[:1])
    app.setApplicationName("PARKER")
    app.setQuitOnLastWindowClosed(False)  # closing the window hides PARKER to the tray
    app.setStyleSheet(theme.STYLESHEET)
    app.setFont(theme.font(theme.SANS, 10))

    memory = agenda = apps = reminders = None
    try:
        memory, agenda = Memory(), Agenda()
    except Exception as err:  # e.g. a locked database file
        QMessageBox.warning(None, "PARKER", f"Memory unavailable: {err}")
    try:
        apps = AppLauncher()
    except Exception:  # opening apps is optional; PARKER works without it
        apps = None
    try:
        reminders = Reminders()
    except Exception:
        reminders = None
    finder = FileFinder()
    calendar = connect_calendar_if_set_up()

    window = MainWindow(
        Assistant(memory=memory, agenda=agenda, calendar=calendar),
        make_speaker=None if args.no_voice else default_speaker,
        make_listener=None if args.no_voice else default_listener,
        start_hidden=args.background,
        apps=apps,
        reminders=reminders,
        finder=finder,
    )
    if window.tray is None:
        app.setQuitOnLastWindowClosed(True)  # no tray: closing really quits
    if not (args.background and window.tray is not None):
        window.show()
    code = app.exec()
    for store in (memory, agenda, apps, reminders):
        if store is not None:
            store.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
