"""One pi process, one session: protocol plumbing plus the renderable transcript."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from openpi.pi.process import PiProcess
from openpi.pi.transcript import Transcript
from openpi.protocol import records
from openpi.protocol.records import (
    AvailableModels,
    CommandInfo,
    Commands,
    Entries,
    ExtensionUIRequest,
    Model,
    SessionStats,
    State,
    ThinkingLevels,
)


class PiSession(QObject):
    changed = Signal()                 # transcript or busy state changed
    state_changed = Signal()           # model, name, stats, thinking level
    ready = Signal()
    ui_request = Signal(object)        # ExtensionUIRequest that needs an answer
    notify = Signal(str, str)          # message, notify type
    failed = Signal(str)

    def __init__(self, argv: list[str], cwd: str | None = None, session_path: str | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.argv = argv
        self.cwd = cwd
        self.session_path = session_path
        self.process = PiProcess(argv, cwd, parent=self)
        self.process.record.connect(self._on_record)
        self.process.stderr_line.connect(self.failed)
        self.process.exited.connect(self._on_exit)
        self.transcript = Transcript()
        self.state = State()
        self.stats: SessionStats | None = None
        self.models: list[Model] = []
        self.levels: list[str] = []
        self.commands: list[CommandInfo] = []
        self.ready_seen = False
        self._backfilled = False
        self._alive = False

    # -- lifecycle -------------------------------------------------------

    def start(self) -> None:
        self.process.start()
        if not self.process.wait_for_started():
            self.failed.emit(f"could not start: {' '.join(self.argv)}")
            return
        self._alive = True
        self.refresh()

    def refresh(self) -> None:
        for command in ({"type": "get_state"}, {"type": "get_entries"},
                        {"type": "get_session_stats"}, {"type": "get_available_models"},
                        {"type": "get_available_thinking_levels"}, {"type": "get_commands"}):
            self.process.send(command)

    def close(self) -> None:
        self._alive = False
        self.process.close()

    @property
    def alive(self) -> bool:
        return self._alive

    def _on_exit(self, code: int) -> None:
        self._alive = False
        if code != 0:
            self.failed.emit(f"pi exited with code {code}")

    # -- commands --------------------------------------------------------

    def prompt(self, message: str, images: list[dict] | None = None,
               behavior: str | None = None) -> None:
        command = {"type": "prompt", "message": message}
        if images:
            command["images"] = images
        if behavior:
            command["streamingBehavior"] = behavior
        self.process.send(command)

    def steer(self, message: str) -> None:
        self.process.send({"type": "steer", "message": message})

    def follow_up(self, message: str) -> None:
        self.process.send({"type": "follow_up", "message": message})

    def abort(self) -> None:
        self.process.send({"type": "abort"})

    def clear_queue(self) -> None:
        self.process.send({"type": "clear_queue"})

    def set_model(self, provider: str, model_id: str) -> None:
        self.process.send({"type": "set_model", "provider": provider, "modelId": model_id})

    def set_thinking(self, level: str) -> None:
        self.process.send({"type": "set_thinking_level", "level": level})

    def rename(self, name: str) -> None:
        self.process.send({"type": "set_session_name", "name": name})

    def stats_now(self) -> None:
        self.process.send({"type": "get_session_stats"})

    def answer_ui(self, request_id: str, *, value=None, confirmed=None,
                  cancelled: bool = False) -> None:
        response = {"type": "extension_ui_response", "id": request_id}
        if cancelled:
            response["cancelled"] = True
        elif confirmed is not None:
            response["confirmed"] = confirmed
        else:
            response["value"] = value
        self.process.send(response)

    # -- records ---------------------------------------------------------

    def _on_record(self, record: dict) -> None:
        kind = record.get("type")
        if kind == "response":
            self._on_response(record)
        elif kind == "extension_ui_request":
            self._on_ui(record)
        else:
            self.transcript.apply(record)
            if kind == "session_info_changed":
                self.state.sessionName = record.get("name")
                self.state_changed.emit()
            elif kind == "thinking_level_changed":
                self.state.thinkingLevel = record.get("level", "off")
                self.state_changed.emit()
            elif kind == "agent_settled":
                self.state.isStreaming = False
                self.state_changed.emit()
                self.stats_now()
            elif kind == "agent_start":
                self.state.isStreaming = True
                self.state_changed.emit()
            self.changed.emit()

    def _on_response(self, record: dict) -> None:
        response = records.decode(record, records.Response)
        command = response.command
        if not response.success:
            if response.error and command not in ("abort",):
                self.failed.emit(response.error)
            return
        data = response.data or {}
        if command == "get_state":
            self.state = records.decode(data, State)
            self.state.isStreaming = self.transcript.busy or self.state.isStreaming
            if not self.ready_seen:
                self.ready_seen = True
                self.ready.emit()
            self.state_changed.emit()
        elif command == "get_entries" and not self._backfilled:
            entries = records.decode(data, Entries).entries
            self.transcript = Transcript.from_entries(entries)
            self._backfilled = True
            self.changed.emit()
        elif command == "get_session_stats":
            self.stats = records.decode(data, SessionStats)
            self.state_changed.emit()
        elif command == "get_available_models":
            self.models = records.decode(data, AvailableModels).models
            self.state_changed.emit()
        elif command == "get_available_thinking_levels":
            self.levels = records.decode(data, ThinkingLevels).levels
            self.state_changed.emit()
        elif command == "get_commands":
            self.commands = records.decode(data, Commands).commands

    def _on_ui(self, record: dict) -> None:
        request = records.decode(record, ExtensionUIRequest)
        if request.is_dialog:
            self.ui_request.emit(request)
        elif request.method == "notify":
            self.notify.emit(request.message, request.notifyType)
        elif request.method == "set_editor_text" and request.text:
            self.notify.emit(request.text, "editor")
