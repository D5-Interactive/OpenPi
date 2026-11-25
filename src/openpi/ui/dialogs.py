"""Render pi's extension UI requests (`ctx.ui.*`) as real dialogs.

pi resolves a dialog itself when the request carries a `timeout`, so on timeout we close the
dialog without replying — a late `extension_ui_response` would answer a request that no longer
exists.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


def handle_ui_request(request, session, parent: QWidget | None = None) -> None:
    dialog = QDialog(parent)
    dialog.setWindowTitle(request.title or "pi")
    dialog.setMinimumWidth(420)
    layout = QVBoxLayout(dialog)
    if request.message:
        layout.addWidget(QLabel(request.message))

    timed_out = {"value": False}
    field = None

    if request.method == "select":
        widget = QListWidget()
        widget.addItems(request.options)
        if request.options:
            widget.setCurrentRow(0)
        widget.itemDoubleClicked.connect(lambda _item: dialog.accept())
        layout.addWidget(widget)
        field = widget
    elif request.method == "input":
        widget = QLineEdit()
        widget.setPlaceholderText(request.placeholder)
        widget.setText(request.prefill)
        layout.addWidget(widget)
        field = widget
    elif request.method == "editor":
        widget = QPlainTextEdit()
        widget.setPlainText(request.prefill)
        widget.setMinimumHeight(220)
        layout.addWidget(widget)
        field = widget

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        if request.method != "confirm"
        else QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if field is not None:
        field.setFocus()

    if request.timeout:
        QTimer.singleShot(int(request.timeout), lambda: (timed_out.__setitem__("value", True),
                                                         dialog.reject()))

    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    if timed_out["value"]:
        return

    if request.method == "confirm":
        session.answer_ui(request.id, confirmed=bool(accepted))
    elif request.method == "select":
        value = field.currentItem().text() if accepted and field.currentItem() else None
        session.answer_ui(request.id, value=value, cancelled=value is None)
    elif request.method == "input":
        value = field.text() if accepted else None
        session.answer_ui(request.id, value=value, cancelled=value is None)
    elif request.method == "editor":
        value = field.toPlainText() if accepted else None
        session.answer_ui(request.id, value=value, cancelled=value is None)
