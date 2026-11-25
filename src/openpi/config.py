"""openpi's own state. Not pi's: settings here never belong to the agent.

Home layout (created on first run, `OPENPI_HOME` overrides the default `~/.openpi`):

    ~/.openpi/
        settings.json    Settings struct
        pairings.json    per-device tokens
        server-token     admin token for `openpi serve`
        server.crt/.key  self-signed TLS material
        extensions/      reserved for openpi extensions
        skills/          reserved for openpi skills
"""

from __future__ import annotations

import os
import secrets
import shutil
import threading
from pathlib import Path

import msgspec

LEGACY_FILES = ("settings.json", "pairings.json", "server-token", "server.crt", "server.key")
RESERVED_DIRS = ("extensions", "skills")


class Settings(msgspec.Struct):
    projects: list[str] = msgspec.field(default_factory=list)
    last_project: str = ""
    trusted: list[str] = msgspec.field(default_factory=list)
    untrusted: list[str] = msgspec.field(default_factory=list)
    last_model: str = ""
    live_cap: int = 8


class Pairing(msgspec.Struct):
    id: str
    name: str
    token: str


def home_dir() -> Path:
    return Path(os.environ.get("OPENPI_HOME") or Path.home() / ".openpi")


def legacy_dir() -> Path:
    base = os.environ.get("OPENPI_STATE_DIR") or os.environ.get("XDG_STATE_HOME") \
        or str(Path.home() / ".local" / "state")
    return Path(base) / "openpi"


def state_dir() -> Path:  # kept as an alias; new code should use home_dir()
    return home_dir()


def ensure_home(directory: Path | None = None) -> Path:
    """Create the home layout and migrate any pre-`~/.openpi` state into it."""
    explicit = directory is not None
    directory = directory or home_dir()
    directory.mkdir(parents=True, exist_ok=True)
    for sub in RESERVED_DIRS:
        (directory / sub).mkdir(exist_ok=True)
    if not explicit and "OPENPI_HOME" not in os.environ:
        legacy = legacy_dir()
        if legacy != directory and legacy.is_dir():
            for name in LEGACY_FILES:
                src, dst = legacy / name, directory / name
                if src.exists() and not dst.exists():
                    try:
                        shutil.copy2(src, dst)
                    except OSError:
                        pass
    return directory


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def load(directory: Path | None = None) -> Settings:
    directory = directory or home_dir()
    path = directory / "settings.json"
    try:
        return msgspec.json.decode(path.read_bytes(), type=Settings)
    except (OSError, msgspec.DecodeError):
        return Settings()


def save(settings: Settings, directory: Path | None = None) -> None:
    _atomic_write((directory or home_dir()) / "settings.json", msgspec.json.encode(settings))


class Pairings:
    """Per-device tokens, reloaded from disk on change so `openpi token` works while serving."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or home_dir()
        self._lock = threading.Lock()
        self._mtime: float = -1.0
        self._by_token: dict[str, Pairing] = {}

    def _path(self) -> Path:
        return self.directory / "pairings.json"

    def _load(self) -> dict[str, Pairing]:
        path = self._path()
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return {}
        if mtime == self._mtime:
            return self._by_token
        try:
            pairings = msgspec.json.decode(path.read_bytes(), type=list[Pairing])
        except (OSError, msgspec.DecodeError):
            return {}
        self._mtime = mtime
        self._by_token = {p.token: p for p in pairings}
        return self._by_token

    def _save(self, pairings: list[Pairing]) -> None:
        _atomic_write(self._path(), msgspec.json.encode(pairings))
        self._mtime = -1.0  # force reload on next read

    def valid(self, token: str) -> bool:
        return token in self._load()

    def add(self, name: str) -> Pairing:
        with self._lock:
            pairings = list(self._load().values())
            pairing = Pairing(id=secrets.token_hex(4), name=name,
                              token=secrets.token_urlsafe(24))
            pairings.append(pairing)
            self._save(pairings)
            return pairing

    def list(self) -> list[Pairing]:
        return list(self._load().values())

    def revoke(self, pairing_id: str) -> bool:
        with self._lock:
            pairings = [p for p in self._load().values() if p.id != pairing_id]
            if len(pairings) == len(self._load()):
                return False
            self._save(pairings)
            return True

