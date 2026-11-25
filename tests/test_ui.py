from openpi.protocol.records import State
from openpi.pi.transcript import Transcript
from openpi.ui.composer import Composer
from openpi.ui.markdown import render_markdown
from openpi.ui.transcript import TranscriptView
from openpi.ui.window import MainWindow


def test_markdown_renders_formatting_and_code():
    html = render_markdown("**bold** and `x = 1`\n\n```python\nprint(1)\n```")
    assert "<strong>bold</strong>" in html
    assert "<code" in html
    assert "print(1)" in html


def test_markdown_escapes_raw_html():
    html = render_markdown("<script>alert(1)</script>")
    assert "<script>" not in html


def test_transcript_view_renders_blocks_and_updates_text(app):
    t = Transcript()
    t.apply({"type": "message_start", "message": {"role": "user", "content": "hello", "timestamp": 1}})
    t.apply({"type": "message_start",
             "message": {"role": "assistant", "content": [], "stopReason": "pending", "timestamp": 2}})
    t.apply({"type": "message_update",
             "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "answer"}})
    view = TranscriptView()
    view.render(t)
    assert view.block_count() == 2
    labels = view.visible_text()
    assert "hello" in labels and "answer" in labels

    t.apply({"type": "message_update",
             "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": " more"}})
    view.render(t)
    assert view.block_count() == 2
    assert "answer more" in view.visible_text()


def test_composer_emits_prompt_on_ctrl_enter(app):
    sent = []
    composer = Composer()
    composer.submitted.connect(lambda message, images: sent.append((message, images)))
    composer.set_text("do the thing")
    composer.submit()
    assert sent == [("do the thing", [])]
    assert composer.text() == ""


def test_slash_autocomplete_pops_up_matches(app):
    from types import SimpleNamespace

    composer = Composer()
    composer.set_commands([SimpleNamespace(name="skill:plan", description=""),
                           SimpleNamespace(name="skill:triage", description="")])
    composer.set_text("/ski")
    composer._maybe_autocomplete()
    assert composer.popup.count() == 2
    composer.popup.hide()


def test_main_window_constructs_without_sessions(app, tmp_path):
    window = MainWindow(session_root=tmp_path, state_dir=tmp_path)
    assert window.session_count() == 0
    window.close()
    window.deleteLater()
    app.processEvents()
