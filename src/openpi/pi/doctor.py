"""Ask a throwaway pi process what it can do. Used by `openpi doctor`."""

from __future__ import annotations

import selectors
import subprocess
import time

import msgspec

from openpi.pi.process import pi_binary


def probe(binary: str | None = None, timeout: float = 20.0) -> dict:
    binary = binary or pi_binary()
    result = {"binary": binary, "version": None, "ok": False, "error": None,
              "state": None, "models": 0, "thinking_levels": []}
    try:
        version = subprocess.run([binary, "--version"], capture_output=True, text=True,
                                 timeout=timeout)
        text = (version.stdout or version.stderr).strip()
        result["version"] = text.splitlines()[0] if text else None
    except (OSError, subprocess.SubprocessError) as exc:
        result["error"] = f"cannot run {binary}: {exc}"
        return result

    process = subprocess.Popen(
        [binary, "--mode", "rpc", "--no-session", "--no-extensions", "--no-mcp"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    assert process.stdin and process.stdout
    for cid, command in (("1", "get_state"), ("2", "get_available_models"),
                         ("3", "get_available_thinking_levels")):
        process.stdin.write(msgspec.json.encode({"id": cid, "type": command}) + b"\n")
    process.stdin.flush()

    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    seen = 0
    while seen < 3 and time.monotonic() < deadline:
        if not selector.select(timeout=0.5):
            continue
        line = process.stdout.readline()
        if not line:
            break
        try:
            record = msgspec.json.decode(line)
        except msgspec.DecodeError:
            continue
        if record.get("type") != "response" or not record.get("success"):
            if record.get("error"):
                result["error"] = record["error"]
            continue
        seen += 1
        data = record.get("data") or {}
        if record.get("command") == "get_state":
            result["state"] = {
                "session_id": data.get("sessionId"),
                "model": (data.get("model") or {}).get("id"),
                "thinking": data.get("thinkingLevel"),
            }
        elif record.get("command") == "get_available_models":
            result["models"] = len(data.get("models") or [])
        elif record.get("command") == "get_available_thinking_levels":
            result["thinking_levels"] = data.get("levels") or []

    process.stdin.close()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
    result["ok"] = result["state"] is not None
    return result
