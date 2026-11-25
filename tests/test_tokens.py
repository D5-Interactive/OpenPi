import json
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest
from PySide6.QtWidgets import QApplication

from openpi import config
from openpi.server.http import start_server
from openpi.server.hub import SessionHub
from fake_pi import FAKE

TOKEN = "admin-token"


def background(fn):
    box: dict = {}

    def run() -> None:
        try:
            box["value"] = fn()
        except Exception as exc:  # noqa: BLE001
            box["error"] = exc

    threading.Thread(target=run, daemon=True).start()
    app = QApplication.instance()
    deadline = time.monotonic() + 10
    while "value" not in box and "error" not in box and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    if "error" in box:
        raise box["error"]
    return box.get("value")


@pytest.fixture()
def pairings(tmp_path):
    return config.Pairings(tmp_path)


def test_pairings_add_list_revoke_round_trip(pairings):
    added = pairings.add("phone")
    assert pairings.valid(added.token)
    assert [p.name for p in pairings.list()] == ["phone"]

    pairings.revoke(added.id)
    assert not pairings.valid(added.token)
    assert pairings.list() == []


def test_pairings_reload_from_disk_when_another_instance_writes(pairings, tmp_path):
    first = config.Pairings(tmp_path)
    second = config.Pairings(tmp_path)
    added = first.add("tablet")
    assert second.valid(added.token), "second instance must see the new token"


def test_pairings_revoke_missing_id_is_a_noop(pairings):
    assert pairings.revoke("nope") is False


@pytest.fixture()
def server(app, tmp_path):
    fake = tmp_path / "fake.py"
    fake.write_text(FAKE)
    hub = SessionHub(argv_factory=lambda cwd, path: [sys.executable, str(fake)],
                     cwd=str(tmp_path))
    pairings = config.Pairings(tmp_path)
    httpd, thread = start_server(hub, TOKEN, "127.0.0.1", 0, pairings=pairings)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base
    httpd.shutdown()
    thread.join(timeout=5)
    hub.shutdown()


def request(url, body=None, method=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data,
                                 method=method or ("POST" if body is not None else "GET"))
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Openpi-Token", token)
    return urllib.request.urlopen(req, timeout=5)


def test_admin_can_issue_and_device_can_use_a_token(server):
    base = server
    with request(f"{base}/api/pairings", {"name": "phone"}, token=TOKEN) as response:
        pairing = json.loads(response.read())
    assert pairing["token"] and pairing["id"]

    # device token opens the API (hub calls need the Qt loop pumped)
    def state_with_device_token():
        with request(f"{base}/api/state", token=pairing["token"]) as response:
            return response.status

    assert background(state_with_device_token) == 200

    # but cannot manage tokens
    with pytest.raises(urllib.error.HTTPError) as error:
        request(f"{base}/api/pairings", {"name": "x"}, token=pairing["token"])
    assert error.value.code == 403


def test_revoked_token_is_rejected(server):
    base = server
    with request(f"{base}/api/pairings", {"name": "phone"}, token=TOKEN) as response:
        pairing = json.loads(response.read())
    with request(f"{base}/api/pairings/{pairing['id']}", method="DELETE", token=TOKEN) as response:
        assert response.status == 200
    with pytest.raises(urllib.error.HTTPError) as error:
        request(f"{base}/api/state", token=pairing["token"])
    assert error.value.code == 401

def test_admin_endpoints_require_the_admin_token(server):
    base = server
    with pytest.raises(urllib.error.HTTPError) as error:
        request(f"{base}/api/pairings")
    assert error.value.code == 401  # no token at all
