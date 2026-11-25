"""Client for a remote openpi server: the desktop uses this instead of spawning pi itself.

RemoteSession mirrors PiSession's public surface (signals, methods, attributes) so the UI layer
— `SessionPane`, `TranscriptView`, `dialogs` — is reused unchanged. The wire protocol is the
server's SSE/HTTP surface documented in `.agents/server-api.md`.

One reader thread streams SSE; it only parses and forwards each event over a Qt signal, so all
transcript/state mutation happens on the GUI thread.
"""

from __future__ import annotations

import http.client
import json
import ssl
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from PySide6.QtCore import QObject, Signal

from openpi.pi.transcript import Block, Transcript
from openpi.protocol import records
from openpi.protocol.records import (
    CommandInfo,
    ContextUsage,
    ExtensionUIRequest,
    Model,
    SessionStats,
    State,
)
from openpi.ui.tasks import run_async


class RemoteClient:
    def __init__(self, base: str, token: str, tls_ca: str | None = None) -> None:
        self.base = base.rstrip("/")
        self.token = token
        self.tls_ca = tls_ca
        self.context: ssl.SSLContext | None = None
        if base.startswith("https://"):
            self.context = ssl.create_default_context(cafile=tls_ca) if tls_ca \
                else ssl.create_default_context()

    def _request(self, path: str, body: dict | None = None, method: str | None = None):
        url = self.base + path
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data,
                                         method=method or ("POST" if body is not None else "GET"))
        request.add_header("X-Openpi-Token", self.token)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=self.context)) if self.context else None
        with (opener.open(request, timeout=15) if opener
              else urllib.request.urlopen(request, timeout=15)) as response:
            return json.loads(response.read() or b"{}")

    def get_state(self) -> dict:
        return self._request("/api/state")

    def open(self, cwd: str | None = None, session: str | None = None) -> str:
        return self._request("/api/open", {"cwd": cwd, "session": session})["key"]

    def action(self, key: str, action: str, body: dict | None = None) -> None:
        self._request(f"/api/sessions/{key}/{action}", body or {})

    def events_url(self, key: str) -> str:
        return f"{self.base}/api/sessions/{key}/events?token={self.token}"


def _block(data: dict) -> Block:
    return Block(uid=data["uid"], kind=data["kind"], text=data.get("text", ""),
                 name=data.get("name", ""), args=data.get("args") or {},
                 result=data.get("result", ""), is_error=bool(data.get("is_error")),
                 duration_ms=data.get("duration_ms"), meta=data.get("meta") or {})


class RemoteSession(QObject):
    changed = Signal()
    state_changed = Signal()
    ready = Signal()
    ui_request = Signal(object)        # ExtensionUIRequest
    notify = Signal(str, str)          # message, kind
    failed = Signal(str)
    _event = Signal(object)            # internal: forwards parsed SSE events to the GUI thread

    def __init__(self, client: RemoteClient, key: str, cwd: str | None = None,
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self.key = key
        self.cwd = cwd or ""
        self.session_path = None
        self.transcript = Transcript()
        self.state = State()
        self.stats: SessionStats | None = None
        self.models: list[Model] = []
        self.levels: list[str] = []
        self.commands: list[CommandInfo] = []
        self.ready_seen = False
        self._running = False
        self._conn: http.client.HTTPConnection | None = None
        self._conn_lock = threading.Lock()
        self._blocks: dict[str, Block] = {}
        self._order: list[str] = []
        self._event.connect(self._on_event)

    # -- lifecycle -------------------------------------------------------

    @property
    def alive(self) -> bool:
        return self._running

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._read, daemon=True,
                         name=f"openpi-remote-{self.key}").start()

    def close(self) -> None:
        self._running = False
        with self._conn_lock:
            connection = self._conn
        if connection is not None:
            try:
                connection.close()
            except Exception:  # noqa: BLE001 - closing is best-effort
                pass

    def _read(self) -> None:
        url = self.client.events_url(self.key)
        parsed = urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        path = parsed.path + (("?" + parsed.query) if parsed.query else "")
        while self._running:
            if parsed.scheme == "https":
                connection = http.client.HTTPSConnection(host, port, timeout=25,
                                                         context=self.client.context)
            else:
                connection = http.client.HTTPConnection(host, port, timeout=25)
            with self._conn_lock:
                self._conn = connection
            try:
                connection.request("GET", path, headers={
                    "X-Openpi-Token": self.client.token,
                    "Accept": "text/event-stream"})
                response = connection.getresponse()
                if response.status != 200:
                    body = response.read(200).decode("utf-8", "replace")
                    raise RuntimeError(f"events {response.status}: {body}")
                for line in response:
                    if not self._running:
                        return
                    if line.startswith(b"data:"):
                        self._event.emit(json.loads(line[5:]))
            except (http.client.HTTPException, OSError, json.JSONDecodeError,
                    RuntimeError) as exc:
                if self._running:
                    self.failed.emit(f"disconnected: {exc}")
                    time.sleep(2)
            finally:
                with self._conn_lock:
                    self._conn = None
                connection.close()

    # -- event handling (GUI thread) -------------------------------------

    def _on_event(self, event: dict) -> None:
        kind = event.get("t")
        if kind == "snapshot":
            self._load_blocks(event["blocks"])
            self._apply_meta(event)
            if not self.ready_seen:
                self.ready_seen = True
                self.ready.emit()
            self.changed.emit()
            self.state_changed.emit()
        elif kind == "patch":
            if event.get("upsert"):
                self._upsert(event["upsert"])
            if event.get("order") is not None:
                self._order = event["order"]
                self._sync()
            if event.get("state") is not None or event.get("stats") is not None:
                self._apply_meta(event)
                self.state_changed.emit()
            if event.get("busy") is not None or event.get("queued") is not None:
                self._apply_busy(event)
            self.changed.emit()
        elif kind == "ui":
            request = records.decode(event["request"], ExtensionUIRequest)
            self.ui_request.emit(request)
        elif kind == "notify":
            self.notify.emit(event.get("message", ""), event.get("kind", "info"))

    def _load_blocks(self, blocks: list[dict]) -> None:
        self._blocks = {data["uid"]: _block(data) for data in blocks}
        self._order = [data["uid"] for data in blocks]
        self._sync()

    def _upsert(self, blocks: list[dict]) -> None:
        for data in blocks:
            uid = data["uid"]
            self._blocks[uid] = _block(data)
            if uid not in self._order:
                self._order.append(uid)
        self._sync()

    def _sync(self) -> None:
        self.transcript.blocks = [self._blocks[uid] for uid in self._order if uid in self._blocks]

    def _apply_busy(self, event: dict) -> None:
        if event.get("busy") is not None:
            self.transcript.busy = event["busy"]
        if event.get("queued") is not None:
            self.transcript.queued = tuple(event["queued"])

    def _apply_meta(self, event: dict) -> None:
        if "state" in event and event["state"] is not None:
            state = event["state"]
            self.state = State(
                sessionName=state.get("name"), thinkingLevel=state.get("thinking", "off"),
                isStreaming=bool(state.get("is_streaming")),
                model=records.decode(state["model"], Model) if state.get("model") else None,
            )
            self.transcript.streaming = self.state.is_streaming
        if "stats" in event:
            stats = event["stats"] or {}
            self.stats = SessionStats(
                cost=stats.get("cost", 0.0),
                contextUsage=ContextUsage(
                    tokens=(stats.get("context") or {}).get("tokens"),
                    contextWindow=(stats.get("context") or {}).get("window"),
                    percent=(stats.get("context") or {}).get("percent"),
                ) if stats.get("context") else None,
            ) if stats else None
        if "models" in event and event["models"] is not None:
            self.models = records.decode({"models": event["models"]}, records.AvailableModels).models
        if "levels" in event and event["levels"] is not None:
            self.levels = event["levels"]
        if "commands" in event and event["commands"] is not None:
            self.commands = records.decode({"commands": event["commands"]}, records.Commands).commands
        self._apply_busy(event)

    # -- commands (fire-and-forget, off the GUI thread) ------------------

    def _post(self, action: str, body: dict | None = None) -> None:
        client, key = self.client, self.key
        run_async(lambda: client.action(key, action, body), lambda _result: None,
                  lambda error: self.failed.emit(str(error)))

    def prompt(self, message: str, images: list[dict] | None = None,
               behavior: str | None = None) -> None:
        self._post("prompt", {"message": message, "images": images, "behavior": behavior})

    def steer(self, message: str) -> None:
        self._post("steer", {"message": message})

    def follow_up(self, message: str) -> None:
        self._post("follow_up", {"message": message})

    def abort(self) -> None:
        self._post("abort")

    def clear_queue(self) -> None:
        self._post("clear_queue")

    def rename(self, name: str) -> None:
        self._post("rename", {"name": name})

    def set_model(self, provider: str, model_id: str) -> None:
        self._post("model", {"provider": provider, "id": model_id})

    def set_thinking(self, level: str) -> None:
        self._post("thinking", {"level": level})

    def stats_now(self) -> None:
        self._post("stats")

    def answer_ui(self, request_id: str, *, value=None, confirmed=None,
                  cancelled: bool = False) -> None:
        self._post("answer", {"id": request_id, "value": value, "confirmed": confirmed,
                              "cancelled": cancelled})
