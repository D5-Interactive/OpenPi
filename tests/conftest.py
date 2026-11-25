import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402 - must follow the platform setting


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])
