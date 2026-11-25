"""HTTP + SSE surface for the web client.

Commands are marshalled onto the Qt thread through the hub. Event streams are per-session SSE:
EventSource cannot send headers, so the token may also arrive as `?token=`.
"""

from __future__ import annotations

import json
import queue
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import msgspec

from .hub import SessionHub

SESSION_ROUTE = re.compile(r"^/api/sessions/(?P<key>[A-Za-z0-9_-]+)/(?P<tail>[a-z_]+)$")
PAIRING_ROUTE = re.compile(r"^/api/pairings/(?P<id>[A-Za-z0-9]+)$")
WEB_DIR = Path(__file__).with_name("web")
MAX_BODY = 2 * 1024 * 1024


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "openpi"

    def log_message(self, fmt: str, *args) -> None:  # quiet: the CLI logs starts
        return

    # -- helpers ---------------------------------------------------------

    @property
    def hub(self) -> SessionHub:
        return self.server.hub

    @property
    def token(self) -> str:
        return self.server.token

    def _authorised(self, query: dict) -> bool:
        given = (self.headers.get("X-Openpi-Token")
                 or (query.get("token") or [""])[0])
        return bool(given) and (given == self.token or self.server.pairings.valid(given))

    def _is_admin(self, query: dict) -> bool:
        given = (self.headers.get("X-Openpi-Token")
                 or (query.get("token") or [""])[0])
        return bool(given) and given == self.token

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload) -> None:
        self._send(status, msgspec.json.encode(payload), "application/json")

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(length) or b"{}")

    # -- routes ----------------------------------------------------------

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path in ("/", "/index.html"):
            return self._static("index.html")
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if not parsed.path.startswith("/api/"):
            return self._error(404, "not found")
        if not self._authorised(query):
            return self._error(401, "token required")
        if parsed.path == "/api/state":
            try:
                return self._json(200, self.hub.call(self.hub.state_json))
            except TimeoutError:
                return self._error(503, "hub busy")
        if parsed.path == "/api/pairings":
            if not self._is_admin(query):
                return self._error(403, "admin token required")
            return self._json(200, {"pairings": [{"id": p.id, "name": p.name}
                                                 for p in self.server.pairings.list()]})
        match = SESSION_ROUTE.match(parsed.path)
        if match and match.group("tail") == "events":
            return self._events(match.group("key"))
        return self._error(404, "not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not self._authorised(query):
            return self._error(401, "token required")
        try:
            body = self._body()
        except (ValueError, json.JSONDecodeError):
            return self._error(400, "bad json body")
        if parsed.path == "/api/pairings":
            if not self._is_admin(query):
                return self._error(403, "admin token required")
            pairing = self.server.pairings.add(body.get("name") or "")
            return self._json(200, {"id": pairing.id, "name": pairing.name,
                                    "token": pairing.token})
        if parsed.path == "/api/open":
            try:
                key = self.hub.call(lambda: self.hub.open(body.get("session"), body.get("cwd")))
            except TimeoutError:
                return self._error(503, "hub busy")
            return self._json(200, {"key": key})
        match = SESSION_ROUTE.match(parsed.path)
        if not match:
            return self._error(404, "not found")
        key, tail = match.group("key"), match.group("tail")
        if not self.hub.has(key):
            return self._error(404, "no such session")
        if tail == "answer":
            try:
                self.hub.call(lambda: self.hub.answer(
                    key, body.get("id", ""), value=body.get("value"),
                    confirmed=body.get("confirmed"),
                    cancelled=bool(body.get("cancelled"))))
            except TimeoutError:
                return self._error(503, "hub busy")
            return self._json(200, {"ok": True})
        try:
            self.hub.call(lambda: self.hub.dispatch(key, tail, body))
        except TimeoutError:
            return self._error(503, "hub busy")
        except KeyError as exc:
            return self._error(400, str(exc))
        return self._json(200, {"ok": True})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not self._is_admin(query):
            return self._error(403, "admin token required")
        match = PAIRING_ROUTE.match(parsed.path)
        if not match:
            return self._error(404, "not found")
        if not self.server.pairings.revoke(match.group("id")):
            return self._error(404, "no such pairing")
        return self._json(200, {"ok": True})

    # -- pieces ----------------------------------------------------------

    def _static(self, name: str) -> None:
        try:
            body = (WEB_DIR / name).read_bytes()
        except OSError:
            return self._error(404, "missing web asset")
        self._send(200, body, "text/html; charset=utf-8")

    def _events(self, key: str) -> None:
        try:
            events: queue.Queue = self.hub.call(lambda: self.hub.subscribe(key))
        except KeyError:
            return self._error(404, "no such session")
        except TimeoutError:
            return self._error(503, "hub busy")

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            while True:
                try:
                    event = events.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                self.wfile.write(b"data: " + msgspec.json.encode(event) + b"\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.hub.post(lambda: self.hub.unsubscribe(key, events))


def start_server(hub: SessionHub, token: str, host: str, port: int, pairings=None,
                 tls_context=None):
    httpd = ThreadingHTTPServer((host, port), _Handler)
    httpd.hub = hub
    httpd.token = token
    httpd.pairings = pairings or _NullPairings()
    httpd.daemon_threads = True
    if tls_context is not None:
        httpd.socket = tls_context.wrap_socket(httpd.socket, server_side=True)
    import threading

    thread = threading.Thread(target=httpd.serve_forever, daemon=True, name="openpi-http")
    thread.start()
    return httpd, thread


class _NullPairings:
    def valid(self, token: str) -> bool:
        return False

    def list(self) -> list:
        return []

    def add(self, name: str):
        raise RuntimeError("pairings disabled")

    def revoke(self, pairing_id: str) -> bool:
        return False
