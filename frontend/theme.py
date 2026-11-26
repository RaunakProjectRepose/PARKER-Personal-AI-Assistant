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
    "loading": "WAKING UP",
    "idle": "READY",
    "listening": "LISTENING",
    "thinking": "THINKING",
    "speaking": "SPEAKING",
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
/* A soft glow of light from the top centre, fading to warm parchment. */
QMainWindow, #central {{
    background: qradialgradient(cx:0.5, cy:0.12, radius:1.0, fx:0.5, fy:0.08,
        stop:0 #FFFFFF, stop:0.45 {IVORY}, stop:1 {CREAM});
}}
QWidget {{ color: {TEXT}; font-size: 10.5pt; }}
QLabel#wordmark {{ color: {GOLD_DEEP}; }}
QLabel#status {{ color: {TEXT_MUTED}; letter-spacing: 2px; font-size: 8.5pt; }}
QLabel#drawerTitle {{ color: {GOLD_DEEP}; }}
QLabel#sectionTitle {{ color: {TEXT_MUTED}; font-size: 8pt; letter-spacing: 2px; font-weight: 600; }}
QLabel#empty {{ color: {TEXT_MUTED}; font-style: italic; }}

/* chat */
QScrollArea#chat, QWidget#chatBody {{ background: transparent; border: none; }}
QFrame#userBubble {{ background: {GOLD_PALE}; border: none; border-radius: 20px; }}
QFrame#parkerBubble {{ background: #FFFFFF; border: none; border-radius: 20px; }}
QLabel#bubbleText {{ background: transparent; border: none; font-size: 11pt; }}
QLabel#bubbleMeta {{ background: transparent; color: {TEXT_MUTED}; font-size: 8pt; }}
QPushButton#fileLink {{
    background: transparent; color: {TEXT}; border: none; border-radius: 10px;
    padding: 8px 10px; text-align: left; font-weight: 500; font-size: 10.5pt;
}}
QPushButton#fileLink:hover {{ background: {GOLD_PALE}; color: {GOLD_DEEP}; }}
QLabel#note {{ color: {TEXT_MUTED}; font-style: italic; font-size: 9.5pt; }}
QLabel#error {{ color: {ERROR}; font-size: 9.5pt; }}

/* the message bar */
QFrame#composer {{ background: #FFFFFF; border: none; border-radius: 28px; }}
QLineEdit#composerInput {{
    background: transparent; border: none; padding: 0 6px; font-size: 11pt;
    selection-background-color: {GOLD_LIGHT};
}}
QToolButton#sendButton {{ background: transparent; border: none; border-radius: 18px; }}
QToolButton#sendButton:hover {{ background: {GOLD_PALE}; }}
QToolButton#micButton {{
    border: none; border-radius: 22px;
    background: qradialgradient(cx:0.5, cy:0.35, radius:0.75, stop:0 #F2D88A, stop:1 {GOLD});
}}
QToolButton#micButton:hover {{
    background: qradialgradient(cx:0.5, cy:0.35, radius:0.75, stop:0 #F6E2A4, stop:1 #D2AC33);
}}
QToolButton#micButton:disabled {{ background: #EDE5CC; }}
QToolButton#micButton[mode="listening"] {{
    background: qradialgradient(cx:0.5, cy:0.35, radius:0.75, stop:0 #FFFFFF, stop:1 #EBC350);
}}
QToolButton#micButton[mode="speaking"] {{ background: {GOLD_DEEP}; }}

/* header icon buttons */
QToolButton#iconButton {{ background: transparent; border: none; border-radius: 18px; }}
QToolButton#iconButton:hover {{ background: rgba(201, 162, 39, 0.12); }}
QToolButton#iconButton:checked {{ background: rgba(201, 162, 39, 0.20); }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

/* settings menu */
QMenu {{ background: #FFFFFF; border: 1px solid {LINE}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 8px 18px; border-radius: 8px; color: {TEXT}; }}
QMenu::item:selected {{ background: {GOLD_PALE}; }}
QMenu::item:disabled {{ color: {TEXT_MUTED}; }}
QMenu::separator {{ height: 1px; background: {LINE}; margin: 4px 8px; }}
QMenu::indicator {{ width: 14px; height: 14px; border-radius: 4px; border: 1px solid {GOLD_LIGHT}; }}
QMenu::indicator:checked {{ background: {GOLD}; border: 1px solid {GOLD}; }}

/* drawer (agenda / memories) */
QFrame#drawer {{ background: rgba(255, 252, 243, 0.97); border-left: 1px solid {LINE}; }}
QLineEdit, QDateEdit {{
    background: #FFFFFF; border: 1px solid {LINE}; border-radius: 12px;
    padding: 8px 12px; selection-background-color: {GOLD_LIGHT};
}}
QLineEdit:focus, QDateEdit:focus {{ border: 1px solid {GOLD}; }}
QDateEdit::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right; width: 22px; border: none;
}}
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{
    background: #FFFFFF; border-radius: 12px; padding: 10px 12px; margin: 3px 0;
}}
QListWidget::item:selected {{ background: {GOLD_PALE}; color: {TEXT}; }}
QListWidget::item:hover {{ background: #FFFDF5; }}
QListWidget::indicator {{
    width: 16px; height: 16px; border-radius: 8px; border: 1px solid {GOLD_LIGHT}; background: #FFFFFF;
}}
QListWidget::indicator:checked {{ background: {GOLD}; border: 1px solid {GOLD}; }}
QPushButton {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {GOLD_LIGHT}, stop:1 {GOLD});
    color: #FFFFFF; border: none; border-radius: 12px; padding: 8px 16px; font-weight: 600;
}}
QPushButton:hover {{ background: {GOLD}; }}
QPushButton:pressed {{ background: {GOLD_DEEP}; }}
QPushButton#secondary {{ background: transparent; color: {GOLD_DEEP}; border: 1px solid {GOLD_LIGHT}; }}
QPushButton#secondary:hover {{ background: {GOLD_PALE}; }}
QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(201, 162, 39, 0.35); border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
