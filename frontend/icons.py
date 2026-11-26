"""Minimal line icons, drawn in code so they stay crisp at any size and need no
image files. Each is drawn on a 24x24 grid."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _pen(colour: QColor, width: float = 1.8) -> QPen:
    pen = QPen(colour, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw(name: str, p: QPainter, colour: QColor) -> None:
    p.setPen(_pen(colour))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name == "mic":
        p.drawRoundedRect(QRectF(9, 3, 6, 11), 3, 3)
        path = QPainterPath(QPointF(5.5, 11))
        path.cubicTo(5.5, 19, 18.5, 19, 18.5, 11)
        p.drawPath(path)
        p.drawLine(QPointF(12, 17.5), QPointF(12, 21))
    elif name == "send":
        p.drawLine(QPointF(12, 19), QPointF(12, 5))
        p.drawLine(QPointF(6, 11), QPointF(12, 5))
        p.drawLine(QPointF(18, 11), QPointF(12, 5))
    elif name == "stop":
        p.setBrush(colour)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(7, 7, 10, 10), 2.5, 2.5)
    elif name == "check":
        path = QPainterPath(QPointF(5.5, 12.5))
        path.lineTo(10, 17)
        path.lineTo(18.5, 7.5)
        p.drawPath(path)
    elif name == "calendar":
        p.drawRoundedRect(QRectF(4, 5.5, 16, 14.5), 3, 3)
        p.drawLine(QPointF(4, 10), QPointF(20, 10))
        p.drawLine(QPointF(8.5, 3.5), QPointF(8.5, 7))
        p.drawLine(QPointF(15.5, 3.5), QPointF(15.5, 7))
    elif name == "memory":  # a four-point sparkle
        path = QPainterPath(QPointF(12, 3))
        path.cubicTo(12.6, 9.4, 14.6, 11.4, 21, 12)
        path.cubicTo(14.6, 12.6, 12.6, 14.6, 12, 21)
        path.cubicTo(11.4, 14.6, 9.4, 12.6, 3, 12)
        path.cubicTo(9.4, 11.4, 11.4, 9.4, 12, 3)
        p.drawPath(path)
    elif name == "settings":  # three sliders
        for y, x in ((6.5, 15), (12, 8.5), (17.5, 13)):
            p.drawLine(QPointF(4, y), QPointF(20, y))
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(QPointF(x, y), 2.2, 2.2)
            p.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "folder":
        path = QPainterPath(QPointF(3.5, 7))
        path.lineTo(3.5, 18.5)
        path.lineTo(20.5, 18.5)
        path.lineTo(20.5, 8.5)
        path.lineTo(11.5, 8.5)
        path.lineTo(9.5, 6)
        path.lineTo(4.5, 6)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "close":
        p.drawLine(QPointF(6.5, 6.5), QPointF(17.5, 17.5))
        p.drawLine(QPointF(17.5, 6.5), QPointF(6.5, 17.5))
    elif name == "plus":
        p.drawLine(QPointF(12, 5.5), QPointF(12, 18.5))
        p.drawLine(QPointF(5.5, 12), QPointF(18.5, 12))
    elif name == "trash":
        p.drawLine(QPointF(4.5, 7), QPointF(19.5, 7))
        p.drawRoundedRect(QRectF(6.5, 7, 11, 13), 2, 2)
        p.drawLine(QPointF(10, 4), QPointF(14, 4))
    else:
        raise ValueError(f"unknown icon {name!r}")


def icon(name: str, colour: str, size: int = 24) -> QIcon:
    """A QIcon drawn at double resolution so it is sharp on high-DPI screens."""
    scale = 2
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size * scale / 24, size * scale / 24)
    _draw(name, p, QColor(colour))
    p.end()
    pixmap.setDevicePixelRatio(scale)
    return QIcon(pixmap)
