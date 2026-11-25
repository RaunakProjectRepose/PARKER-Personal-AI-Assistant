"""The glowing status orb: shows at a glance whether PARKER is listening,
thinking or speaking. It breathes slowly when idle and pulses when active."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

from frontend.theme import ORB_COLOURS

# Breathing speed (radians per frame) and pulse size per state.
_MOTION = {
    "loading": (0.04, 0.04),
    "idle": (0.05, 0.06),
    "listening": (0.16, 0.16),
    "thinking": (0.10, 0.08),
    "speaking": (0.22, 0.12),
}


class StatusOrb(QWidget):
    def __init__(self, size: int = 140, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.state = "loading"
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)  # ~30 frames per second

    def set_state(self, state: str) -> None:
        self.state = state if state in ORB_COLOURS else "idle"
        self.update()

    def _tick(self) -> None:
        self._phase += _MOTION[self.state][0]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        depth = _MOTION[self.state][1]
        core, halo = ORB_COLOURS[self.state]
        breath = (math.sin(self._phase) + 1) / 2  # 0..1
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        full = self.width() / 2

        # Outer halo: soft light that swells and fades.
        halo_r = full * (0.78 + depth * breath)
        g = QRadialGradient(c, halo_r)
        glow = QColor(halo)
        g.setColorAt(0.0, glow)
        glow.setAlpha(int(halo.alpha() * 0.35))
        g.setColorAt(0.6, glow)
        glow.setAlpha(0)
        g.setColorAt(1.0, glow)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(c, halo_r, halo_r)

        # Listening: expanding rings, like sound arriving.
        if self.state == "listening":
            for k in range(2):
                t = (self._phase / 3 + k / 2) % 1.0
                ring = QColor(halo)
                ring.setAlpha(int(160 * (1 - t)))
                p.setPen(QPen(ring, 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                r = full * (0.42 + 0.5 * t)
                p.drawEllipse(c, r, r)

        # Thinking: a slow golden arc circling the core.
        if self.state == "thinking":
            arc = QColor(halo)
            arc.setAlpha(220)
            pen = QPen(arc, 3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            r = full * 0.55
            rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
            p.drawArc(rect, int(-math.degrees(self._phase) * 16 * 3) % (360 * 16), 100 * 16)

        # Core: a pearl of light with a gold rim.
        core_r = full * (0.36 + 0.03 * breath)
        g = QRadialGradient(QPointF(c.x() - core_r * 0.3, c.y() - core_r * 0.3), core_r * 1.4)
        g.setColorAt(0.0, QColor("#FFFFFF"))
        g.setColorAt(0.45, core)
        rim = QColor(halo)
        rim.setAlpha(255)
        g.setColorAt(1.0, rim)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawEllipse(c, core_r, core_r)
        p.end()
