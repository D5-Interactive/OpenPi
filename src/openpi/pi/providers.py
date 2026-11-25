"""Local model server discovery and pi `models.json` configuration.

pi configures OpenAI-compatible endpoints (Ollama, LM Studio, vLLM, llama.cpp, Colibri, …) in
`~/.pi/agent/models.json` under `providers`. openpi detects what is actually running and writes
that file — the one place pi documents for user-managed compatible endpoints (not its catalogs
or settings). Detection is read-only until the user saves.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

KNOWN_SERVERS = {
    "lmstudio": ("LM Studio", "http://127.0.0.1:1234/v1"),
    "ollama": ("Ollama", "http://127.0.0.1:11434/v1"),
    "vllm": ("vLLM", "http://127.0.0.1:8000/v1"),
    "llamacpp": ("llama.cpp", "http://127.0.0.1:8080/v1"),
    "colibri": ("Colibri", "http://127.0.0.1:2345/v1"),
}

SCHEMA = "https://pi.dev/schemas/models.schema.json"


def models_json_path() -> Path:
    agent_dir = os.environ.get("PI_CODING_AGENT_DIR") or str(Path.home() / ".pi" / "agent")
    return Path(agent_dir) / "models.json"


def detect_server(base_url: str, timeout: float = 2.0) -> list[str] | None:
    """Return the model ids an OpenAI-compatible `/models` endpoint exposes, or None."""
    url = f"{base_url.rstrip('/')}/models"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return None
    models = data.get("data") or []
    if isinstance(models, list):
        return [m.get("id") for m in models if isinstance(m, dict) and m.get("id")]
    return None


def detect_all() -> dict[str, dict]:
    """Probe every known server. Value: {name, base_url, ok, models}. Off the GUI thread."""
    results = {}
    for key, (name, base_url) in KNOWN_SERVERS.items():
        models = detect_server(base_url)
        results[key] = {"name": name, "base_url": base_url, "ok": models is not None,
                        "models": models or []}
    return results


def load_models_json() -> dict:
    path = models_json_path()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    data.setdefault("$schema", SCHEMA)
    data.setdefault("providers", {})
    return data


def _save(data: dict) -> None:
    path = models_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)


def configured_providers() -> dict:
    return load_models_json().get("providers", {})


def configure_provider(key: str, base_url: str, models: list[str], api_key: str = "",
                       api: str = "openai-completions") -> None:
    data = load_models_json()
    entry = {"baseUrl": base_url.rstrip("/"), "api": api}
    if api_key:
        entry["apiKey"] = api_key
    if models:
        entry["models"] = [{"id": model} for model in models]
    data["providers"][key] = entry
    _save(data)


def remove_provider(key: str) -> bool:
    data = load_models_json()
    if key not in data.get("providers", {}):
        return False
    del data["providers"][key]
    _save(data)
    return True
