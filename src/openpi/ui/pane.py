"""One session's whole surface: header controls, transcript, composer, context footer."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .composer import Composer
from .dialogs import handle_ui_request
from .transcript import TranscriptView


def fmt_tokens(count: int | None) -> str:
    if not count:
        return "0"
    if count >= 1000:
        return f"{count / 1000:.0f}k"
    return str(count)


class SessionPane(QWidget):
    close_requested = Signal()
    status = Signal(str)

    def __init__(self, session, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(14, 8, 14, 6)
        header.setSpacing(8)
        self.name = QLabel()
        self.name.setStyleSheet("font-weight:600; font-size:14px;")
        self.rename_button = QPushButton("✎")
        self.rename_button.setFixedWidth(28)
        self.rename_button.setToolTip("Rename session")
        self.rename_button.clicked.connect(self._rename)
        self.model = QComboBox()
        self.model.setMinimumWidth(220)
        self.model.setToolTip("Model")
        self.model.activated.connect(self._model_chosen)
        self.thinking = QComboBox()
        self.thinking.setToolTip("Thinking level")
        self.thinking.activated.connect(self._thinking_chosen)
        self.state_label = QLabel()
        self.state_label.setObjectName("muted")
        close = QPushButton("✕")
        close.setFixedWidth(28)
        close.setToolTip("Close session (pi keeps the transcript on disk)")
        close.clicked.connect(self.close_requested)
        header.addWidget(self.name)
        header.addWidget(self.rename_button)
        header.addWidget(self.model)
        header.addWidget(self.thinking)
        header.addWidget(self.state_label, 1)
        header.addWidget(close)
        layout.addLayout(header)

        self.transcript = TranscriptView()
        layout.addWidget(self.transcript, 1)

        self.composer = Composer()
        self.composer.set_commands(session.commands)
        layout.addWidget(self.composer)

        footer = QHBoxLayout()
        footer.setContentsMargins(14, 0, 14, 8)
        footer.setSpacing(10)
        self.context_bar = QProgressBar()
        self.context_bar.setFixedWidth(120)
        self.context_bar.setRange(0, 100)
        self.context_bar.setTextVisible(False)
        self.context = QLabel()
        self.context.setObjectName("stats")
        self.cost = QLabel()
        self.cost.setObjectName("stats")
        self.cwd = QLabel(session.cwd or "")
        self.cwd.setObjectName("stats")
        footer.addWidget(QLabel("context"))
        footer.addWidget(self.context_bar)
        footer.addWidget(self.context)
        footer.addWidget(self.cost)
        footer.addStretch(1)
        footer.addWidget(self.cwd)
        layout.addLayout(footer)

        self.composer.submitted.connect(self._send)
        self.composer.abort_requested.connect(self._abort)
        session.changed.connect(self._refresh)
        session.state_changed.connect(self._refresh_state)
        session.ui_request.connect(lambda request: handle_ui_request(request, session, self))
        session.notify.connect(self._notify)
        session.failed.connect(self._failed)

        self._refresh()
        self._refresh_state()

    # -- actions ---------------------------------------------------------

    def _send(self, text: str, images=None) -> None:
        if self.session.transcript.busy:
            self.session.steer(text)
        else:
            self.session.prompt(text, images=images)

    def _abort(self) -> None:
        self.session.clear_queue()
        self.session.abort()

    def _rename(self) -> None:
        current = self.session.state.session_name or ""
        name, ok = QInputDialog.getText(self, "Rename session", "Name:", text=current)
        if ok and name.strip():
            self.session.rename(name.strip())

    def _model_chosen(self, index: int) -> None:
        data = self.model.itemData(index)
        if data:
            self.session.set_model(data[0], data[1])

    def _thinking_chosen(self, index: int) -> None:
        level = self.thinking.itemText(index)
        if level:
            self.session.set_thinking(level)

    # -- rendering -------------------------------------------------------

    def _refresh(self) -> None:
        self.transcript.render(self.session.transcript)
        self.composer.set_busy(self.session.transcript.busy)
        steering, follow_up = self.session.transcript.queued
        self.composer.set_queue(steering, follow_up)
        self.state_label.setText("working" if self.session.transcript.busy else "")

    def _refresh_state(self) -> None:
        state = self.session.state
        self.name.setText(state.session_name or "new session")
        self.cwd.setText(self.session.cwd or "")

        signature = (len(self.session.models), self.session.models[0].id if self.session.models else "")
        if self.session.models and signature != getattr(self, "_model_sig", None):
            self._model_sig = signature
            self.model.blockSignals(True)
            current = self.model.currentData()
            self.model.clear()
            for model in self.session.models:
                self.model.addItem(model.name or model.label, (model.provider, model.id))
            if current:
                index = self.model.findData(current)
                if index >= 0:
                    self.model.setCurrentIndex(index)
            self.model.blockSignals(False)

        levels = list(self.session.levels) or ["off", "minimal", "low", "medium", "high"]
        if state.thinking_level not in levels:
            levels = [*levels, state.thinking_level]
        if getattr(self, "_level_sig", None) != levels:
            self._level_sig = levels
            self.thinking.blockSignals(True)
            self.thinking.clear()
            self.thinking.addItems(levels)
            self.thinking.blockSignals(False)
        if self.thinking.currentText() != state.thinking_level:
            self.thinking.setCurrentText(state.thinking_level)

        stats = self.session.stats
        if stats and stats.context_usage:
            usage = stats.context_usage
            percent = int(usage.percent or 0)
            self.context_bar.setValue(percent)
            self.context_bar.setStyleSheet(
                f"QProgressBar::chunk {{ background: "
                f"{theme.OK if percent < 60 else theme.WARN if percent < 85 else theme.ERR};"
                " border-radius:3px; }"
            )
            self.context.setText(f"{fmt_tokens(usage.tokens)} / {fmt_tokens(usage.contextWindow)}"
                                 f" · {percent}%")
            self.cost.setText(f"${stats.cost:.2f}")
        elif stats:
            self.cost.setText(f"${stats.cost:.2f}")

    def _notify(self, message: str, kind: str) -> None:
        if kind == "editor":
            self.composer.set_text(message)
            return
        prefix = {"warning": "⚠ ", "error": "✕ "}.get(kind, "")
        self.status.emit(prefix + message)

    def _failed(self, message: str) -> None:
        self.status.emit(f"pi: {message}")
