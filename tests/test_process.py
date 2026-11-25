import sys
import time

import pytest
from PySide6.QtWidgets import QApplication

from openpi.pi.process import PiProcess

FAKE_PI = r'''
import json, os, sys
for raw in sys.stdin.buffer:
    cmd = json.loads(raw)
    if cmd.get("type") == "get_state":
        out = {"id": cmd.get("id"), "type": "response", "command": "get_state",
               "success": True, "data": {"sessionId": "s1", "isStreaming": False}}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()
    elif cmd.get("type") == "shout":
        sys.stderr.write("diagnostic only\n")
        sys.stderr.flush()
        out = {"id": cmd.get("id"), "type": "response", "command": "shout", "success": True}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()
sys.exit(0)
'''


@pytest.fixture()
def fake_pi(tmp_path):
    path = tmp_path / "fake_pi.py"
    path.write_text(FAKE_PI)
    return path


def pump_until(predicate, timeout=5.0):
    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_request_gets_correlated_response(app, fake_pi):
    proc = PiProcess([sys.executable, str(fake_pi)])
    records, stderr, exits = [], [], []
    proc.record.connect(records.append)
    proc.stderr_line.connect(stderr.append)
    proc.exited.connect(exits.append)
    proc.start()
    req_id = proc.send({"type": "get_state"})
    assert pump_until(lambda: any(r.get("type") == "response" for r in records))
    response = next(r for r in records if r.get("type") == "response")
    assert response["id"] == req_id
    assert response["data"]["sessionId"] == "s1"
    proc.close()
    assert pump_until(lambda: exits)


def test_ids_are_unique_when_not_supplied(app, fake_pi):
    proc = PiProcess([sys.executable, str(fake_pi)])
    records = []
    proc.record.connect(records.append)
    proc.start()
    a = proc.send({"type": "get_state"})
    b = proc.send({"type": "get_state"})
    assert a != b
    assert pump_until(lambda: len([r for r in records if r.get("type") == "response"]) == 2)
    proc.close()


def test_stderr_is_separate_from_protocol_records(app, fake_pi):
    proc = PiProcess([sys.executable, str(fake_pi)])
    records, stderr = [], []
    proc.record.connect(records.append)
    proc.stderr_line.connect(stderr.append)
    proc.start()
    proc.send({"type": "shout"})
    assert pump_until(lambda: stderr and any(r.get("type") == "response" for r in records))
    assert any("diagnostic only" in line for line in stderr)
    assert all(isinstance(r, dict) for r in records)
    proc.close()
