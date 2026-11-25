import sys
import time

import pytest

from openpi.server.hub import SessionHub
from fake_pi import FAKE


@pytest.fixture()
def fake_pi(tmp_path):
    path = tmp_path / "fake.py"
    path.write_text(FAKE)
    return path


@pytest.fixture()
def hub(app, fake_pi, tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    hub = SessionHub(argv_factory=lambda cwd, path: [sys.executable, str(fake_pi)],
                     cwd=str(project))
    yield hub
    hub.shutdown()


def pump_until(predicate, timeout=5.0):
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def next_event(q, predicate, timeout=5.0):
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        try:
            event = q.get_nowait()
        except Exception:
            time.sleep(0.01)
            continue
        if predicate(event):
            return event
    raise AssertionError("no matching event")


def test_snapshot_has_state_blocks_and_menus(hub):
    key = hub.open()
    assert pump_until(lambda: hub.session(key).ready_seen)
    snapshot = hub.subscribe(key).get_nowait()
    assert snapshot["t"] == "snapshot"
    assert snapshot["state"]["name"] == "demo"
    assert snapshot["blocks"][0]["text"] == "old prompt"
    assert snapshot["levels"] == ["low", "high", "max"]
    assert [c["name"] for c in snapshot["commands"]] == ["skill:plan"]
    hub.close(key)


def test_prompt_produces_block_patches_and_busy_state(hub):
    key = hub.open()
    queue = hub.subscribe(key)
    assert pump_until(lambda: hub.session(key).ready_seen)
    hub.dispatch(key, "prompt", {"message": "go"})
    event = next_event(queue, lambda e: e["t"] == "patch"
                       and any(b["text"] == "hello hub" for b in e.get("upsert", [])))
    assert event["upsert"][0]["kind"] == "text"
    assert next_event(queue, lambda e: e["t"] == "patch" and e.get("busy") is False)
    hub.close(key)


def test_rename_updates_state_and_title(hub):
    key = hub.open()
    queue = hub.subscribe(key)
    assert pump_until(lambda: hub.session(key).ready_seen)
    hub.dispatch(key, "rename", {"name": "renamed"})
    event = next_event(queue, lambda e: e["t"] == "patch" and e.get("state", {}).get("name") == "renamed")
    assert event["state"]["name"] == "renamed"
    assert hub.sessions()[0]["title"] == "renamed"
    hub.close(key)


def test_two_subscribers_receive_the_same_patch(hub):
    key = hub.open()
    first, second = hub.subscribe(key), hub.subscribe(key)
    assert pump_until(lambda: hub.session(key).ready_seen)
    hub.dispatch(key, "prompt", {"message": "go"})
    for queue in (first, second):
        event = next_event(queue, lambda e: e["t"] == "patch"
                           and any(b["text"] == "hello hub" for b in e.get("upsert", [])))
        assert event["t"] == "patch"
    hub.close(key)


def test_prompt_images_reach_pi(hub):
    key = hub.open()
    stderr = []
    hub.session(key).failed.connect(stderr.append)
    assert pump_until(lambda: hub.session(key).ready_seen)
    hub.dispatch(key, "prompt", {"message": "look",
                                 "images": [{"data": "AA==", "mimeType": "image/png"}]})
    assert pump_until(lambda: any("prompt-images 1" in line for line in stderr))
    hub.close(key)


def test_extension_dialog_is_broadcast_and_answer_reaches_pi(hub):
    key = hub.open()
    queue = hub.subscribe(key)
    assert pump_until(lambda: hub.session(key).ready_seen)
    hub.dispatch(key, "prompt", {"message": "go"})
    request = next_event(queue, lambda e: e["t"] == "ui")["request"]
    assert request["options"] == ["Allow", "Block"]
    answers = []
    hub.session(key).failed.connect(answers.append)
    hub.answer(key, request["id"], value="Allow")
    assert pump_until(lambda: any("ui-answer" in line and "Allow" in line for line in answers))
    hub.close(key)
