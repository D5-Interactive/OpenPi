import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from openpi.server.client import RemoteClient

from . import theme
from .window import MainWindow


def _token_from(base: str, token: str | None) -> str | None:
    if token:
        return token
    if "?token=" in base:
        return base.partition("?token=")[2].split("&")[0]
    return None


def launch(project: str | None = None, session_root: Path | None = None,
           state_dir: Path | None = None, connect: str | None = None,
           token: str | None = None, tls_ca: str | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("openpi")
    theme.apply(app)
    remote = None
    if connect:
        token = _token_from(connect, token)
        if not token:
            print("openpi: --connect needs a token (pass --token, or put ?token= in the URL)",
                  file=sys.stderr)
            return 2
        remote = RemoteClient(connect, token, tls_ca=tls_ca)
    window = MainWindow(session_root=session_root, state_dir=state_dir, project=project,
                        remote=remote)
    window.show()
    return app.exec()
