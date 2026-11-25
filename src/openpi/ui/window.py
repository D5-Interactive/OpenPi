"""Main window: hideable project→session sidebar, one pane per open session.

The session backend is either local (spawn `pi --mode rpc`) or remote (attach to an openpi
server). `SessionPane` does not care which. Theme and zoom live in `config.Settings`; `Ctrl+B`
toggles the sidebar, `Ctrl+`/`Ctrl-`/`Ctrl+0` zoom.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QSystemTrayIcon,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openpi import config
from openpi.pi.index import default_session_dir, scan
from openpi.pi.process import pi_binary
from openpi.pi.session import PiSession
from openpi.server.client import RemoteClient, RemoteSession

from . import theme
from .pane import SessionPane
from .settings import SettingsDialog
from .tasks import run_async


class MainWindow(QMainWindow):
    def __init__(self, session_root: Path | None = None, state_dir: Path | None = None,
                 project: str | None = None, remote: RemoteClient | None = None) -> None:
        super().__init__()
        self.session_root = Path(session_root) if session_root else default_session_dir()
        self.state_dir = Path(state_dir) if state_dir else config.home_dir()
        config.ensure_home(self.state_dir)
        self.settings = config.load(self.state_dir)
        self._remote = remote
        self._panes: dict[str, SessionPane] = {}
        self._metas: list[dict] = []
        self._project = ""
        self._new_counter = 0

        self.setWindowTitle("openpi" + (f" — {remote.base}" if remote else ""))
        self.resize(1180, 760)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.rail = self._build_rail()
        splitter.addWidget(self.rail)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._placeholder())
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 900])
        self.setCentralWidget(splitter)
        self.statusBar().showMessage("connected" if remote else "pi not started")

        self._streaming = 0
        self._tray = None
        self._setup_tray()
        self._apply_theme()
        self._load_projects(project)
        self._refresh_sessions()

    # -- construction ----------------------------------------------------

    def _build_rail(self) -> QWidget:
        rail = QWidget()
        rail.setMinimumWidth(240)
        rail.setMaximumWidth(380)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self.hide_button = QPushButton("☰")
        self.hide_button.setObjectName("flat")
        self.hide_button.setFixedWidth(30)
        self.hide_button.setToolTip("Hide sidebar (Ctrl+B)")
        self.hide_button.clicked.connect(self._toggle_sidebar)
        title = QLabel("openpi")
        title.setStyleSheet("font-weight:700; font-size:14px;")
        self.settings_button = QPushButton("⚙")
        self.settings_button.setObjectName("flat")
        self.settings_button.setFixedWidth(30)
        self.settings_button.setToolTip("Settings")
        self.settings_button.clicked.connect(self._open_settings)
        header.addWidget(self.hide_button)
        header.addWidget(title, 1)
        header.addWidget(self.settings_button)
        layout.addLayout(header)

        layout.addWidget(self._section("Projects · Sessions"))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(16)
        self.tree.itemClicked.connect(self._tree_clicked)
        layout.addWidget(self.tree, 1)

        row = QHBoxLayout()
        add = QPushButton("+ folder")
        add.clicked.connect(self._add_project)
        new = QPushButton("+ session")
        new.clicked.connect(lambda: self._open(None))
        rescan = QPushButton("↻")
        rescan.setFixedWidth(30)
        rescan.setToolTip("Rescan sessions")
        rescan.clicked.connect(self._refresh_sessions)
        row.addWidget(add)
        row.addWidget(new)
        row.addWidget(rescan)
        layout.addLayout(row)
        return rail

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text.upper())
        label.setObjectName("muted")
        label.setStyleSheet("font-size:10px; letter-spacing:1px; padding:6px 2px 2px;")
        return label

    def _placeholder(self) -> QWidget:
        label = QLabel("Pick a session, or start a new one.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setObjectName("muted")
        return label

    # -- projects / sessions tree ----------------------------------------

    def _load_projects(self, project: str | None) -> None:
        wanted = project or self.settings.last_project or str(Path.cwd())
        if wanted not in self.settings.projects:
            self.settings.projects.insert(0, wanted)
        self._project = wanted
        self.settings.last_project = wanted
        config.save(self.settings, self.state_dir)

    def _add_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Add project folder", self._project or "")
        if path and path not in self.settings.projects:
            self.settings.projects.insert(0, path)
            config.save(self.settings, self.state_dir)
            self._refresh_sessions()

    def _refresh_sessions(self) -> None:
        if self._remote:
            run_async(self._remote.get_state, self._fill_remote,
                      lambda error: self.statusBar().showMessage(f"server unreachable: {error}"))
        else:
            run_async(lambda: scan(self.session_root), self._fill_local,
                      lambda error: self.statusBar().showMessage(f"session scan failed: {error}"))

    def _fill_local(self, metas) -> None:
        rows = [{"key": str(m.path), "title": m.title, "cwd": m.cwd, "path": str(m.path),
                 "preview": m.preview, "id": m.id, "busy": False} for m in metas]
        self._fill_tree(rows)

    def _fill_remote(self, state: dict) -> None:
        rows = [{"key": s["key"], "title": s.get("title") or s.get("cwd", ""),
                 "cwd": s.get("cwd", ""), "path": None, "preview": "", "id": s["key"],
                 "busy": s.get("busy", False)} for s in state.get("sessions", [])]
        self._fill_tree(rows)

    def _fill_tree(self, rows: list[dict]) -> None:
        self._metas = rows
        self.tree.clear()
        cwds = list(self.settings.projects)
        for row in rows:
            if row["cwd"] and row["cwd"] not in cwds:
                cwds.append(row["cwd"])
        for cwd in cwds:
            project_item = QTreeWidgetItem(self.tree)
            project_item.setText(0, f"📁 {Path(cwd).name if cwd else '(no folder)'}")
            project_item.setToolTip(0, cwd or "")
            project_item.setData(0, Qt.ItemDataRole.UserRole, ("project", cwd))
            project_item.setExpanded(cwd == self._project)
            for row in [r for r in rows if r["cwd"] == cwd]:
                child = QTreeWidgetItem(project_item)
                live = row["key"] in self._panes
                mark = "●" if (live or row["busy"]) else "○"
                child.setText(0, f"{mark} {row['title'][:48]}")
                child.setToolTip(0, f"{row['cwd']}\n{row['preview'] or row['id']}")
                child.setData(0, Qt.ItemDataRole.UserRole, ("session", row["key"]))
        self._update_status()

    def _tree_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, value = data
        if kind == "project":
            self._project = value
            self.settings.last_project = value
            config.save(self.settings, self.state_dir)
            self._refresh_sessions()
        elif kind == "session":
            if value in self._panes:
                self.stack.setCurrentWidget(self._panes[value])
                self._panes[value].composer.focus()
                return
            meta = next((m for m in self._metas if m["key"] == value), None)
            if meta:
                self._open(meta)

    # -- opening ---------------------------------------------------------

    def _open(self, meta: dict | None) -> None:
        if self._remote:
            self._open_remote(meta)
        else:
            self._open_local(meta)

    def _open_local(self, meta: dict | None) -> None:
        if not self._project:
            return
        cwd = meta["cwd"] if meta else self._project
        path = meta["path"] if meta else None
        if path and path in self._panes:
            self.stack.setCurrentWidget(self._panes[path])
            return

        trusted = self._ensure_trust(cwd)
        argv = [pi_binary(), "--mode", "rpc"]
        if path:
            argv += ["--session", path]
        argv.append("--approve" if trusted else "--no-approve")

        session = PiSession(argv, cwd=cwd, session_path=path, parent=self)
        self._attach(session, key=path or f"new-{self._new_counter}", rekey_by_file=True)

    def _open_remote(self, meta: dict | None) -> None:
        if meta and meta["key"] in self._panes:
            self.stack.setCurrentWidget(self._panes[meta["key"]])
            return
        cwd = meta["cwd"] if meta else (self._project or "")
        if meta:
            self._attach_remote(meta["key"], cwd)
            return
        run_async(lambda: self._remote.open(cwd=cwd),
                  lambda key: self._attach_remote(key, cwd),
                  lambda error: self.statusBar().showMessage(f"open failed: {error}"))

    def _attach_remote(self, key: str, cwd: str) -> None:
        session = RemoteSession(self._remote, key, cwd=cwd, parent=self)
        self._attach(session, key=key, rekey_by_file=False)

    def _attach(self, session, key: str, rekey_by_file: bool) -> None:
        pane = SessionPane(session)
        pane.status.connect(lambda message: self.statusBar().showMessage(message, 8000))
        pane.close_requested.connect(lambda: self._close_pane(pane))
        self._panes[key] = pane
        self.stack.addWidget(pane)
        self.stack.setCurrentWidget(pane)
        if rekey_by_file:
            session.ready.connect(lambda: self._session_ready(pane, session, key))
        session.changed.connect(self._update_status)
        session.state_changed.connect(lambda: self._pane_state_changed(pane))
        session.start()
        pane.composer.focus()
        self._update_status()

    def _pane_state_changed(self, pane: SessionPane) -> None:
        self._update_status()

    def _session_ready(self, pane: SessionPane, session: PiSession, key: str) -> None:
        file = session.state.session_file
        if file and key != file:
            self._panes.pop(key, None)
            self._panes[file] = pane
        if session.state.session_name:
            self.setWindowTitle(f"openpi — {session.state.session_name}")
        self._refresh_sessions()

    def _close_pane(self, pane: SessionPane) -> None:
        for key, value in list(self._panes.items()):
            if value is pane:
                self._panes.pop(key, None)
        pane.session.close()
        self.stack.removeWidget(pane)
        pane.deleteLater()
        if self.stack.count() == 1:
            self.stack.setCurrentIndex(0)
        self._refresh_sessions()

    def _ensure_trust(self, cwd: str) -> bool:
        if cwd in self.settings.trusted:
            return True
        if cwd in self.settings.untrusted:
            return False
        answer = QMessageBox.question(
            self, "Project trust",
            f"Load project-local pi resources from\n{cwd}\n\n"
            "That covers .pi/settings.json, .pi/extensions, .pi/skills, .pi/mcp.json, and "
            "project skills. File access is not limited either way.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.settings.trusted.append(cwd)
        else:
            self.settings.untrusted.append(cwd)
        config.save(self.settings, self.state_dir)
        return answer == QMessageBox.StandardButton.Yes

    # -- theme / settings / sidebar --------------------------------------

    def _apply_theme(self) -> None:
        app = QApplication.instance()
        theme.apply(app, self.settings.theme)
        theme.apply_zoom(app, self.settings.zoom)
        for pane in self._panes.values():
            pane.transcript.rebuild(pane.session.transcript)

    def _toggle_sidebar(self) -> None:
        self.settings.sidebar_visible = not self.settings.sidebar_visible
        config.save(self.settings, self.state_dir)
        self.rail.setVisible(self.settings.sidebar_visible)
        if not self.settings.sidebar_visible:
            self.statusBar().showMessage("sidebar hidden — Ctrl+B to show", 6000)

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self._build_catalog(), self)
        if dialog.exec():
            config.save(self.settings, self.state_dir)
            self._apply_theme()
            for pane in self._panes.values():
                pane.apply_favorites(self.settings.favorite_providers,
                                     self.settings.favorite_models)

    def _build_catalog(self) -> dict[str, list[str]]:
        catalog: dict[str, list[str]] = {}
        for pane in self._panes.values():
            for model in pane.session.models:
                catalog.setdefault(model.provider, [])
                if model.id not in catalog[model.provider]:
                    catalog[model.provider].append(model.id)
        return catalog

    def _zoom(self, level: int) -> None:
        level = max(-4, min(6, level))
        self.settings.zoom = level
        config.save(self.settings, self.state_dir)
        theme.apply_zoom(QApplication.instance(), level)

    def keyPressEvent(self, event) -> None:
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        if ctrl and event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._zoom(self.settings.zoom + 1)
            return
        if ctrl and event.key() == Qt.Key.Key_Minus:
            self._zoom(self.settings.zoom - 1)
            return
        if ctrl and event.key() == Qt.Key.Key_0:
            self._zoom(0)
            return
        if ctrl and event.key() == Qt.Key.Key_B:
            self._toggle_sidebar()
            return
        super().keyPressEvent(event)

    # -- status ----------------------------------------------------------

    def _update_status(self) -> None:
        panes = list(self._panes.values())
        streaming = sum(1 for p in panes if p.session.transcript.busy)
        waiting = sum(1 for p in panes if p.session.transcript.queued[0]
                      + p.session.transcript.queued[1])
        if self._streaming and not streaming and self._tray and not self.isActiveWindow():
            self._tray.showMessage("openpi", "work settled", QSystemTrayIcon.MessageIcon.Information)
        self._streaming = streaming
        parts = [f"{len(panes)} live", f"{streaming} streaming"]
        if waiting:
            parts.append(f"{waiting} queued")
        parts.append(self._remote.base if self._remote else pi_binary())
        self.statusBar().showMessage(" · ".join(parts))
        if streaming and not self.isActiveWindow():
            QApplication.alert(self)

    def session_count(self) -> int:
        return len(self._panes)

    # -- tray ------------------------------------------------------------

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#6ea8fe"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(6, 6, 52, 52)
        painter.end()
        self._tray = QSystemTrayIcon(QIcon(pixmap), self)
        menu = QMenu()
        show = menu.addAction("Show openpi")
        show.triggered.connect(self._show_window)
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.close)
        self._tray.setContextMenu(menu)
        self._tray.setToolTip("openpi")
        self._tray.activated.connect(
            lambda reason: self._show_window()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self._tray.show()

    def _show_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    # -- shutdown --------------------------------------------------------

    def closeEvent(self, event) -> None:
        for pane in list(self._panes.values()):
            pane.session.close()
        self._panes.clear()
        config.save(self.settings, self.state_dir)
        if self._tray is not None:
            self._tray.hide()
        super().closeEvent(event)
