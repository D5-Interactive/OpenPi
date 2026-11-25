import json
import sys
import time

import pytest
from PySide6.QtWidgets import QApplication

from openpi.pi.session import PiSession

from fake_pi import FAKE


@pytest.fixture()
def fake_pi(tmp_path):
    path = tmp_path / "fake.py"
    path.write_text(FAKE)
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


def test_load_backfills_transcript_state_and_stats(app, fake_pi):
    session = PiSession([sys.executable, str(fake_pi)])
    loaded = []
    session.ready.connect(lambda: loaded.append(True))
    session.start()
    assert pump_until(lambda: loaded)
    assert session.state.session_name == "demo"
    assert session.state.thinking_level == "high"
    assert session.transcript.blocks[0].text == "old prompt"
    assert pump_until(lambda: session.stats is not None)
    assert session.stats.context_usage.percent == 32.0
    assert [m.id for m in session.models] == ["balanced"]
    session.close()


def test_prompt_streams_and_settles(app, fake_pi):
    session = PiSession([sys.executable, str(fake_pi)])
    session.start()
    assert pump_until(lambda: session.ready_seen)
    session.prompt("new prompt")
    assert pump_until(lambda: any(b.text == "hello hub" for b in session.transcript.blocks))
    assert pump_until(lambda: session.transcript.busy is False)
    kinds = [b.kind for b in session.transcript.blocks]
    assert kinds == ["user", "user", "text"]
    session.close()


def test_session_reports_pi_stderr_without_crashing(app, fake_pi):
    session = PiSession([sys.executable, str(fake_pi)])
    problems = []
    session.failed.connect(problems.append)
    session.start()
    assert pump_until(lambda: session.ready_seen)
    session.close()
