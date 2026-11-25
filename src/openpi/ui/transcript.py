"""Transcript rendering.

Blocks come from pi.transcript.Transcript. Widgets are keyed by block uid and updated in
place, so streaming does not rebuild the page.

shortcut: only the newest MAX_BLOCKS blocks are rendered. Older ones come back through the
session tree (M2) rather than a "load earlier" button.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .markdown import render_markdown

MAX_BLOCKS = 200

ROLE_LABELS = {"user": "you", "text": "assistant", "thinking": "thinking"}
STATUS = {
    "tool": ("running", theme.WARN),
}


class BlockWidget(QFrame):
    def __init__(self, block, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.uid = block.uid
        self.kind = block.kind
        self._signature = None
        self._detail_visible = False

        if block.kind == "user":
            self.setObjectName("userCard")
        elif block.kind == "notice":
            self.setObjectName("notice")
        elif block.kind in ("tool", "bash"):
            self.setObjectName("card")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 7, 10, 7)
        outer.setSpacing(4)

        self.header = QHBoxLayout()
        self.header.setSpacing(8)
        self.title = QLabel()
        self.title.setObjectName("role" if block.kind in ("user", "text", "thinking") else "muted")
        if block.kind in ("tool", "bash"):
            self.title.setStyleSheet(f"font-family:{theme.MONO}; color:{theme.ACCENT};")
        elif block.kind == "notice":
            self.title.setStyleSheet(f"color:{theme.DIM}; font-size:11px;")
        self.summary = QLabel()
        self.summary.setObjectName("muted")
        if block.kind in ("tool", "bash"):
            self.summary.setStyleSheet(f"font-family:{theme.MONO}; font-size:11px;")
        self.status = QLabel()
        self.status.setObjectName("muted")
        self.header.addWidget(self.title)
        self.header.addWidget(self.summary, 1)
        self.header.addWidget(self.status)
        self.toggle = QToolButton()
        self.toggle.setText("▸")
        self.toggle.setVisible(block.kind in ("tool", "bash"))
        self.toggle.clicked.connect(self._toggle_detail)
        self.header.addWidget(self.toggle)
        outer.addLayout(self.header)

        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        if block.kind == "notice":
            self.text.setStyleSheet(f"color:{theme.DIM}; font-size:11px;")
        outer.addWidget(self.text)

        self.detail = QLabel()
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet(
            f"font-family:{theme.MONO}; font-size:11.5px; color:{theme.CODE_FG};"
            f"background:{theme.CODE_BG}; border-radius:6px; padding:8px;"
        )
        self.detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.detail.setVisible(False)
        outer.addWidget(self.detail)

        if block.kind == "thinking":
            self.text.setStyleSheet(f"color:{theme.DIM}; font-style:italic; font-size:12px;")
        if block.kind == "user":
            self.text.setStyleSheet(f"color:{theme.TEXT};")

    def _toggle_detail(self) -> None:
        self._detail_visible = not self._detail_visible
        self.detail.setVisible(self._detail_visible)
        self.toggle.setText("▾" if self._detail_visible else "▸")

    def update_block(self, block, streaming: bool, force: bool = False) -> None:
        signature = (block.kind, block.text, block.result, block.name, block.is_error,
                     block.duration_ms, tuple(sorted(block.args.items())), streaming)
        if signature == self._signature and not force:
            return
        self._signature = signature

        if block.kind in ("tool", "bash"):
            self.title.setText(block.name if block.kind == "tool" else "bash")
            command = block.args.get("command") if block.kind == "tool" else None
            self.summary.setText(str(command) if command else "")
            self.text.setVisible(False)
            if block.kind == "bash":
                detail = block.result
            else:
                args = "\n".join(f"{k}: {v}" for k, v in block.args.items()) if block.args else ""
                detail = args
                if block.result:
                    detail = f"{detail}\n\n{block.result}" if detail else block.result
            self.detail.setText(detail)
            if not block.result and not block.args:
                self.status.setText("running")
                self.status.setStyleSheet(f"color:{theme.WARN};")
            elif block.is_error:
                self.status.setText("✗ error")
                self.status.setStyleSheet(f"color:{theme.ERR};")
            elif block.duration_ms is not None:
                self.status.setText(f"✓ {block.duration_ms} ms")
                self.status.setStyleSheet(f"color:{theme.OK};")
            else:
                self.status.setText("done")
                self.status.setStyleSheet(f"color:{theme.OK};")
            return

        self.title.setText(ROLE_LABELS.get(block.kind, ""))
        if block.kind == "thinking":
            self.text.setText(block.text)
        elif streaming:
            self.text.setTextFormat(Qt.TextFormat.PlainText)
            self.text.setText(block.text)
        else:
            self.text.setTextFormat(Qt.TextFormat.RichText)
            self.text.setText(render_markdown(block.text))
        if block.kind == "notice" and block.is_error:
            self.text.setStyleSheet(f"color:{theme.ERR}; font-size:11px;")
            self.title.setText("")


class TranscriptView(QScrollArea):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._inner = QWidget()
        self._layout = QVBoxLayout(self._inner)
        self._layout.setContentsMargins(14, 10, 14, 10)
        self._layout.setSpacing(6)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._widgets: dict[str, BlockWidget] = {}
        self._order: list[str] = []
        self.setWidget(self._inner)

    def block_count(self) -> int:
        return len(self._widgets)

    def visible_text(self) -> str:
        return "\n".join(w.text.text() for w in self._widgets.values())

    def _near_bottom(self) -> bool:
        bar = self.verticalScrollBar()
        return bar.value() >= bar.maximum() - 48

    def rebuild(self, transcript) -> None:
        """Drop and recreate every widget so inline theme colors are re-read (theme switch)."""
        for uid in list(self._widgets):
            widget = self._widgets.pop(uid)
            self._layout.removeWidget(widget)
            widget.deleteLater()
        self.render(transcript)

    def render(self, transcript, force: bool = False) -> None:
        should_scroll = self._near_bottom()
        blocks = transcript.blocks[-MAX_BLOCKS:]
        keep = {b.uid for b in blocks}
        for uid in list(self._widgets):
            if uid not in keep:
                widget = self._widgets.pop(uid)
                self._layout.removeWidget(widget)
                widget.deleteLater()
        for index, block in enumerate(blocks):
            widget = self._widgets.get(block.uid)
            if widget is None:
                widget = BlockWidget(block)
                self._widgets[block.uid] = widget
                self._layout.addWidget(widget)
            widget.update_block(block, streaming=transcript.streaming and index == len(blocks) - 1,
                                force=force)
        if should_scroll:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())
