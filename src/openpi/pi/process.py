"""Spawn and talk to `pi --mode rpc`.

Uses QProcess so records arrive as Qt signals on the GUI thread; no reader thread, no qasync.
Records are split on LF only (see protocol/codec.py).
"""

from __future__ import annotations

import os

import msgspec
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from openpi.protocol.codec import encode_record


def pi_binary() -> str:
    return os.environ.get("OPENPI_PI_BINARY", "pi")


class PiProcess(QObject):
    record = Signal(object)      # any parsed JSON record, in arrival order
    stderr_line = Signal(str)
    exited = Signal(int)

    def __init__(self, argv: list[str], cwd: str | None = None, env: dict | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._argv = argv
        self._buffer = bytearray()
        self._counter = 0
        self._proc = QProcess(self)
        self._proc.setProgram(argv[0])
        self._proc.setArguments(argv[1:])
        if cwd:
            self._proc.setWorkingDirectory(cwd)
        if env:
            qenv = QProcessEnvironment.systemEnvironment()
            for key, value in env.items():
                qenv.insert(key, value)
            self._proc.setProcessEnvironment(qenv)
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        self._proc.readyReadStandardOutput.connect(self._read_stdout)
        self._proc.readyReadStandardError.connect(self._read_stderr)
        self._proc.finished.connect(lambda code, _status: self.exited.emit(code))
        self._proc.errorOccurred.connect(
            lambda err: self.stderr_line.emit(f"pi process error: {err.name}")
        )

    # -- lifecycle -------------------------------------------------------

    def start(self) -> None:
        self._proc.start()

    def wait_for_started(self, timeout_ms: int = 5000) -> bool:
        return self._proc.waitForStarted(timeout_ms)

    @property
    def is_running(self) -> bool:
        return self._proc.state() != QProcess.ProcessState.NotRunning

    def close(self, grace_ms: int = 3000) -> None:
        if not self.is_running:
            return
        self._proc.closeWriteChannel()
        if not self._proc.waitForFinished(grace_ms):
            self._proc.terminate()
            if not self._proc.waitForFinished(1000):
                self._proc.kill()
                self._proc.waitForFinished(1000)

    # -- io --------------------------------------------------------------

    def send(self, command: dict) -> str:
        command = dict(command)
        if not command.get("id"):
            self._counter += 1
            command["id"] = str(self._counter)
        self._proc.write(encode_record(command))
        return command["id"]

    def _read_stdout(self) -> None:
        self._buffer.extend(bytes(self._proc.readAllStandardOutput()))
        while b"\n" in self._buffer:
            raw, _, rest = bytes(self._buffer).partition(b"\n")
            self._buffer = bytearray(rest)
            line = raw.rstrip(b"\r")
            if not line.strip():
                continue
            try:
                self.record.emit(msgspec.json.decode(line))
            except msgspec.DecodeError as exc:
                self.stderr_line.emit(f"unparseable record dropped: {exc}")

    def _read_stderr(self) -> None:
        text = bytes(self._proc.readAllStandardError()).decode("utf-8", "replace")
        for line in text.splitlines():
            if line.strip():
                self.stderr_line.emit(line)
