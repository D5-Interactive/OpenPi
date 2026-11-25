from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_SLASH = re.compile(r"^/([\w:-]*)$")


class _Edit(QPlainTextEdit):
    submitted = Signal()
    escaped = Signal()
    text_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.textChanged.connect(self.text_changed)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if enter and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.submitted.emit()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.escaped.emit()
            return
        super().keyPressEvent(event)


class Composer(QWidget):
    submitted = Signal(str, object)   # message, images (list of {data, mimeType})
    abort_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._commands = []
        self._images: list[dict] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 10)
        layout.setSpacing(6)

        self.edit = _Edit()
        self.edit.setPlaceholderText("Ask pi…  Enter to send, Shift+Enter for a newline")
        self.edit.setFixedHeight(76)
        self.edit.submitted.connect(self._submit_or_accept)
        self.edit.escaped.connect(self._escape)
        self.edit.text_changed.connect(self._maybe_autocomplete)
        layout.addWidget(self.edit)

        self.chips = QLabel("")
        self.chips.setObjectName("muted")
        self.chips.setVisible(False)
        layout.addWidget(self.chips)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.commands_button = QPushButton("/")
        self.commands_button.setToolTip("Insert a skill, template, or extension command")
        self.commands_button.setFixedWidth(30)
        self.commands_button.clicked.connect(self._show_commands)
        self.attach_button = QPushButton("🖼")
        self.attach_button.setToolTip("Attach images")
        self.attach_button.setFixedWidth(30)
        self.attach_button.clicked.connect(self._attach_images)
        self.queue = QLabel("")
        self.queue.setObjectName("muted")
        self.send = QPushButton("Send")
        self.send.setObjectName("send")
        self.send.clicked.connect(self.submit)
        self.stop = QPushButton("Stop")
        self.stop.setObjectName("stop")
        self.stop.setVisible(False)
        self.stop.clicked.connect(self.abort_requested)
        bar.addWidget(self.commands_button)
        bar.addWidget(self.attach_button)
        bar.addWidget(self.queue, 1)
        bar.addWidget(self.stop)
        bar.addWidget(self.send)
        layout.addLayout(bar)

        # slash autocomplete popup
        self.popup = QListWidget()
        self.popup.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.popup.setMaximumHeight(180)
        self.popup.itemClicked.connect(self._accept_autocomplete)

    # -- api -------------------------------------------------------------

    def text(self) -> str:
        return self.edit.toPlainText()

    def set_text(self, text: str) -> None:
        self.edit.setPlainText(text)
        self.edit.moveCursor(QTextCursor.MoveOperation.End)

    def focus(self) -> None:
        self.edit.setFocus()

    def submit(self) -> None:
        message = self.edit.toPlainText().strip()
        if not message and not self._images:
            return
        self.edit.clear()
        images, self._images = self._images, []
        self._update_chips()
        self.submitted.emit(message, images)

    def set_busy(self, busy: bool) -> None:
        self.stop.setVisible(busy)
        self.send.setText("Queue" if busy else "Send")

    def set_queue(self, steering: int, follow_up: int) -> None:
        total = steering + follow_up
        self.queue.setText(f"{total} queued" if total else "")

    def set_commands(self, commands) -> None:
        self._commands = commands

    # -- images ----------------------------------------------------------

    def _attach_images(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Attach images", "",
                                                "Images (*.png *.jpg *.jpeg *.gif *.webp)")
        for path in paths:
            data = Path(path).read_bytes()
            mime = mimetypes.guess_type(path)[0] or "image/png"
            self._images.append({"data": base64.b64encode(data).decode(), "mimeType": mime})
        self._update_chips()

    def _update_chips(self) -> None:
        count = len(self._images)
        self.chips.setText(f"{count} image{'s' if count != 1 else ''} attached")
        self.chips.setVisible(count > 0)

    # -- slash autocomplete ----------------------------------------------

    def _matches(self, prefix: str) -> list[str]:
        names = [f"/{command.name}" for command in self._commands]
        return [name for name in names if name.startswith(prefix)][:12]

    def _maybe_autocomplete(self) -> None:
        text = self.edit.toPlainText()
        match = _SLASH.match(text)
        if match:
            names = self._matches(text)
            if not names:
                self.popup.hide()
                return
            self.popup.clear()
            self.popup.addItems(names)
            cursor = self.edit.cursorRect()
            point = self.edit.mapToGlobal(cursor.bottomLeft())
            self.popup.setCurrentRow(0)
            self.popup.move(point)
            self.popup.show()
            self.popup.setFocus()
        else:
            self.popup.hide()

    def _accept_autocomplete(self, item: QListWidgetItem) -> None:
        self.set_text(item.text() + " ")
        self.popup.hide()
        self.edit.setFocus()

    def _submit_or_accept(self) -> None:
        if self.popup.isVisible() and self.popup.currentItem():
            self._accept_autocomplete(self.popup.currentItem())
            return
        self.submit()

    def _show_commands(self) -> None:
        menu = QMenu(self)
        if not self._commands:
            menu.addAction("No commands loaded").setEnabled(False)
        for command in self._commands:
            label = f"/{command.name}" + (f" — {command.description}" if command.description else "")
            menu.addAction(label).setData(command.name)
        chosen = menu.exec(self.commands_button.mapToGlobal(self.commands_button.rect().bottomLeft()))
        if chosen and chosen.data():
            self.set_text(f"/{chosen.data()} ")

    def _escape(self) -> None:
        if self.popup.isVisible():
            self.popup.hide()
            return
        if self.text().strip():
            self.set_text("")
            return
        self.abort_requested.emit()
