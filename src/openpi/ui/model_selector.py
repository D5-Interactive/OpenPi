"""Fixed-width, searchable model picker.

A `QComboBox` with hundreds of entries stretches off-screen, so this is a button that opens a
popup: a filter box plus a provider-grouped list with pinned providers and models floated to
the top. The popup sizes to the viewport, never wider than the button.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openpi.protocol.records import Model


class _Popup(QWidget):
    def __init__(self, selector: "ModelSelector") -> None:
        super().__init__(selector, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter models…")
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setMaximumWidth(360)
        layout.addWidget(self.tree)
        self.setMinimumWidth(300)
        self._groups: dict[str, QTreeWidgetItem] = {}

    def populate(self, models: list[Model], current: tuple[str, str],
                 provider_favs: set[str], model_favs: set[str]) -> None:
        self.tree.clear()
        self._groups = {}
        groups: dict[str, list[Model]] = {}
        for model in models:
            groups.setdefault(model.provider, []).append(model)

        def sort_key(pair):
            provider, model = pair
            fav = 0 if f"{provider}/{model.id}" in model_favs else 1
            return (fav, (model.name or model.id).lower())

        for provider in sorted(groups, key=lambda p: (p not in provider_favs, p.lower())):
            provider_item = QTreeWidgetItem(self.tree)
            star = "★ " if provider in provider_favs else ""
            provider_item.setText(0, f"{star}{provider}")
            provider_item.setFlags(provider_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            provider_item.setData(0, Qt.ItemDataRole.UserRole, ("group", provider))
            self._groups[provider] = provider_item
            for model in sorted(groups[provider], key=lambda m: sort_key((provider, m))):
                child = QTreeWidgetItem(provider_item)
                star = "★ " if f"{provider}/{model.id}" in model_favs else ""
                child.setText(0, f"{star}{model.name or model.id}")
                child.setData(0, Qt.ItemDataRole.UserRole, ("model", provider, model.id))
                if (provider, model.id) == current:
                    self.tree.setCurrentItem(child)
            provider_item.setExpanded(True)

    def _filter(self, text: str) -> None:
        needle = text.lower()
        for provider, group in self._groups.items():
            matches = 0
            for i in range(group.childCount()):
                child = group.child(i)
                shown = needle in (child.text(0) or "").lower() or needle in provider.lower()
                child.setHidden(not shown)
                matches += int(shown)
            group.setHidden(matches == 0)


class ModelSelector(QPushButton):
    model_chosen = Signal(str, str)  # provider, id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMaximumWidth(300)
        self.setMinimumWidth(140)
        self.setText("no model")
        self._models: list[Model] = []
        self._current: tuple[str, str] = ("", "")
        self._provider_favs: set[str] = set()
        self._model_favs: set[str] = set()
        self._popup = _Popup(self)
        self._popup.tree.itemClicked.connect(self._chosen)
        self.clicked.connect(self._toggle)

    def set_models(self, models: list[Model], provider: str = "", model_id: str = "") -> None:
        self._models = models
        self._current = (provider or "", model_id or "")
        self._refresh_label()

    def set_favorites(self, provider_favs: list[str], model_favs: list[str]) -> None:
        self._provider_favs = set(provider_favs)
        self._model_favs = set(model_favs)

    def _refresh_label(self) -> None:
        provider, model_id = self._current
        for model in self._models:
            if model.provider == provider and model.id == model_id:
                star = "★ " if f"{provider}/{model_id}" in self._model_favs else ""
                self.setText(f"{star}{model.name or model_id}")
                return
        self.setText(model_id or "select model")

    def _toggle(self) -> None:
        if not self._models:
            return
        self._popup.populate(self._models, self._current, self._provider_favs, self._model_favs)
        self._popup.search.clear()
        point = self.mapToGlobal(self.rect().bottomLeft())
        self._popup.adjustSize()
        height = min(self._popup.height(), 480)
        self._popup.resize(max(300, self.width()), height)
        self._popup.move(point)
        self._popup.show()
        self._popup.search.setFocus()

    def _chosen(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data[0] == "model":
            _kind, provider, model_id = data
            self._current = (provider, model_id)
            self._refresh_label()
            self._popup.hide()
            self.model_chosen.emit(provider, model_id)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._popup.isVisible():
            self._popup.hide()
            return
        super().keyPressEvent(event)
