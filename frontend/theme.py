"""PARKER's "heavenly gold" look: warm ivory light, soft gold accents.

All colours and fonts live here so the theme can be tuned in one place.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont

# ---- palette ------------------------------------------------------------------
IVORY = "#FFFDF6"  # top of the window, almost white
CREAM = "#F7EDD3"  # bottom of the window, warm parchment
PANEL = "#FFFBEF"  # sidebar cards
GOLD = "#C9A227"  # main accent
GOLD_LIGHT = "#E9CF7A"
GOLD_PALE = "#F4E6BC"  # user message bubbles
GOLD_DEEP = "#9C7A12"  # pressed buttons, headings
TEXT = "#4A3B1A"  # warm dark brown, easier on the eyes than black
TEXT_MUTED = "#8C7A55"
LINE = "#E8D9AE"  # thin borders
ERROR = "#A94428"

# Orb colours per state: (core, halo)
ORB_COLOURS = {
    "loading": (QColor("#F3E7C6"), QColor(201, 162, 39, 60)),
    "idle": (QColor("#FFF6D8"), QColor(212, 175, 55, 110)),
    "listening": (QColor("#FFFFFF"), QColor(240, 196, 70, 190)),
    "thinking": (QColor("#FFF3CF"), QColor(201, 162, 39, 150)),
    "speaking": (QColor("#FFFDF2"), QColor(232, 186, 60, 200)),
}

STATUS_TEXT = {
    "loading": "Waking up…",
    "idle": "Ready",
    "listening": "Listening…",
    "thinking": "Thinking…",
    "speaking": "Speaking…",
}

# Windows has Palatino Linotype / Georgia / Segoe UI; the rest are fallbacks.
SERIF = ["Cormorant Garamond", "Palatino Linotype", "Book Antiqua", "Georgia", "DejaVu Serif", "serif"]
SANS = ["Segoe UI", "Inter", "Helvetica Neue", "DejaVu Sans", "sans-serif"]


def font(families: list[str], size: int, weight: QFont.Weight = QFont.Weight.Normal,
         spacing: float = 0.0) -> QFont:
    f = QFont()
    f.setFamilies(families)
    f.setPointSize(size)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f


STYLESHEET = f"""
QMainWindow, #central {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {IVORY}, stop:1 {CREAM});
}}
QWidget {{ color: {TEXT}; font-size: 10.5pt; }}
QLabel#title {{ color: {GOLD_DEEP}; }}
QLabel#subtitle, QLabel#status {{ color: {TEXT_MUTED}; }}
QLabel#sectionTitle {{ color: {GOLD_DEEP}; font-weight: 600; letter-spacing: 1px; }}

/* chat */
QScrollArea#chat, QWidget#chatBody {{ background: transparent; border: none; }}
QFrame#userBubble {{
    background: {GOLD_PALE}; border: 1px solid {GOLD_LIGHT};
    border-radius: 16px; border-bottom-right-radius: 4px;
}}
QFrame#parkerBubble {{
    background: #FFFFFF; border: 1px solid {LINE};
    border-radius: 16px; border-bottom-left-radius: 4px;
}}
QLabel#bubbleText {{ background: transparent; border: none; }}
QLabel#bubbleMeta {{ background: transparent; color: {TEXT_MUTED}; font-size: 8.5pt; }}
QLabel#note {{ color: {TEXT_MUTED}; font-style: italic; }}
QLabel#error {{ color: {ERROR}; }}

/* inputs */
QLineEdit, QDateEdit {{
    background: #FFFFFF; border: 1px solid {LINE}; border-radius: 12px;
    padding: 8px 12px; selection-background-color: {GOLD_LIGHT};
}}
QLineEdit:focus, QDateEdit:focus {{ border: 1px solid {GOLD}; }}
QDateEdit::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right; width: 22px; border: none;
}}

/* buttons */
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {GOLD_LIGHT}, stop:1 {GOLD});
    color: #FFFFFF; border: none; border-radius: 12px; padding: 8px 16px; font-weight: 600;
}}
QPushButton:hover {{ background: {GOLD}; }}
QPushButton:pressed {{ background: {GOLD_DEEP}; }}
QPushButton:disabled {{ background: #E9E1C8; color: #FFFFFF; }}
QPushButton#secondary {{
    background: transparent; color: {GOLD_DEEP}; border: 1px solid {GOLD_LIGHT};
}}
QPushButton#secondary:hover {{ background: {GOLD_PALE}; }}
QPushButton#talk {{
    border-radius: 30px; min-width: 60px; max-width: 60px; min-height: 60px; max-height: 60px;
    padding: 0; font-size: 10pt;
    background: qradialgradient(cx:0.5, cy:0.4, radius:0.7, stop:0 #F7DE8E, stop:1 {GOLD});
}}
QPushButton#talk[listening="true"] {{
    background: qradialgradient(cx:0.5, cy:0.4, radius:0.7, stop:0 #FFFFFF, stop:1 #E7B93C);
    color: {GOLD_DEEP};
}}

/* sidebar */
QFrame#sidebar {{
    background: {PANEL}; border-left: 1px solid {LINE};
}}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {TEXT_MUTED}; padding: 8px 18px; border: none;
    border-bottom: 2px solid transparent; font-weight: 600;
}}
QTabBar::tab:selected {{ color: {GOLD_DEEP}; border-bottom: 2px solid {GOLD}; }}
QListWidget {{
    background: #FFFFFF; border: 1px solid {LINE}; border-radius: 12px; padding: 4px;
}}
QListWidget::item {{ padding: 6px 8px; border-radius: 8px; }}
QListWidget::item:selected {{ background: {GOLD_PALE}; color: {TEXT}; }}
QCheckBox {{ color: {TEXT_MUTED}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px; border: 1px solid {GOLD_LIGHT}; background: #FFFFFF;
}}
QCheckBox::indicator:checked {{ background: {GOLD}; border: 1px solid {GOLD}; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {GOLD_LIGHT}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""
