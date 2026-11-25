"""Run a blocking function off the GUI thread and deliver its result as a signal."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

_alive: set["_Worker"] = set()


class _Worker(QObject):
    done = Signal(object)
    failed = Signal(str)


def run_async(fn, on_done, on_error=None) -> None:
    worker = _Worker()
    _alive.add(worker)

    def run() -> None:
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - surfaced in the UI
            worker.failed.emit(str(exc))
        else:
            worker.done.emit(result)
        finally:
            _alive.discard(worker)

    worker.done.connect(on_done)
    if on_error is not None:
        worker.failed.connect(on_error)
    threading.Thread(target=run, daemon=True).start()
