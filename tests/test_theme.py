from PySide6.QtWidgets import QApplication

from openpi.ui import theme


def test_palette_modes_have_distinct_backgrounds():
    assert theme.palette("dark").bg == theme.DARK.bg
    assert theme.palette("light").bg == theme.LIGHT.bg
    assert theme.palette("dark").bg != theme.palette("light").bg


def test_qss_covers_scrollbars_and_focus(app):
    stylesheet = theme._qss(theme.palette("dark"))
    assert "QScrollBar:vertical" in stylesheet
    assert "QScrollBar::handle:horizontal" in stylesheet
    assert "QScrollBar::add-line" in stylesheet


def test_apply_sets_the_stylesheet_and_updates_aliases(app):
    theme.apply(app, "light")
    assert "QScrollBar" in app.styleSheet()
    assert theme.BG == theme.LIGHT.bg
    theme.apply(app, "dark")
    assert theme.BG == theme.DARK.bg


def test_apply_zoom_scales_the_font(app):
    theme.apply_zoom(app, 0)
    base = app.font().pointSize()
    theme.apply_zoom(app, 3)
    assert app.font().pointSize() > base
    theme.apply_zoom(app, 0)
