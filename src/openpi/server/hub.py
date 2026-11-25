"""Server-side session registry and event fan-out.

The hub owns pi processes. Both the desktop app (in-process, later) and the web server talk to
it through the same block-level snapshots and patches, so the browser never re-implements the
transcript reducer.

All hub methods must be called on the Qt thread, except `subscribe`/`dispatch`, which are safe
to call from an HTTP worker: they marshal through `call()`/`post()`.
"""

from __future__ import annotations

import queue
import threading
from collections import deque
from dataclasses import asdict
from pathlib import Path

import msgspec
from PySide6.QtCore import QObject, QTimer, Signal

from openpi.pi.index import scan
from openpi.pi.session import PiSession


def _block_json(block) -> dict:
    data = asdict(block)
    return data


class SessionHub(QObject):
    sessions_changed = Signal()

    def __init__(self, argv_factory=None, cwd: str = "", session_root: Path | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.argv_factory = argv_factory or (lambda cwd, path: ["pi", "--mode", "rpc"])
        self.cwd = cwd or str(Path.cwd())
        self.session_root = session_root
        self._sessions: dict[str, PiSession] = {}
        self._meta: dict[str, dict] = {}
        self._subs: dict[str, list[queue.Queue]] = {}
        self._last: dict[str, dict] = {}
        self._counter = 0
        self._calls: deque = deque()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._drain)
        self._timer.start(30)

    # -- cross-thread plumbing -------------------------------------------

    def post(self, fn) -> None:
        self._calls.append(fn)

    def call(self, fn, timeout: float = 5.0):
        box: dict = {}
        done = threading.Event()

        def run() -> None:
            try:
                box["value"] = fn()
            except Exception as exc:  # noqa: BLE001 - reported to the caller
                box["error"] = exc
            finally:
                done.set()

        self.post(run)
        if not done.wait(timeout):
            raise TimeoutError("hub did not answer in time")
        if "error" in box:
            raise box["error"]
        return box.get("value")

    def _drain(self) -> None:
        while self._calls:
            fn = self._calls.popleft()
            fn()

    # -- sessions --------------------------------------------------------

    def open(self, session_path: str | None = None, cwd: str | None = None) -> str:
        self._counter += 1
        key = f"s{self._counter}"
        folder = cwd or self.cwd
        session = PiSession(self.argv_factory(folder, session_path), cwd=folder,
                            session_path=session_path, parent=self)
        self._sessions[key] = session
        self._meta[key] = {"key": key, "cwd": folder, "file": session_path, "title": ""}
        session.changed.connect(lambda: self._publish(key))
        session.state_changed.connect(lambda: self._publish(key))
        session.ready.connect(self._on_ready)
        session.ui_request.connect(lambda request: self._broadcast(key, {
            "t": "ui", "request": self._ui_json(request), "key": key}))
        session.notify.connect(lambda message, kind: self._broadcast(key, {
            "t": "notify", "message": message, "kind": kind, "key": key}))
        session.failed.connect(lambda message: self._broadcast(key, {
            "t": "notify", "message": message, "kind": "error", "key": key}))
        session.start()
        self.sessions_changed.emit()
        return key

    def _on_ready(self) -> None:
        for key, session in self._sessions.items():
            if session.state.session_file and not self._meta[key]["file"]:
                self._meta[key]["file"] = session.state.session_file
        self.sessions_changed.emit()

    def close(self, key: str) -> None:
        session = self._sessions.pop(key, None)
        if session is not None:
            session.close()
        self._meta.pop(key, None)
        self._subs.pop(key, None)
        self._last.pop(key, None)
        self.sessions_changed.emit()

    def shutdown(self) -> None:
        for key in list(self._sessions):
            self.close(key)
        self._timer.stop()

    def session(self, key: str) -> PiSession:
        return self._sessions[key]

    def has(self, key: str) -> bool:
        return key in self._sessions

    def sessions(self) -> list[dict]:
        return [self._meta_info(key) for key in self._sessions]

    def on_disk(self) -> list[dict]:
        metas = scan(self.session_root) if self.session_root else []
        return [{"cwd": m.cwd, "file": str(m.path), "title": m.title, "id": m.id}
                for m in metas]

    @staticmethod
    def _ui_json(request) -> dict:
        return {"id": request.id, "method": request.method, "title": request.title,
                "message": request.message, "options": request.options,
                "placeholder": request.placeholder, "prefill": request.prefill,
                "timeout": request.timeout}

    def _meta_info(self, key: str) -> dict:
        session = self._sessions[key]
        meta = self._meta[key]
        return {"key": key, "cwd": meta["cwd"], "file": meta["file"],
                "title": session.state.session_name or (session.transcript.blocks[0].text[:60]
                                                        if session.transcript.blocks else "")
                or Path(meta["cwd"]).name,
                "busy": session.transcript.busy}

    # -- state -----------------------------------------------------------

    def state_json(self) -> dict:
        return {"cwd": self.cwd, "sessions": self.sessions()}

    def snapshot(self, key: str) -> dict:
        session = self._sessions[key]
        return {
            "t": "snapshot",
            "key": key,
            "blocks": [_block_json(block) for block in session.transcript.blocks],
            "state": self._state_json(session),
            "stats": self._stats_json(session),
            "busy": session.transcript.busy,
            "queued": list(session.transcript.queued),
            "models": [{"id": m.id, "provider": m.provider, "name": m.name}
                       for m in session.models],
            "levels": session.levels,
            "commands": [{"name": c.name, "description": c.description}
                         for c in session.commands],
        }

    def _state_json(self, session) -> dict:
        state = session.state
        return {"name": state.session_name, "thinking": state.thinking_level,
                "model": {"id": state.model.id, "provider": state.model.provider,
                          "name": state.model.name} if state.model else None,
                "is_streaming": state.is_streaming}

    def _stats_json(self, session) -> dict:
        stats = session.stats
        if stats is None:
            return {}
        usage = stats.context_usage
        return {"cost": stats.cost,
                "context": {"tokens": usage.tokens, "window": usage.contextWindow,
                            "percent": usage.percent} if usage else None}

    # -- subscriptions ---------------------------------------------------

    def subscribe(self, key: str) -> queue.Queue:
        if key not in self._sessions:
            raise KeyError(key)
        events: queue.Queue = queue.Queue(maxsize=2000)
        events.put(self.snapshot(key))
        self._subs.setdefault(key, []).append(events)
        self._last.setdefault(key, {})
        return events

    def unsubscribe(self, key: str, events: queue.Queue) -> None:
        if key in self._subs and events in self._subs[key]:
            self._subs[key].remove(events)

    def _broadcast(self, key: str, event: dict) -> None:
        for events in list(self._subs.get(key, [])):
            try:
                events.put_nowait(event)
            except queue.Full:
                pass

    def _publish(self, key: str) -> None:
        if key not in self._sessions:
            return
        snapshot = self.snapshot(key)
        last = self._last.setdefault(key, {})
        known = last.setdefault("sigs", {})
        upserts = []
        sigs = {}
        for block in snapshot["blocks"]:
            signature = (block["kind"], block["text"], block["name"], block["result"],
                         block["is_error"], block["duration_ms"],
                         msgspec.json.encode(block["args"]))
            sigs[block["uid"]] = signature
            if known.get(block["uid"]) != signature:
                upserts.append(block)
        patch: dict = {"t": "patch", "key": key}
        if upserts:
            patch["upsert"] = upserts
        order = [block["uid"] for block in snapshot["blocks"]]
        if last.get("order") != order:
            patch["order"] = order
        for field in ("state", "stats", "busy", "queued"):
            if last.get(field) != snapshot[field]:
                patch[field] = snapshot[field]
        last["sigs"] = sigs
        last["order"] = order
        for field in ("state", "stats", "busy", "queued"):
            last[field] = snapshot[field]
        if len(patch) > 2:
            self._broadcast(key, patch)

    # -- commands --------------------------------------------------------

    def dispatch(self, key: str, action: str, body: dict) -> None:
        session = self._sessions[key]
        if action == "prompt":
            session.prompt(body.get("message", ""), images=body.get("images"),
                           behavior=body.get("behavior"))
        elif action == "steer":
            session.steer(body.get("message", ""))
        elif action == "follow_up":
            session.follow_up(body.get("message", ""))
        elif action == "abort":
            session.abort()
        elif action == "clear_queue":
            session.clear_queue()
        elif action == "rename":
            session.rename(body.get("name", ""))
        elif action == "model":
            session.set_model(body.get("provider", ""), body.get("id", ""))
        elif action == "thinking":
            session.set_thinking(body.get("level", "off"))
        elif action == "stats":
            session.stats_now()
        else:
            raise KeyError(f"unknown action {action}")

    def answer(self, key: str, request_id: str, *, value=None, confirmed=None,
               cancelled: bool = False) -> None:
        self._sessions[key].answer_ui(request_id, value=value, confirmed=confirmed,
                                      cancelled=cancelled)
