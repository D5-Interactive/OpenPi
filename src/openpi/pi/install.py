"""Ensure the pi coding agent is installed and up to date.

Fresh install uses pi's official installer (`https://pi.dev/install.sh`); updates use
`pi update --self` (pi's documented self-update), falling back to a global npm install when the
self-update fails (e.g. pi was installed from npm rather than the installer).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

PI_PACKAGE = "@earendil-works/pi-coding-agent"
REGISTRY = "https://registry.npmjs.org/@earendil-works/pi-coding-agent/latest"
INSTALL_SCRIPT = "https://pi.dev/install.sh"


def find_pi() -> str | None:
    binary = shutil.which("pi")
    if binary:
        return binary
    candidate = Path.home() / ".local" / "bin" / "pi"
    return str(candidate) if candidate.exists() else None


def installed_version(binary: str | None = None) -> str | None:
    binary = binary or find_pi()
    if not binary:
        return None
    try:
        result = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (result.stdout or result.stderr).strip()
    return text.splitlines()[0] if text else None


def latest_version(timeout: float = 10.0) -> str | None:
    try:
        with urllib.request.urlopen(REGISTRY, timeout=timeout) as response:
            return json.loads(response.read()).get("version")
    except (OSError, ValueError):
        return None


def pi_status() -> dict:
    binary = find_pi()
    return {"binary": binary, "version": installed_version(binary),
            "latest": latest_version(), "ok": binary is not None}


def _run(command: list[str], *, timeout: float = 300) -> subprocess.CompletedProcess:
    env = dict(os.environ, CI="true", DEBIAN_FRONTEND="noninteractive")
    return subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=env)


def ensure_pi(update: bool = True, binary: str | None = None) -> str:
    """Return the pi binary path, installing or updating it first when asked."""
    binary = binary or find_pi()
    if binary is None:
        _run(["sh", "-c", f"curl -fsSL {INSTALL_SCRIPT} | sh"])
        binary = find_pi()
        if binary is None:
            raise RuntimeError("pi did not appear on PATH after running the installer")
        return binary
    if not update:
        return binary
    latest = latest_version()
    current = installed_version(binary)
    if latest and current != latest:
        result = _run([binary, "update", "--self"])
        if result.returncode != 0:
            _run(["npm", "install", "-g", "--ignore-scripts", PI_PACKAGE])
    return binary
