"""Settings dialog: appearance (theme, zoom), providers (detect + pi models.json), favorites."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from openpi import config
from openpi.pi import providers as pi_providers

from .tasks import run_async


class SettingsDialog(QDialog):
    def __init__(self, settings: config.Settings,
                 catalog: dict[str, list[str]] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(520, 440)
        self.settings = settings
        self.catalog = catalog or {}
        self._detected: dict[str, dict] = {}

        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._appearance_tab(), "Appearance")
        self.tabs.addTab(self._providers_tab(), "Providers")
        self.tabs.addTab(self._favorites_tab(), "Favorites")
        layout.addWidget(self.tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # -- appearance -------------------------------------------------------

    def _appearance_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(14)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme"))
        self.theme = QComboBox()
        self.theme.addItems(["dark", "light", "system"])
        self.theme.setCurrentText(self.settings.theme)
        theme_row.addWidget(self.theme, 1)
        layout.addLayout(theme_row)

        layout.addWidget(QLabel("Zoom (Ctrl+plus / Ctrl+minus / Ctrl+0)"))
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(-4, 6)
        self.zoom.setValue(self.settings.zoom)
        self.zoom.valueChanged.connect(
            lambda value: self.zoom_label.setText(f"{value:+d}"))
        self.zoom_label = QLabel(f"{self.settings.zoom:+d}")
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(self.zoom, 1)
        zoom_row.addWidget(self.zoom_label)
        layout.addLayout(zoom_row)
        layout.addStretch(1)
        return tab

    # -- providers --------------------------------------------------------

    def _providers_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        row = QHBoxLayout()
        row.addWidget(QLabel("Local model servers"))
        self.detect_button = QPushButton("Detect")
        self.detect_button.clicked.connect(self._detect)
        row.addWidget(self.detect_button)
        row.addStretch(1)
        layout.addLayout(row)

        self.provider_list = QListWidget()
        layout.addWidget(self.provider_list, 1)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Add selected to pi")
        self.add_button.setObjectName("send")
        self.add_button.clicked.connect(self._add_selected)
        self.remove_button = QPushButton("Remove from pi")
        self.remove_button.clicked.connect(self._remove_selected)
        actions.addWidget(self.add_button)
        actions.addWidget(self.remove_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self._refresh_provider_list()
        return tab

    def _detect(self) -> None:
        self.detect_button.setEnabled(False)
        self.detect_button.setText("Detecting…")

        def done(results: dict[str, dict]) -> None:
            self._detected = results
            self._refresh_provider_list()
            self.detect_button.setEnabled(True)
            self.detect_button.setText("Detect")

        run_async(pi_providers.detect_all, done,
                  lambda error: self.detect_button.setText(f"failed: {error}"))

    def _refresh_provider_list(self) -> None:
        configured = pi_providers.configured_providers()
        self.provider_list.clear()
        for key, (name, base_url) in pi_providers.KNOWN_SERVERS.items():
            detected = self._detected.get(key)
            configured_key = key in configured
            if detected and detected["ok"]:
                label = f"✓ {name} — {len(detected['models'])} models  ({base_url})"
            elif configured_key:
                label = f"⚙ {name} — configured  ({base_url})"
            else:
                label = f"○ {name} — not detected  ({base_url})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, (key, base_url))
            self.provider_list.addItem(item)

    def _selected_provider(self) -> tuple[str, str] | None:
        item = self.provider_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _add_selected(self) -> None:
        selected = self._selected_provider()
        if not selected:
            return
        key, base_url = selected
        models = self._detected.get(key, {}).get("models", [])
        pi_providers.configure_provider(key, base_url, models)
        self._refresh_provider_list()

    def _remove_selected(self) -> None:
        selected = self._selected_provider()
        if selected and pi_providers.remove_provider(selected[0]):
            self._refresh_provider_list()

    # -- favorites --------------------------------------------------------

    def _favorites_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)
        layout.addWidget(QLabel("Pinned providers and models float to the top of the picker."))

        row = QHBoxLayout()
        left = QVBoxLayout()
        left.addWidget(QLabel("Providers"))
        self.fav_providers = QListWidget()
        for provider in sorted(self.catalog):
            item = QListWidgetItem(f"{'★ ' if provider in self.settings.favorite_providers else '  '}{provider}")
            item.setData(Qt.ItemDataRole.UserRole, provider)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if provider in self.settings.favorite_providers
                               else Qt.CheckState.Unchecked)
            self.fav_providers.addItem(item)
        left.addWidget(self.fav_providers, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("Models"))
        self.fav_models = QListWidget()
        for provider, models in sorted(self.catalog.items()):
            for model_id in models:
                full = f"{provider}/{model_id}"
                item = QListWidgetItem(f"{'★ ' if full in self.settings.favorite_models else '  '}{full}")
                item.setData(Qt.ItemDataRole.UserRole, full)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if full in self.settings.favorite_models
                                   else Qt.CheckState.Unchecked)
                self.fav_models.addItem(item)
        right.addWidget(self.fav_models, 1)

        row.addLayout(left, 1)
        row.addLayout(right, 1)
        layout.addLayout(row, 1)
        return tab

    # -- commit -----------------------------------------------------------

    def accept(self) -> None:
        self.settings.theme = self.theme.currentText()
        self.settings.zoom = self.zoom.value()
        self.settings.favorite_providers = [
            self.fav_providers.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.fav_providers.count())
            if self.fav_providers.item(i).checkState() == Qt.CheckState.Checked]
        self.settings.favorite_models = [
            self.fav_models.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.fav_models.count())
            if self.fav_models.item(i).checkState() == Qt.CheckState.Checked]
        super().accept()
