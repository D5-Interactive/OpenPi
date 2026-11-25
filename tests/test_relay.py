import json
import socket
import sys
import time

import pytest
from PySide6.QtWidgets import QApplication

from openpi.relay import RelayClient, start_relay, stop_relay
from openpi.server.http import start_server
from openpi.server.hub import SessionHub
from fake_pi import FAKE

TOKEN = "relay-token"


def pump_until(predicate, timeout=10.0):
    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


@pytest.fixture()
def relay():
    public_port, instance_port, thread, loop = start_relay(TOKEN, 0, 0)
    yield public_port, instance_port
    stop_relay(loop)
    thread.join(timeout=5)


@pytest.fixture()
def http_server(app, tmp_path):
    fake = tmp_path / "fake.py"
    fake.write_text(FAKE)
    hub = SessionHub(argv_factory=lambda cwd, path: [sys.executable, str(fake)],
                     cwd=str(tmp_path))
    httpd, thread = start_server(hub, "http-token", "127.0.0.1", 0)
    yield httpd.server_address[1]
    httpd.shutdown()
    thread.join(timeout=5)
    hub.shutdown()


def http_get(port, path):
    with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
        sock.sendall(f"GET {path} HTTP/1.0\r\nHost: localhost\r\n\r\n".encode())
        chunks = []
        while chunk := sock.recv(65536):
            chunks.append(chunk)
    return b"".join(chunks)


def test_relay_pipes_a_browser_connection_to_the_local_server(relay, http_server):
    public_port, instance_port = relay
    client = RelayClient("127.0.0.1", instance_port, TOKEN, "127.0.0.1", http_server)
    client.start()
    try:
        assert pump_until(lambda: client.connected)
        response = http_get(public_port, "/")
        assert b"200 OK" in response
        assert b"openpi" in response
    finally:
        client.stop()


def test_relay_rejects_a_wrong_instance_token(relay):
    _public_port, instance_port = relay
    client = RelayClient("127.0.0.1", instance_port, "wrong", "127.0.0.1", 1)
    client.start()
    try:
        assert pump_until(lambda: client.failed)
        assert not client.connected
    finally:
        client.stop()


def test_relay_answers_503_when_no_instance_is_connected(relay):
    public_port, _instance_port = relay
    response = http_get(public_port, "/")
    assert b"503" in response
