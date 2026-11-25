"""Contract test against the real pi binary. Skipped unless -m live is selected."""

import pytest
from PySide6.QtWidgets import QApplication

from openpi.pi.process import pi_binary
from openpi.pi.session import PiSession

pytestmark = pytest.mark.live


def pump_until(predicate, timeout=20.0):
    import time

    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_real_pi_answers_state_and_models(app):
    session = PiSession([pi_binary(), "--mode", "rpc", "--no-session", "--no-extensions",
                         "--no-mcp"])
    session.start()
    try:
        assert pump_until(lambda: session.ready_seen), "pi never answered get_state"
        assert session.state.session_id, "get_state returned no session id"
        assert pump_until(lambda: session.models), "no models returned"
        assert session.state.thinking_level in {"off", "minimal", "low", "medium", "high",
                                                "xhigh", "max"}
    finally:
        session.close()


def test_window_opens_a_session_in_a_trusted_folder(app, tmp_path):
    import json
    from openpi.ui.window import MainWindow

    project = tmp_path / "project"
    project.mkdir()
    sessions = tmp_path / "sessions"
    folder = sessions / "--demo--"
    folder.mkdir(parents=True)
    path = folder / "s.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in [
        {"type": "session", "version": 3, "id": "live-1", "timestamp": "t", "cwd": str(project)},
        {"type": "message", "id": "u1", "parentId": None, "timestamp": "t",
         "message": {"role": "user", "content": "hello from disk", "timestamp": 1}},
        {"type": "session_info", "id": "s1", "parentId": "u1", "timestamp": "t", "name": "disk-session"},
    ]) + "\n")

    window = MainWindow(session_root=sessions, state_dir=tmp_path / "state", project=str(project))
    window.settings.trusted.append(str(project))
    from openpi.pi.index import scan

    [meta] = scan(sessions)
    window._open({"key": str(meta.path), "title": meta.title, "cwd": meta.cwd,
                  "path": str(meta.path), "preview": meta.preview, "id": meta.id,
                  "busy": False})
    try:
        assert pump_until(lambda: window.session_count() == 1)
        pane = list(window._panes.values())[0]
        assert pump_until(lambda: pane.session.ready_seen)
        assert pane.session.state.session_name == "disk-session"
        assert pump_until(lambda: any("hello from disk" in b.text
                                      for b in pane.session.transcript.blocks))
    finally:
        window.close()
