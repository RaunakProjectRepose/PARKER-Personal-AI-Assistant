"""The "Pair phone" window: a QR code the PARKER Android app scans once."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from frontend import theme


class QrCode(QWidget):
    def __init__(self, matrix: list[list[bool]], size: int = 260) -> None:
        super().__init__()
        self.matrix = matrix
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#FFFFFF"))
        n = len(self.matrix)
        cell = self.width() / n
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2B220C"))
        for y, row in enumerate(self.matrix):
            for x, dark in enumerate(row):
                if dark:
                    p.drawRect(QRectF(x * cell, y * cell, cell + 0.5, cell + 0.5))
        p.end()


class PairingDialog(QDialog):
    def __init__(self, matrix, hosts: list[str], port: int, on_reset, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pair your phone")
        self.reset_requested = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(12)
        title = QLabel("Pair your phone")
        title.setFont(theme.font(theme.SERIF, 17, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {theme.GOLD_DEEP};")
        steps = QLabel(
            "1. Open the PARKER app on your phone and tap <b>Pair with laptop</b>.<br>"
            "2. Scan this code. Your phone must be on the same Wi-Fi.<br>"
            "3. If Windows asks, allow Python on <b>private networks</b>."
        )
        steps.setWordWrap(True)
        self.qr = QrCode(matrix)
        where = QLabel("PARKER is listening at " + (", ".join(f"{h}:{port}" for h in hosts) or "no network found")
                       + "<br><span style='color:%s'>Keep this code private: it lets a phone use PARKER.</span>"
                       % theme.TEXT_MUTED)
        where.setWordWrap(True)
        buttons = QHBoxLayout()
        reset = QPushButton("Unpair all phones")
        reset.setObjectName("secondary")
        reset.setToolTip("Makes a new code; phones paired before will stop working.")
        reset.clicked.connect(lambda: (on_reset(), self.accept()))
        done = QPushButton("Done")
        done.clicked.connect(self.accept)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        buttons.addWidget(done)
        layout.addWidget(title)
        layout.addWidget(steps)
        layout.addWidget(self.qr, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(where)
        layout.addLayout(buttons)
