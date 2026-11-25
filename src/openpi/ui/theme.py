"""One palette, one stylesheet. Widgets opt in with object names and properties."""

from __future__ import annotations

BG = "#16181d"
PANEL = "#1c1f26"
PANEL_2 = "#22262f"
LINE = "#2e333d"
TEXT = "#e6e8ec"
DIM = "#8b93a1"
ACCENT = "#6ea8fe"
OK = "#4ec9a0"
WARN = "#e0b050"
ERR = "#e06c75"
MONO = "'JetBrains Mono','DejaVu Sans Mono',monospace"

QSS = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: 13px; }}
QMainWindow, QDialog {{ background: {BG}; }}
QListWidget {{ background: {PANEL}; border: none; outline: 0; }}
QListWidget::item {{ padding: 6px 10px; border-radius: 6px; }}
QListWidget::item:selected {{ background: #2a3038; color: {TEXT}; border: none; }}
QListWidget::item:selected:!active {{ background: #262b34; }}
QListView {{ outline: 0; }}
QListWidget::item:hover {{ background: #262b34; }}
QScrollArea {{ border: none; }}
QPlainTextEdit {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 8px;
                  padding: 6px; selection-background-color: #33415c; }}
QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
QPushButton {{ background: {PANEL_2}; border: 1px solid {LINE}; border-radius: 6px;
               padding: 4px 10px; }}
QPushButton:hover {{ background: #2b313b; }}
QPushButton#send {{ background: {ACCENT}; color: #0b1220; border: none; font-weight: 600; }}
QPushButton#send:disabled {{ background: #33415c; color: {DIM}; }}
QPushButton#stop {{ background: #3a2b2e; border-color: {ERR}; color: {ERR}; }}
QComboBox {{ background: {PANEL_2}; border: 1px solid {LINE}; border-radius: 6px;
             padding: 3px 8px; }}
QComboBox QAbstractItemView {{ background: {PANEL}; selection-background-color: #33415c; }}
QLabel#muted, QLabel#stats {{ color: {DIM}; }}
QLabel#role {{ color: {DIM}; font-size: 10px; }}
QFrame#card {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 8px; }}
QFrame#userCard {{ background: #1f2530; border: 1px solid #2a3446; border-radius: 8px; }}
QFrame#notice {{ background: transparent; }}
QToolButton {{ border: none; color: {DIM}; }}
QToolButton:hover {{ color: {TEXT}; }}
QStatusBar {{ background: {PANEL}; color: {DIM}; border-top: 1px solid {LINE}; }}
QProgressBar {{ background: #2b303a; border: none; border-radius: 3px; height: 5px;
                text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {OK}; border-radius: 3px; }}
QSplitter::handle {{ background: {LINE}; width: 1px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #3a4048; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}
"""


def apply(app) -> None:
    app.setStyleSheet(QSS)
