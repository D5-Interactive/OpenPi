import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from openpi.pi import providers


@pytest.fixture()
def model_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"object": "list", "data": [
                {"id": "model-a"}, {"id": "model-b"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/v1"
    httpd.shutdown()
    thread.join(timeout=5)


def test_detect_server_lists_models(model_server):
    assert providers.detect_server(model_server) == ["model-a", "model-b"]


def test_detect_server_returns_none_when_unreachable():
    assert providers.detect_server("http://127.0.0.1:1/v1", timeout=0.5) is None


def test_configure_and_remove_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(providers, "models_json_path", lambda: tmp_path / "models.json")
    providers.configure_provider("ollama", "http://localhost:11434/v1", ["qwen:7b"], "ollama")
    data = json.loads((tmp_path / "models.json").read_text())
    assert data["providers"]["ollama"]["baseUrl"] == "http://localhost:11434/v1"
    assert data["providers"]["ollama"]["apiKey"] == "ollama"
    assert data["providers"]["ollama"]["models"] == [{"id": "qwen:7b"}]

    assert providers.remove_provider("ollama") is True
    assert providers.remove_provider("ollama") is False
    assert providers.configured_providers() == {}


def test_configure_preserves_existing_providers(monkeypatch, tmp_path):
    path = tmp_path / "models.json"
    monkeypatch.setattr(providers, "models_json_path", lambda: path)
    providers.configure_provider("a", "http://a/v1", [])
    providers.configure_provider("b", "http://b/v1", [])
    assert set(providers.configured_providers()) == {"a", "b"}
