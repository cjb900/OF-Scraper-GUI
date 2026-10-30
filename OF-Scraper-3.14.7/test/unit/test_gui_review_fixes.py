"""Fixes from the GUI review: theme colors, disabled buttons, labels, privacy, layout."""
import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

import ofscraper.gui.styles as styles  # noqa: E402
import ofscraper.gui.utils.privacy_mode as pm  # noqa: E402

GUI_DIR = pathlib.Path(styles.__file__).parent
PLUGINS_DIR = GUI_DIR.parents[2] / "Available Plugins"


@pytest.fixture
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    elif not isinstance(app, QtWidgets.QApplication):
        pytest.skip("a QCoreApplication from another test is already running")
    return app


@pytest.fixture
def privacy():
    """Turn Privacy mode on/off for a test, then restore it."""
    before = pm.is_privacy_mode()

    def set_(on):
        pm.set_privacy_mode(on, persist=False, emit=True)

    yield set_
    pm.set_privacy_mode(before, persist=False, emit=False)


# ── Theme colors ─────────────────────────────────────────────────────────────

def _color_names_used():
    names = set()
    files = list(GUI_DIR.rglob("*.py")) + list(PLUGINS_DIR.rglob("*.py"))
    for f in files:
        for m in re.finditer(r"""\bc\(\s*["'](\w+)["']\s*\)""", f.read_text(encoding="utf-8")):
            names.add(m.group(1))
    # Color maps looked up indirectly with c(...)
    from ofscraper.gui.widgets import model_badge_bar, status_strip

    names |= set(status_strip._PHASE_COLORS.values())
    names |= set(status_strip._HEALTH_LEVEL_COLORS.values())
    names |= set(model_badge_bar._STATUS_COLOR.values())
    return names


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_every_color_name_exists_in_the_theme(theme):
    # An unknown name falls back to bright magenta (#ff00ff).
    missing = sorted(_color_names_used() - set(styles.COLORS[theme]))
    assert missing == []


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("kind", ["primary", "danger"])
def test_disabled_colored_buttons_look_disabled(qapp, theme, kind):
    from ofscraper.gui.widgets.styled_button import StyledButton

    qss = styles.get_dark_theme_qss() if theme == "dark" else styles.get_light_theme_qss()
    host = QtWidgets.QWidget()
    host.setStyleSheet(qss)
    lay = QtWidgets.QHBoxLayout(host)
    on = StyledButton("On", **{kind: True})
    off = StyledButton("Off", **{kind: True})
    off.setEnabled(False)
    lay.addWidget(on)
    lay.addWidget(off)
    host.resize(300, 60)
    host.show()
    qapp.processEvents()

    def fill(btn):
        img = btn.grab().toImage()
        return img.pixelColor(4, img.height() // 2).name()

    color = styles.COLORS[theme]["blue" if kind == "primary" else "red"]
    assert fill(on) == color.lower()
    assert fill(off) != fill(on)
    host.close()


# ── Labels ───────────────────────────────────────────────────────────────────

def test_action_labels_show_a_real_ampersand(qapp):
    from ofscraper.gui.pages.action_page import ActionPage

    page = ActionPage(manager=None)
    texts = [b.text() for b in page.findChildren(QtWidgets.QRadioButton)]
    msg = [t for t in texts if t.startswith("Check messages")]
    # "&&" is shown as "&"; a single "&" would become a shortcut underline.
    assert msg and "message && paid" in msg[0]
    assert not [t for t in texts if re.search(r"(?<!&)&(?!&)", t)]


# ── Privacy mode on path fields ──────────────────────────────────────────────

def test_masked_path_fields_keep_the_real_path(qapp, privacy):
    privacy(False)
    edit = QtWidgets.QLineEdit()
    fields = pm.MaskedPathFields(edit)
    fields.set_value(edit, "/home/someone/keys")
    assert edit.text() == "/home/someone/keys"

    privacy(True)
    assert "someone" not in edit.text() and edit.isReadOnly()
    assert fields.value(edit) == "/home/someone/keys"
    fields.set_value(edit, "/home/someone/other")
    assert "someone" not in edit.text()

    privacy(False)
    assert edit.text() == "/home/someone/other" and not edit.isReadOnly()


def test_drm_and_merge_pages_hide_paths(qapp, privacy):
    from ofscraper.gui.dialogs.drm_dialog import DRMKeyPage
    from ofscraper.gui.dialogs.merge_dialog import MergePage

    privacy(False)
    drm, merge = DRMKeyPage(), MergePage()
    merge._paths.set_value(merge.source_input, "/home/someone/dbs")
    script = drm._paths.value(drm.script_input)
    privacy(True)
    for edit in (drm.script_input, merge.source_input):
        assert "/home/" not in edit.text()
    assert drm._paths.value(drm.script_input) == script
    assert merge._paths.value(merge.source_input) == "/home/someone/dbs"
    drm._on_line("saved to /home/someone/keys")
    assert "someone" not in drm.output_text.toPlainText()


# ── Layout ───────────────────────────────────────────────────────────────────

def test_next_is_the_last_button_on_the_areas_page(qapp):
    from ofscraper.gui.pages.area_selector_page import AreaSelectorPage

    page = AreaSelectorPage(manager=None)
    lay = page._nav_bar.layout()
    widgets = [lay.itemAt(i).widget() for i in range(lay.count()) if lay.itemAt(i).widget()]
    assert widgets[-1] is page.next_btn


def test_profile_buttons_follow_the_selection(qapp, monkeypatch):
    import ofscraper.utils.profiles.data as data
    from ofscraper.gui.dialogs.profile_dialog import ProfilePage

    monkeypatch.setattr(data, "get_profile_names", lambda: ["main_profile", "alt_profile"])
    monkeypatch.setattr(data, "get_active_profile", lambda: "main_profile")
    page = ProfilePage()
    buttons = (page.set_default_btn, page.rename_btn, page.delete_btn)
    assert not any(b.isEnabled() for b in buttons)  # nothing selected

    page.profile_list.setCurrentRow(0)  # the active profile
    assert page._get_selected_profile() == "main_profile"
    assert not any(b.isEnabled() for b in buttons)

    page.profile_list.setCurrentRow(1)
    assert all(b.isEnabled() for b in buttons)


def test_profiles_page_says_when_there_are_none(qapp, monkeypatch):
    import ofscraper.utils.profiles.data as data
    from ofscraper.gui.dialogs.profile_dialog import ProfilePage

    monkeypatch.setattr(data, "get_profile_names", lambda: [])
    monkeypatch.setattr(data, "get_active_profile", lambda: "main_profile")
    page = ProfilePage()
    assert page.profile_list.count() == 1
    assert "No profiles found" in page.profile_list.item(0).text()
    assert page._get_selected_profile() is None


def test_filters_panel_is_never_narrower_than_its_rows(qapp):
    from PyQt6.QtWidgets import QScrollArea
    from ofscraper.gui.pages.table_page import TablePage

    page = TablePage(manager=None)
    page.resize(1100, 700)
    page.show()
    qapp.processEvents()
    page._restore_filters_width()
    scroll = page.sidebar.findChild(QScrollArea)
    width = page._content_splitter.sizes()[0]
    assert scroll.viewport().width() >= scroll.widget().minimumSizeHint().width()
    assert width < 520  # the old default: the table gets the rest
    page.close()


# ── Page titles, status bar, toolbar (review items 9–11) ─────────────────────

PAGE_FILES = [
    "pages/action_page.py", "pages/model_selector_page.py", "pages/area_selector_page.py",
    "dialogs/auth_dialog.py", "dialogs/config_dialog.py", "dialogs/drm_dialog.py",
    "dialogs/profile_dialog.py", "dialogs/merge_dialog.py", "pages/plugins_page.py",
    "pages/help_page.py",
]


@pytest.mark.parametrize("path", PAGE_FILES)
def test_every_page_title_uses_the_shared_style(path):
    text = (GUI_DIR / path).read_text(encoding="utf-8")
    assert "style_page_title(header)" in text
    # a fixed QFont on the title would fight the shared size
    assert not re.search(r"apply_font\(header,", text)


def test_page_titles_render_the_same_on_every_page(qapp):
    from PyQt6.QtGui import QFontInfo
    from ofscraper.gui.dialogs.merge_dialog import MergePage
    from ofscraper.gui.pages.action_page import ActionPage

    host = QtWidgets.QWidget()
    host.setStyleSheet(styles.get_dark_theme_qss())
    lay = QtWidgets.QVBoxLayout(host)
    # Action sits in a scroll area, Merge doesn't: they used to differ (29 vs 18 px).
    pages = [ActionPage(manager=None), MergePage()]
    for p in pages:
        lay.addWidget(p)
    host.show()
    qapp.processEvents()
    sizes = set()
    for p in pages:
        title = [lb for lb in p.findChildren(QtWidgets.QLabel) if lb.property("heading")][0]
        sizes.add(QFontInfo(title.font()).pixelSize())
    host.close()
    assert len(sizes) == 1


def test_page_title_follows_the_gui_text_size(qapp):
    from ofscraper.gui.utils import ui_scale

    before = ui_scale.get_gui_font_size()
    label = QtWidgets.QLabel("Title")
    try:
        ui_scale.set_gui_font_size(13)
        ui_scale.style_page_title(label)
        small = label.styleSheet()
        ui_scale.set_gui_font_size(20)
        ui_scale.refresh_scaled_fonts(label)
        assert label.styleSheet() != small and "font-size" in label.styleSheet()
    finally:
        ui_scale.set_gui_font_size(before)


def test_window_status_bar_hides_only_on_the_scrape_table():
    from types import SimpleNamespace
    from ofscraper.gui.main_window import MainWindow

    shown = []
    scraper, table, other = object(), object(), object()
    win = SimpleNamespace(
        _pages={"scraper": scraper},
        table_page=table,
        status_bar=SimpleNamespace(setVisible=shown.append),
        stack=SimpleNamespace(currentWidget=lambda: scraper),
        scraper_stack=SimpleNamespace(currentWidget=lambda: table),
        _note_page_for_crash_log=lambda: None,
    )
    MainWindow._sync_status_bar(win)
    win.scraper_stack.currentWidget = lambda: other  # e.g. Select Action
    MainWindow._sync_status_bar(win)
    win.stack.currentWidget = lambda: other  # another sidebar page
    MainWindow._sync_status_bar(win)
    assert shown == [False, True, True]


def test_toolbar_keeps_color_for_main_and_stop_buttons_only(qapp):
    from ofscraper.gui.pages.table_page import TablePage

    page = TablePage(manager=None)
    surface = styles.c("surface1")
    for btn in (page.filter_btn, page.new_scrape_btn, page.reset_btn,
                page.open_folder_btn, page.history_btn, page.export_csv_btn):
        assert f"background-color: {surface}" in btn.styleSheet()
    assert styles.c("green") in page.start_scraping_btn.styleSheet()
    assert styles.c("red") in page.cancel_scrape_btn.styleSheet()


def test_crash_breadcrumbs_name_the_current_page():
    from types import SimpleNamespace
    import ofscraper.gui.utils.crash_diagnostics as cd
    from ofscraper.gui.main_window import MainWindow

    class TablePage:
        pass

    scraper, merge = object(), object()
    win = SimpleNamespace(
        _pages={"scraper": scraper, "merge": merge},
        stack=SimpleNamespace(currentWidget=lambda: merge),
        scraper_stack=SimpleNamespace(currentWidget=lambda: TablePage()),
    )
    MainWindow._note_page_for_crash_log(win)
    assert "page=merge" in cd.activity_snapshot()
    win.stack.currentWidget = lambda: scraper
    MainWindow._note_page_for_crash_log(win)
    assert "page=scraper/TablePage" in cd.activity_snapshot()


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("kind", ["QCheckBox", "QRadioButton"])
def test_disabled_checkboxes_look_disabled(qapp, theme, kind):
    qss = styles.get_dark_theme_qss() if theme == "dark" else styles.get_light_theme_qss()
    host = QtWidgets.QWidget()
    host.setStyleSheet(qss)
    lay = QtWidgets.QVBoxLayout(host)
    on = getattr(QtWidgets, kind)("Option")
    off = getattr(QtWidgets, kind)("Option")
    for box in (on, off):
        box.setChecked(True)
        lay.addWidget(box)
    off.setEnabled(False)
    host.show()
    qapp.processEvents()
    # Same checked box, enabled vs disabled: the pictures must differ.
    assert on.grab().toImage() != off.grab().toImage()
    host.close()
