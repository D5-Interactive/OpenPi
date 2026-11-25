import json
import time
from pathlib import Path

from openpi.pi.index import scan


def write_session(root: Path, mangled: str, session_id: str, cwd: str, lines: list[dict],
                  filename: str = "2026-11-25T10-00-00Z_x.jsonl") -> Path:
    folder = root / mangled
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / filename
    header = {"type": "session", "version": 3, "id": session_id,
              "timestamp": "2026-11-25T10:00:00.000Z", "cwd": cwd}
    path.write_text("\n".join(json.dumps(x) for x in [header, *lines]) + "\n")
    return path


def user(text: str, entry_id: str = "u1") -> dict:
    return {"type": "message", "id": entry_id, "parentId": None,
            "timestamp": "2026-11-25T10:00:01.000Z",
            "message": {"role": "user", "content": text, "timestamp": 1}}


def test_scan_uses_header_cwd_not_folder_name(tmp_path):
    write_session(tmp_path, "--wrong-name--", "sid-1", "/home/dsient/real-project",
                  [user("hello")])
    [meta] = scan(tmp_path)
    assert meta.cwd == "/home/dsient/real-project"
    assert meta.id == "sid-1"
    assert meta.preview == "hello"
    assert meta.message_count == 1


def test_scan_reads_session_name_and_latest_model(tmp_path):
    write_session(tmp_path, "--p--", "sid-2", "/p", [
        user("first prompt"),
        {"type": "model_change", "id": "m1", "parentId": "u1",
         "timestamp": "2026-11-25T10:01:00.000Z", "provider": "anthropic",
         "modelId": "claude-sonnet-4-5"},
        {"type": "session_info", "id": "s1", "parentId": "m1",
         "timestamp": "2026-11-25T10:02:00.000Z", "name": "fix/upload-retry"},
    ])
    [meta] = scan(tmp_path)
    assert meta.name == "fix/upload-retry"
    assert meta.model == "anthropic/claude-sonnet-4-5"


def test_preview_uses_first_text_block_of_a_block_list(tmp_path):
    write_session(tmp_path, "--p--", "sid-3", "/p", [
        {"type": "message", "id": "u1", "parentId": None, "timestamp": "t",
         "message": {"role": "user", "timestamp": 1,
                     "content": [{"type": "text", "text": "look at this"},
                                 {"type": "image", "data": "x", "mimeType": "image/png"}]}},
    ])
    [meta] = scan(tmp_path)
    assert meta.preview == "look at this"


def test_scan_sorts_newest_first_and_skips_junk_files(tmp_path):
    old = write_session(tmp_path, "--p--", "old", "/p", [user("old")], "a.jsonl")
    new = write_session(tmp_path, "--p--", "new", "/p", [user("new")], "b.jsonl")
    now = time.time()
    import os
    os.utime(old, (now - 100, now - 100))
    os.utime(new, (now, now))
    (tmp_path / "--p--" / "notes.txt").write_text("not a session")
    [first, second] = scan(tmp_path)
    assert (first.id, second.id) == ("new", "old")


def test_malformed_line_does_not_abort_the_scan(tmp_path):
    path = write_session(tmp_path, "--p--", "sid-4", "/p", [user("survives")])
    with path.open("a") as fh:
        fh.write("{broken json}\n")
    [meta] = scan(tmp_path)
    assert meta.preview == "survives"
