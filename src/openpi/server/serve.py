"""`openpi serve` — the background server the desktop app and the browser both talk to.

Runs on a Qt core event loop (no display). Sessions are pi processes owned by the hub; the HTTP
server lives in threads and marshals commands onto the Qt thread.
"""

from __future__ import annotations

import os
import secrets
import socket
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from openpi import config
from openpi.pi.index import default_session_dir
from openpi.pi.process import pi_binary
from openpi.relay import RelayClient
from openpi.server.http import start_server
from openpi.server.hub import SessionHub

DEFAULT_PORT = 7717


def ensure_token(directory: Path | None = None) -> str:
    directory = directory or config.home_dir()
    path = directory / "server-token"
    try:
        token = path.read_text().strip()
    except OSError:
        token = ""
    if token:
        return token
    directory.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(24)
    path.write_text(token + "\n")
    os.chmod(path, 0o600)
    return token


def session_argv(trust: bool):
    def build(cwd: str, path: str | None) -> list[str]:
        argv = [pi_binary(), "--mode", "rpc"]
        if path:
            argv += ["--session", path]
        argv.append("--approve" if trust else "--no-approve")
        return argv

    return build


def lan_address() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))
            return sock.getsockname()[0]
    except OSError:
        return None


def run(host: str = "127.0.0.1", port: int = DEFAULT_PORT, cwd: str | None = None,
        session_root: Path | None = None, token: str | None = None, trust: bool = False,
        relay: str | None = None, relay_token: str | None = None, tls: bool = False) -> int:
    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    token = token or ensure_token()
    from .pi.install import find_pi

    if find_pi() is None:
        print("warning: pi not found — run `openpi setup` to install it", file=sys.stderr)
    hub = SessionHub(argv_factory=session_argv(trust), cwd=cwd or str(Path.cwd()),
                     session_root=session_root or default_session_dir())
    pairings = config.Pairings(config.home_dir())

    tls_context = None
    scheme = "http"
    if tls:
        from .tls import fingerprint, server_context

        tls_context, cert_path = server_context(config.home_dir())
        scheme = "https"
    httpd, _thread = start_server(hub, token, host, port, pairings=pairings,
                                  tls_context=tls_context)
    bound = httpd.server_address[1]

    print(f"openpi server  {scheme}://{host}:{bound}")
    print(f"open           {scheme}://127.0.0.1:{bound}/?token={token}")
    if tls:
        print(f"tls cert       {cert_path}")
        print(f"tls sha256     {fingerprint(cert_path.read_bytes())}")
    if host in ("0.0.0.0", "::"):
        address = lan_address()
        if address:
            print(f"lan            {scheme}://{address}:{bound}/?token={token}")

    relay_client = None
    if relay:
        relay_host, _, relay_port = relay.rpartition(":")
        relay_client = RelayClient(relay_host or "127.0.0.1", int(relay_port or "7719"),
                                   relay_token or token, "127.0.0.1", bound)
        relay_client.start()
        print(f"relay          {relay_host or '127.0.0.1'}:{relay_port or '7719'}")
    print("ctrl-c to stop", flush=True)

    try:
        return app.exec()
    except KeyboardInterrupt:
        return 0
    finally:
        if relay_client is not None:
            relay_client.stop()
        httpd.shutdown()
        hub.shutdown()
