import sys
import threading
import time

import pytest
from PySide6.QtWidgets import QApplication

from openpi.server.client import RemoteClient, RemoteSession
from openpi.server.http import start_server
from openpi.server.hub import SessionHub
from openpi.ui.pane import SessionPane
from fake_pi import FAKE

TOKEN = "client-token"


@pytest.fixture()
def server(app, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    fake = tmp_path / "fake.py"
    fake.write_text(FAKE)
    hub = SessionHub(argv_factory=lambda cwd, path: [sys.executable, str(fake)],
                     cwd=str(project))
    httpd, thread = start_server(hub, TOKEN, "127.0.0.1", 0)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, hub
    httpd.shutdown()
    thread.join(timeout=5)
    hub.shutdown()


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


def pump_until(predicate, timeout=10.0):
    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_remote_session_streams_a_prompt(app, server):
    base, _hub = server
    client = RemoteClient(base, TOKEN)
    key = background(lambda: client.open())
    session = RemoteSession(client, key)
    session.start()
    try:
        assert pump_until(lambda: session.ready_seen)
        assert session.transcript.blocks[0].text == "old prompt"
        assert session.state.session_name == "demo"
        session.prompt("go")
        assert pump_until(lambda: any(b.text == "hello hub" for b in session.transcript.blocks))
        assert pump_until(lambda: session.transcript.busy is False)
        assert pump_until(lambda: session.stats is not None)
        assert session.stats.cost == 0.25
    finally:
        session.close()


def test_remote_session_rename_round_trips(app, server):
    base, _hub = server
    client = RemoteClient(base, TOKEN)
    key = background(lambda: client.open())
    session = RemoteSession(client, key)
    session.start()
    try:
        assert pump_until(lambda: session.ready_seen)
        session.rename("renamed")
        assert pump_until(lambda: session.state.session_name == "renamed")
    finally:
        session.close()


def test_session_pane_binds_a_remote_session(app, server):
    base, _hub = server
    client = RemoteClient(base, TOKEN)
    key = background(lambda: client.open())
    session = RemoteSession(client, key)
    session.start()
    try:
        assert pump_until(lambda: session.ready_seen)
        pane = SessionPane(session)
        assert pane.transcript.block_count() == 1
        assert session.state.session_name == "demo"
    finally:
        session.close()
