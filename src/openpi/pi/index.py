"""Read-only index of pi's session files.

openpi never writes these files; pi is the only writer. The scan is meant to run off the GUI
thread and is cheap enough to repeat on a file-change signal.

shortcut: every file is decoded in full on each scan. If a large session directory makes this
noticeable, cache by (path, mtime, size) and skip unchanged files.
"""

from __future__ import annotations

import msgspec
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class SessionMeta:
    path: Path
    id: str
    cwd: str
    name: str | None = None
    preview: str = ""
    model: str | None = None
    message_count: int = 0
    mtime: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def title(self) -> str:
        return self.name or self.preview or self.id


def default_session_dir() -> Path:
    return Path.home() / ".pi" / "agent" / "sessions"


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "")
    return ""


def read_meta(path: Path) -> SessionMeta | None:
    session_id = cwd = None
    name = None
    preview = ""
    model = None
    message_count = 0
    with path.open("rb") as fh:
        for raw in fh:
            line = raw.rstrip(b"\r\n")
            if not line.strip():
                continue
            try:
                entry = msgspec.json.decode(line)
            except msgspec.DecodeError:
                continue
            kind = entry.get("type")
            if kind == "session":
                session_id = entry.get("id")
                cwd = entry.get("cwd")
            elif kind == "session_info":
                name = entry.get("name") or None
            elif kind == "model_change":
                model = f"{entry.get('provider')}/{entry.get('modelId')}"
            elif kind == "message":
                message = entry.get("message") or {}
                role = message.get("role")
                if role == "user":
                    message_count += 1
                    if not preview:
                        text = _text_of(message.get("content")).strip()
                        text = text.lstrip("●○∙ ").strip()
                        preview = text.splitlines()[0] if text else ""
                elif role == "assistant" and not model:
                    provider, model_id = message.get("provider"), message.get("model")
                    if provider and model_id:
                        model = f"{provider}/{model_id}"
    if not session_id or not cwd:
        return None
    return SessionMeta(
        path=path, id=session_id, cwd=cwd, name=name, preview=preview, model=model,
        message_count=message_count, mtime=path.stat().st_mtime,
    )


def scan(root: Path | None = None) -> list[SessionMeta]:
    root = root or default_session_dir()
    if not root.is_dir():
        return []
    metas = []
    for path in root.rglob("*.jsonl"):
        try:
            meta = read_meta(path)
        except OSError:
            continue
        if meta is not None:
            metas.append(meta)
    metas.sort(key=lambda m: m.mtime, reverse=True)
    return metas


def for_cwd(root: Path | None, cwd: str) -> list[SessionMeta]:
    return [m for m in scan(root) if m.cwd == cwd]
