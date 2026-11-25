"""Theme system: one palette object drives every color, QSS is generated from it.

Modes are dark and light (plus `system`, which follows the OS). Zoom is handled by scaling the
application font — see `apply_zoom` — so every widget scales together and nothing is hardcoded
in pixels beyond base spacing.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

MONO = "'JetBrains Mono','DejaVu Sans Mono',ui-monospace,monospace"


@dataclass(frozen=True)
class Palette:
    bg: str
    surface: str
    surface2: str
    border: str
    text: str
    muted: str
    accent: str
    accent_fg: str
    success: str
    warning: str
    danger: str
    code_bg: str
    code_fg: str


DARK = Palette(
    bg="#16181d", surface="#1c1f26", surface2="#232733", border="#2e333d",
    text="#e6e8ec", muted="#8b93a1", accent="#6ea8fe", accent_fg="#0b1220",
    success="#4ec9a0", warning="#e0b050", danger="#e06c75",
    code_bg="#191c22", code_fg="#c9d1d9",
)

LIGHT = Palette(
    bg="#f5f6f8", surface="#ffffff", surface2="#eef0f3", border="#d6dae1",
    text="#1f2328", muted="#6b7280", accent="#2f6fed", accent_fg="#ffffff",
    success="#1a7f4b", warning="#9a6700", danger="#c0392b",
    code_bg="#f0f1f4", code_fg="#24292f",
)

# Module-level color aliases, updated by apply(); widget code reads these directly.
BG = DARK.bg
PANEL = DARK.surface
PANEL_2 = DARK.surface2
LINE = DARK.border
TEXT = DARK.text
DIM = DARK.muted
ACCENT = DARK.accent
OK = DARK.success
WARN = DARK.warning
ERR = DARK.danger
CODE_BG = DARK.code_bg
CODE_FG = DARK.code_fg


def resolve_mode(mode: str) -> str:
    if mode == "system":
        app = QApplication.instance()
        if app is not None and app.styleHints().colorScheme().name.lower() == "dark":
            return "dark"
        return "light"
    return "dark" if mode == "dark" else "light"


def palette(mode: str) -> Palette:
    return DARK if resolve_mode(mode) == "dark" else LIGHT


def _qss(p: Palette) -> str:
    return f"""
* {{ outline: 0; }}
QWidget {{ background: {p.bg}; color: {p.text}; font-size: 13px; }}
QMainWindow, QDialog {{ background: {p.bg}; }}
QLabel#muted, QLabel#stats {{ color: {p.muted}; }}
QLabel#role {{ color: {p.muted}; font-size: 10px; }}

QListWidget, QTreeWidget, QListView {{ background: {p.surface}; border: none;
    border-radius: 8px; padding: 4px; alternate-background-color: {p.surface2}; }}
QListWidget::item, QTreeWidget::item, QListView::item {{ padding: 6px 10px; border-radius: 6px; }}
QListWidget::item:selected, QTreeWidget::item:selected, QListView::item:selected {{
    background: {p.accent}; color: {p.accent_fg}; }}
QListWidget::item:hover:!selected, QTreeWidget::item:hover:!selected {{
    background: {p.surface2}; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QPlainTextEdit, QTextEdit, QLineEdit {{ background: {p.surface}; border: 1px solid {p.border};
    border-radius: 8px; padding: 6px; selection-background-color: {p.accent};
    selection-color: {p.accent_fg}; }}
QPlainTextEdit:focus, QTextEdit:focus, QLineEdit:focus {{ border-color: {p.accent}; }}

QPushButton {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 7px;
    padding: 5px 12px; }}
QPushButton:hover {{ background: {p.border}; }}
QPushButton:pressed {{ background: {p.surface2}; }}
QPushButton:checked {{ background: {p.accent}; color: {p.accent_fg}; border-color: {p.accent}; }}
QPushButton#send {{ background: {p.accent}; color: {p.accent_fg}; border: none; font-weight: 600; }}
QPushButton#send:disabled {{ background: {p.surface2}; color: {p.muted}; }}
QPushButton#stop {{ background: transparent; border-color: {p.danger}; color: {p.danger}; }}
QPushButton#flat {{ background: transparent; border: none; color: {p.muted}; }}
QPushButton#flat:hover {{ color: {p.text}; }}

QToolButton {{ border: none; color: {p.muted}; border-radius: 6px; padding: 4px; }}
QToolButton:hover {{ color: {p.text}; background: {p.surface2}; }}

QComboBox {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 7px;
    padding: 4px 8px; min-height: 22px; }}
QComboBox:focus {{ border-color: {p.accent}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{ background: {p.surface}; border: 1px solid {p.border};
    selection-background-color: {p.accent}; selection-color: {p.accent_fg}; }}

QFrame#card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 10px; }}
QFrame#userCard {{ background: {p.surface2}; border: 1px solid {p.border}; border-radius: 10px; }}
QFrame#notice {{ background: transparent; }}

QProgressBar {{ background: {p.surface2}; border: none; border-radius: 4px; height: 6px;
    text-align: center; color: transparent; }}
QProgressBar::chunk {{ border-radius: 4px; }}

QStatusBar {{ background: {p.surface}; color: {p.muted}; border-top: 1px solid {p.border}; }}
QSplitter::handle {{ background: {p.border}; }}
QSplitter::handle:hover {{ background: {p.accent}; }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.border}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p.muted}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p.border}; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {p.muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QTabWidget::pane {{ border: 1px solid {p.border}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {p.muted}; padding: 7px 14px;
    border-bottom: 2px solid transparent; }}
QTabBar::tab:selected {{ color: {p.text}; border-bottom: 2px solid {p.accent}; }}
QTabBar::tab:hover {{ color: {p.text}; }}

QMenu {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: {p.accent}; color: {p.accent_fg}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 4px 8px; }}

QToolTip {{ background: {p.surface2}; color: {p.text}; border: 1px solid {p.border};
    border-radius: 4px; padding: 4px 6px; }}
"""


def apply(app: QApplication, mode: str = "dark") -> None:
    global BG, PANEL, PANEL_2, LINE, TEXT, DIM, ACCENT, OK, WARN, ERR
    p = palette(mode)
    (BG, PANEL, PANEL_2, LINE, TEXT, DIM, ACCENT, OK, WARN, ERR, CODE_BG, CODE_FG) = (
        p.bg, p.surface, p.surface2, p.border, p.text, p.muted, p.accent,
        p.success, p.warning, p.danger, p.code_bg, p.code_fg)
    app.setStyleSheet(_qss(p))
    app_palette = app.palette()
    app_palette.setColor(QPalette.ColorRole.Window, QColor(p.bg))
    app_palette.setColor(QPalette.ColorRole.Base, QColor(p.surface))
    app_palette.setColor(QPalette.ColorRole.Text, QColor(p.text))
    app_palette.setColor(QPalette.ColorRole.Highlight, QColor(p.accent))
    app.setPalette(app_palette)


def apply_zoom(app: QApplication, level: int) -> None:
    """level 0 = default; each step moves the app font ~1pt. Everything scales with it."""
    font = QFont(app.font())
    font.setPointSize(max(7, 10 + level))
    app.setFont(font)
