"""PARKER's own reminder pop-up: a small golden card in the bottom-right corner.

It doesn't depend on Windows notifications (which can be switched off for
"Python" or hidden by focus rules), stays on top of every app without taking
keyboard focus, and stays until Done or Snooze is pressed.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QRadialGradient
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from frontend import theme

MARGIN = 24
GAP = 12
WIDTH = 360


class _Orb(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setFixedSize(34, 34)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(17, 17)
        g = QRadialGradient(QPointF(13, 13), 18)
        g.setColorAt(0.0, QColor("#FFFFFF"))
        g.setColorAt(0.5, QColor("#F7DE8E"))
        g.setColorAt(1.0, QColor(theme.GOLD))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(c, 14, 14)
        p.end()


class ReminderToast(QWidget):
    done = Signal(object)  # the toast
    snoozed = Signal(object, str)  # the toast, the reminder text

    def __init__(self, text: str, when: str = "") -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.text = text
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)  # don't steal typing focus
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("PARKER reminder")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)  # room for the shadow
        card = QFrame()
        card.setObjectName("toastCard")
        card.setStyleSheet(
            f"""
            QFrame#toastCard {{ background: #FFFDF6; border: 1px solid {theme.GOLD_LIGHT}; border-radius: 18px; }}
            QLabel#toastTitle {{ color: {theme.GOLD_DEEP}; background: transparent; letter-spacing: 2px; }}
            QLabel#toastText {{ color: {theme.TEXT}; background: transparent; }}
            QLabel#toastWhen {{ color: {theme.TEXT_MUTED}; background: transparent; }}
            QPushButton {{ border: none; border-radius: 11px; padding: 7px 14px; font-weight: 600; }}
            QPushButton#toastDone {{
                color: #FFFFFF;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {theme.GOLD_LIGHT}, stop:1 {theme.GOLD});
            }}
            QPushButton#toastSnooze {{ color: {theme.GOLD_DEEP}; background: transparent; border: 1px solid {theme.GOLD_LIGHT}; }}
            """
        )
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(150, 110, 20, 60))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        body = QVBoxLayout(card)
        body.setContentsMargins(18, 16, 18, 14)
        body.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(_Orb(), 0, Qt.AlignmentFlag.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(2)
        title = QLabel("REMINDER")
        title.setObjectName("toastTitle")
        title.setFont(theme.font(theme.SANS, 8, QFont.Weight.DemiBold))
        self.text_label = QLabel(text[:1].upper() + text[1:])
        self.text_label.setObjectName("toastText")
        self.text_label.setWordWrap(True)
        self.text_label.setFont(theme.font(theme.SANS, 12, QFont.Weight.Medium))
        words.addWidget(title)
        words.addWidget(self.text_label)
        if when:
            when_label = QLabel(when)
            when_label.setObjectName("toastWhen")
            words.addWidget(when_label)
        top.addLayout(words, 1)
        body.addLayout(top)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.snooze_button = QPushButton("Snooze 10 min")
        self.snooze_button.setObjectName("toastSnooze")
        self.snooze_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.snooze_button.clicked.connect(self._snooze)
        self.done_button = QPushButton("Done")
        self.done_button.setObjectName("toastDone")
        self.done_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.done_button.clicked.connect(self._done)
        buttons.addWidget(self.snooze_button)
        buttons.addWidget(self.done_button)
        body.addLayout(buttons)
        self.setFixedWidth(WIDTH)

    def place(self, index: int) -> None:
        """Bottom-right of the main screen; later toasts stack upwards."""
        self.adjustSize()
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        if area is None:
            return
        x = area.right() - self.width() - MARGIN + 16
        y = area.bottom() - (self.height() - 16 + GAP) * (index + 1) - MARGIN + 16
        self.move(x, y)

    def _done(self) -> None:
        self.done.emit(self)
        self.close()

    def _snooze(self) -> None:
        self.snoozed.emit(self, self.text)
        self.close()
