import json
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest
from PySide6.QtWidgets import QApplication

from openpi.server.http import start_server
from openpi.server.hub import SessionHub
from fake_pi import FAKE

TOKEN = "test-token"


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
    yield hub, base
    httpd.shutdown()
    thread.join(timeout=5)
    hub.shutdown()


def pump_until(predicate, timeout=10.0):
    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def get(url, token=None):
    request = urllib.request.Request(url)
    if token:
        request.add_header("X-Openpi-Token", token)
    return urllib.request.urlopen(request, timeout=5)


def post(url, body, token=None):
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
    if token:
        request.add_header("X-Openpi-Token", token)
    return urllib.request.urlopen(request, timeout=5)


def background(fn):
    """Run an HTTP call off the test thread and pump Qt until it returns."""
    box: dict = {}

    def run() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:  # noqa: BLE001 - asserted by the caller
            box["error"] = exc

    threading.Thread(target=run, daemon=True).start()
    pump_until(lambda: "value" in box or "error" in box)
    if "error" in box:
        raise box["error"]
    return box.get("value")


def test_static_page_is_served_without_a_token(server):
    _hub, base = server
    with get(base + "/") as response:
        assert response.status == 200
        assert b"openpi" in response.read()


def test_api_requires_the_token(server):
    _hub, base = server
    with pytest.raises(urllib.error.HTTPError) as error:
        get(base + "/api/state")
    assert error.value.code == 401


def test_state_and_open_a_session(server):
    hub, base = server

    def read_state():
        with get(base + "/api/state?token=" + TOKEN) as response:
            return json.loads(response.read())

    assert background(read_state)["sessions"] == []

    def open_session():
        with post(base + "/api/open?token=" + TOKEN, {"cwd": hub.cwd}) as response:
            return json.loads(response.read())["key"]

    key = background(open_session)
    assert key
    assert pump_until(lambda: hub.session(key).ready_seen)


def test_sse_stream_sends_snapshot_then_prompt_text(server):
    hub, base = server

    def open_session():
        with post(base + "/api/open?token=" + TOKEN, {"cwd": hub.cwd}) as response:
            return json.loads(response.read())["key"]

    key = background(open_session)
    assert pump_until(lambda: hub.session(key).ready_seen)

    events = []
    url = f"{base}/api/sessions/{key}/events?token={TOKEN}"
    threading.Thread(target=lambda: read_events(url, events), daemon=True).start()
    assert pump_until(lambda: len(events) >= 1)

    def prompt():
        with post(f"{base}/api/sessions/{key}/prompt?token={TOKEN}", {"message": "go"}) as response:
            return response.status

    assert background(prompt) == 200
    assert pump_until(lambda: any(b.get("text") == "hello hub"
                                  for e in events for b in e.get("upsert", [])))


def read_events(url, out):
    with urllib.request.urlopen(url, timeout=15) as response:
        for raw in response:
            if raw.startswith(b"data:"):
                out.append(json.loads(raw[5:]))


def test_bad_token_query_is_rejected(server):
    _hub, base = server
    with pytest.raises(urllib.error.HTTPError) as error:
        get(base + "/api/state?token=wrong")
    assert error.value.code == 401
