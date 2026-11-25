import http.client
import socket
import sys
import threading
import time

import pytest
from PySide6.QtWidgets import QApplication

from openpi.relay import RelayClient, start_relay, stop_relay
from openpi.server.client import RemoteClient
from openpi.server.http import start_server
from openpi.server.hub import SessionHub
from openpi.server.tls import ensure_cert, server_context
from fake_pi import FAKE


def pump_until(predicate, timeout=10.0):
    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def background(fn):
    box: dict = {}

    def run() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:  # noqa: BLE001
            box["error"] = exc

    threading.Thread(target=run, daemon=True).start()
    pump_until(lambda: "value" in box or "error" in box)
    if "error" in box:
        raise box["error"]
    return box.get("value")


def raw_get(port):
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.settimeout(3)
        sock.sendall(b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n")
        chunks = []
        try:
            while chunk := sock.recv(65536):
                chunks.append(chunk)
        except (socket.timeout, ConnectionResetError, OSError):
            pass
    return b"".join(chunks)


@pytest.fixture()
def tls_server(app, tmp_path):
    fake = tmp_path / "fake.py"
    fake.write_text(FAKE)
    hub = SessionHub(argv_factory=lambda cwd, path: [sys.executable, str(fake)],
                     cwd=str(tmp_path))
    cert_path, _key = ensure_cert(tmp_path)
    context, _cert = server_context(tmp_path)
    httpd, thread = start_server(hub, "srv-token", "127.0.0.1", 0, tls_context=context)
    yield httpd.server_address[1], cert_path
    httpd.shutdown()
    thread.join(timeout=5)
    hub.shutdown()


def test_https_client_trusts_the_self_signed_cert(tls_server):
    port, cert_path = tls_server
    client = RemoteClient(f"https://127.0.0.1:{port}", "srv-token", tls_ca=str(cert_path))
    state = background(client.get_state)
    assert state["sessions"] == []


def test_plaintext_http_against_the_tls_server_is_not_http(tls_server):
    port, _cert_path = tls_server
    response = raw_get(port)
    assert b"HTTP/1." not in response and b"<!doctype html>" not in response


def test_tls_is_end_to_end_through_the_relay(app, tls_server):
    server_port, cert_path = tls_server
    public_port, instance_port, relay_thread, loop = start_relay("relay-secret", 0, 0)
    relay = RelayClient("127.0.0.1", instance_port, "relay-secret", "127.0.0.1", server_port)
    relay.start()
    try:
        assert pump_until(lambda: relay.connected)
        client = RemoteClient(f"https://127.0.0.1:{public_port}", "srv-token",
                              tls_ca=str(cert_path))
        assert background(client.get_state)["sessions"] == []

        # a plaintext request through the relay must not reach plain HTTP — only ciphertext
        assert b"HTTP/1." not in raw_get(public_port)
    finally:
        relay.stop()
        stop_relay(loop)
        relay_thread.join(timeout=5)
