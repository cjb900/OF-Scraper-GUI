import os

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


def _asset_path(filename):
    """Return a forward-slash path to an asset file (required by Qt QSS url())."""
    return os.path.join(_ASSETS_DIR, filename).replace("\\", "/")


def get_dark_theme_qss():
    """Return the dark-theme QSS with resolved asset paths for indicator icons."""
    check = _asset_path("check.svg")
    radio = _asset_path("radio.svg")
    return _DARK_THEME_TEMPLATE.format(check_svg=check, radio_svg=radio)


def get_light_theme_qss():
    """Return the light-theme QSS (Catppuccin Latte) with resolved asset paths."""
    check = _asset_path("check.svg")
    radio = _asset_path("radio.svg")
    return _LIGHT_THEME_TEMPLATE.format(check_svg=check, radio_svg=radio)


# Sidebar background colors used by main_window.py (kept in sync with QSS)
DARK_SIDEBAR_BG = "#181825"
LIGHT_SIDEBAR_BG = "#e6e9ef"
DARK_SEP_COLOR = "#313244"
LIGHT_SEP_COLOR = "#ccd0da"
DARK_LOGO_COLOR = "#89b4fa"
LIGHT_LOGO_COLOR = "#1e66f5"

# Module-level theme state
_is_dark = True


def is_dark_theme():
    return _is_dark


def set_theme(dark):
    global _is_dark
    _is_dark = dark


def themed(dark_val, light_val):
    """Return dark_val or light_val based on current theme."""
    return dark_val if _is_dark else light_val


# Centralized color palette — call themed() or use these dicts
COLORS = {
    "dark": {
        "base": "#1e1e2e",
        "mantle": "#181825",
        "surface0": "#313244",
        "surface1": "#45475a",
        "surface2": "#585b70",
        "text": "#cdd6f4",
        "subtext": "#a6adc8",
        "muted": "#6c7086",
        "blue": "#89b4fa",
        "sky": "#74c7ec",
        "teal": "#94e2d5",
        "green": "#a6e3a1",
        "yellow": "#f9e2af",
        "peach": "#fab387",
        "red": "#f38ba8",
        "mauve": "#cba6f7",
        "lavender": "#b4befe",
        "sep": "#313244",
        "warning": "#f9e2af",
    },
    "light": {
        "base": "#eff1f5",
        "mantle": "#e6e9ef",
        "surface0": "#ccd0da",
        "surface1": "#bcc0cc",
        "surface2": "#acb0be",
        "text": "#11111b",
        "subtext": "#3c3f58",
        "muted": "#6c6f85",
        "blue": "#1e66f5",
        "sky": "#04a5e5",
        "teal": "#179299",
        "green": "#40a02b",
        "yellow": "#df8e1d",
        "peach": "#fe640b",
        "red": "#d20f39",
        "mauve": "#8839ef",
        "lavender": "#7287fd",
        "sep": "#ccd0da",
        "warning": "#d35400",
    },
}


def c(name):
    """Get a named color for the current theme. E.g. c('blue') -> '#89b4fa' or '#1e66f5'."""
    palette = COLORS["dark"] if _is_dark else COLORS["light"]
    return palette.get(name, "#ff00ff")


_DARK_THEME_TEMPLATE = """
/* ==================== Global ==================== */
QWidget {{
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Consolas", monospace;
    font-size: 13px;
}}

/* ==================== Main Window ==================== */
QMainWindow {{
    background-color: #1e1e2e;
}}

QMainWindow::separator {{
    background-color: #313244;
    width: 1px;
    height: 1px;
}}

/* ==================== Menu / Toolbar ==================== */
QMenuBar {{
    background-color: #181825;
    border-bottom: 1px solid #313244;
}}

QMenuBar::item:selected {{
    background-color: #313244;
}}

QMenu {{
    background-color: #1e1e2e;
    border: 1px solid #313244;
}}

QMenu::item:selected {{
    background-color: #313244;
}}

QToolBar {{
    background-color: #181825;
    border-bottom: 1px solid #313244;
    spacing: 4px;
    padding: 2px;
}}

/* ==================== Buttons ==================== */
QPushButton {{
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 24px;
}}

QPushButton:hover {{
    background-color: #45475a;
    border-color: #89b4fa;
}}

QPushButton:pressed {{
    background-color: #585b70;
}}

QPushButton:disabled {{
    background-color: #1e1e2e;
    color: #585b70;
    border-color: #313244;
}}

QPushButton#primary_button, QPushButton[primary="true"] {{
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    font-weight: bold;
}}

QPushButton#primary_button:hover, QPushButton[primary="true"]:hover {{
    background-color: #74c7ec;
}}

QPushButton#danger_button, QPushButton[danger="true"] {{
    background-color: #f38ba8;
    color: #1e1e2e;
    border: none;
}}

QPushButton#danger_button:hover, QPushButton[danger="true"]:hover {{
    background-color: #eba0ac;
}}

/* ==================== Nav Buttons ==================== */
QPushButton.nav_button {{
    background-color: transparent;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    text-align: left;
    font-size: 14px;
    min-height: 32px;
}}

QPushButton.nav_button:hover {{
    background-color: #313244;
}}

QPushButton.nav_button:checked {{
    background-color: #313244;
    color: #89b4fa;
    border-left: 3px solid #89b4fa;
}}

/* ==================== Inputs ==================== */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QTimeEdit {{
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 24px;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QDateEdit:focus, QTimeEdit:focus {{
    border-color: #89b4fa;
}}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: #1e1e2e;
    color: #585b70;
}}

QLineEdit[placeholderText] {{
    color: #6c7086;
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox QAbstractItemView {{
    background-color: #313244;
    border: 1px solid #45475a;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}}

/* ==================== Checkboxes & Radio ==================== */
QCheckBox, QRadioButton {{
    spacing: 6px;
    color: #cdd6f4;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid #45475a;
    background-color: #313244;
}}

QCheckBox::indicator {{
    border-radius: 3px;
}}

QRadioButton::indicator {{
    border-radius: 9px;
}}

QCheckBox::indicator:checked {{
    background-color: #89b4fa;
    border-color: #89b4fa;
    image: url({check_svg});
}}

QRadioButton::indicator:checked {{
    background-color: #89b4fa;
    border-color: #89b4fa;
    image: url({radio_svg});
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: #89b4fa;
}}

/* ==================== Tables ==================== */
QTableView, QTreeView, QListView, QListWidget {{
    background-color: #1e1e2e;
    alternate-background-color: #181825;
    border: 1px solid #313244;
    gridline-color: #313244;
    selection-background-color: #313244;
    selection-color: #cdd6f4;
}}

QTableView::item:selected, QTreeView::item:selected,
QListView::item:selected, QListWidget::item:selected {{
    background-color: #313244;
}}

QTableView::item:hover, QListWidget::item:hover {{
    background-color: #2a2a3e;
}}

QHeaderView::section {{
    background-color: #181825;
    color: #a6adc8;
    border: none;
    border-right: 1px solid #313244;
    border-bottom: 1px solid #313244;
    padding: 6px 8px;
    font-weight: bold;
}}

QHeaderView::section:hover {{
    background-color: #313244;
    color: #89b4fa;
}}

/* ==================== Scroll Bars ==================== */
QScrollBar:vertical {{
    background-color: #1e1e2e;
    width: 10px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background-color: #45475a;
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: #585b70;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: #1e1e2e;
    height: 10px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background-color: #45475a;
    border-radius: 5px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: #585b70;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ==================== Tab Widget ==================== */
QTabWidget::pane {{
    border: 1px solid #313244;
    background-color: #1e1e2e;
}}

QTabBar::tab {{
    background-color: #181825;
    color: #6c7086;
    border: 1px solid #313244;
    border-bottom: none;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}

QTabBar::tab:selected {{
    background-color: #1e1e2e;
    color: #89b4fa;
    border-bottom: 2px solid #89b4fa;
}}

QTabBar::tab:hover:!selected {{
    background-color: #313244;
    color: #cdd6f4;
}}

/* ==================== Group Box ==================== */
QGroupBox {{
    border: 1px solid #313244;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #a6adc8;
}}

/* ==================== Progress Bar ==================== */
QProgressBar {{
    background-color: #313244;
    border: none;
    border-radius: 4px;
    text-align: center;
    min-height: 20px;
    color: #cdd6f4;
}}

QProgressBar::chunk {{
    background-color: #89b4fa;
    border-radius: 4px;
}}

/* ==================== Splitter ==================== */
QSplitter::handle {{
    background-color: #313244;
}}

QSplitter::handle:hover {{
    background-color: #89b4fa;
}}

/* ==================== Labels ==================== */
QLabel {{
    color: #cdd6f4;
    background-color: transparent;
}}

QLabel[heading="true"] {{
    font-size: 18px;
    font-weight: bold;
    color: #cdd6f4;
}}

QLabel[subheading="true"] {{
    font-size: 14px;
    color: #a6adc8;
}}

QLabel[muted="true"] {{
    color: #6c7086;
    font-size: 11px;
}}

/* ==================== Status Bar ==================== */
QStatusBar {{
    background-color: #181825;
    border-top: 1px solid #313244;
    color: #6c7086;
}}

/* ==================== Dialog ==================== */
QDialog {{
    background-color: #1e1e2e;
}}

/* ==================== Text Edit / Plain Text ==================== */
QPlainTextEdit, QTextEdit {{
    background-color: #181825;
    color: #a6e3a1;
    border: 1px solid #313244;
    border-radius: 4px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}}

/* ==================== Tooltips ==================== */
QToolTip {{
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    padding: 4px;
    border-radius: 4px;
}}

/* ==================== Frame ==================== */
QFrame[frameShape="4"] {{
    color: #313244;
    max-height: 1px;
}}

QFrame[frameShape="5"] {{
    color: #313244;
    max-width: 1px;
}}
"""

_LIGHT_THEME_TEMPLATE = """
/* ==================== Global ==================== */
QWidget {{
    background-color: #eff1f5;
    color: #11111b;
    font-family: "Segoe UI", "Consolas", monospace;
    font-size: 13px;
}}

/* ==================== Main Window ==================== */
QMainWindow {{
    background-color: #eff1f5;
}}

QMainWindow::separator {{
    background-color: #ccd0da;
    width: 1px;
    height: 1px;
}}

/* ==================== Menu / Toolbar ==================== */
QMenuBar {{
    background-color: #e6e9ef;
    border-bottom: 1px solid #ccd0da;
}}

QMenuBar::item:selected {{
    background-color: #ccd0da;
}}

QMenu {{
    background-color: #eff1f5;
    border: 1px solid #ccd0da;
}}

QMenu::item:selected {{
    background-color: #ccd0da;
}}

QToolBar {{
    background-color: #e6e9ef;
    border-bottom: 1px solid #ccd0da;
    spacing: 4px;
    padding: 2px;
}}

/* ==================== Buttons ==================== */
QPushButton {{
    background-color: #ccd0da;
    color: #11111b;
    border: 1px solid #bcc0cc;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 24px;
}}

QPushButton:hover {{
    background-color: #bcc0cc;
    border-color: #1e66f5;
}}

QPushButton:pressed {{
    background-color: #acb0be;
}}

QPushButton:disabled {{
    background-color: #eff1f5;
    color: #acb0be;
    border-color: #ccd0da;
}}

QPushButton#primary_button, QPushButton[primary="true"] {{
    background-color: #1e66f5;
    color: #eff1f5;
    border: none;
    font-weight: bold;
}}

QPushButton#primary_button:hover, QPushButton[primary="true"]:hover {{
    background-color: #2070ff;
}}

QPushButton#danger_button, QPushButton[danger="true"] {{
    background-color: #d20f39;
    color: #eff1f5;
    border: none;
}}

QPushButton#danger_button:hover, QPushButton[danger="true"]:hover {{
    background-color: #e33e5a;
}}

/* ==================== Nav Buttons ==================== */
QPushButton.nav_button {{
    background-color: transparent;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    text-align: left;
    font-size: 14px;
    min-height: 32px;
}}

QPushButton.nav_button:hover {{
    background-color: #ccd0da;
}}

QPushButton.nav_button:checked {{
    background-color: #ccd0da;
    color: #1e66f5;
    border-left: 3px solid #1e66f5;
}}

/* ==================== Inputs ==================== */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QTimeEdit {{
    background-color: #dce0e8;
    color: #11111b;
    border: 1px solid #bcc0cc;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 24px;
    selection-background-color: #1e66f5;
    selection-color: #eff1f5;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QDateEdit:focus, QTimeEdit:focus {{
    border-color: #1e66f5;
}}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: #eff1f5;
    color: #acb0be;
}}

QLineEdit[placeholderText] {{
    color: #9ca0b0;
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox QAbstractItemView {{
    background-color: #dce0e8;
    border: 1px solid #bcc0cc;
    selection-background-color: #1e66f5;
    selection-color: #eff1f5;
}}

/* ==================== Checkboxes & Radio ==================== */
QCheckBox, QRadioButton {{
    spacing: 6px;
    color: #11111b;
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid #bcc0cc;
    background-color: #dce0e8;
}}

QCheckBox::indicator {{
    border-radius: 3px;
}}

QRadioButton::indicator {{
    border-radius: 9px;
}}

QCheckBox::indicator:checked {{
    background-color: #1e66f5;
    border-color: #1e66f5;
    image: url({check_svg});
}}

QRadioButton::indicator:checked {{
    background-color: #1e66f5;
    border-color: #1e66f5;
    image: url({radio_svg});
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: #1e66f5;
}}

/* ==================== Tables ==================== */
QTableView, QTreeView, QListView, QListWidget {{
    background-color: #eff1f5;
    alternate-background-color: #e6e9ef;
    border: 1px solid #ccd0da;
    gridline-color: #ccd0da;
    selection-background-color: #ccd0da;
    selection-color: #4c4f69;
}}

QTableView::item:selected, QTreeView::item:selected,
QListView::item:selected, QListWidget::item:selected {{
    background-color: #ccd0da;
}}

QTableView::item:hover, QListWidget::item:hover {{
    background-color: #dce0e8;
}}

QHeaderView::section {{
    background-color: #e6e9ef;
    color: #2c2f47;
    border: none;
    border-right: 1px solid #ccd0da;
    border-bottom: 1px solid #ccd0da;
    padding: 6px 8px;
    font-weight: bold;
}}

QHeaderView::section:hover {{
    background-color: #ccd0da;
    color: #1e66f5;
}}

/* ==================== Scroll Bars ==================== */
QScrollBar:vertical {{
    background-color: #eff1f5;
    width: 10px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background-color: #bcc0cc;
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: #acb0be;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background-color: #eff1f5;
    height: 10px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background-color: #bcc0cc;
    border-radius: 5px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: #acb0be;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ==================== Tab Widget ==================== */
QTabWidget::pane {{
    border: 1px solid #ccd0da;
    background-color: #eff1f5;
}}

QTabBar::tab {{
    background-color: #e6e9ef;
    color: #4c4f69;
    border: 1px solid #ccd0da;
    border-bottom: none;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}

QTabBar::tab:selected {{
    background-color: #eff1f5;
    color: #1e66f5;
    border-bottom: 2px solid #1e66f5;
}}

QTabBar::tab:hover:!selected {{
    background-color: #ccd0da;
    color: #11111b;
}}

/* ==================== Group Box ==================== */
QGroupBox {{
    border: 1px solid #ccd0da;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: #2c2f47;
}}

/* ==================== Progress Bar ==================== */
QProgressBar {{
    background-color: #ccd0da;
    border: none;
    border-radius: 4px;
    text-align: center;
    min-height: 20px;
    color: #11111b;
}}

QProgressBar::chunk {{
    background-color: #1e66f5;
    border-radius: 4px;
}}

/* ==================== Splitter ==================== */
QSplitter::handle {{
    background-color: #ccd0da;
}}

QSplitter::handle:hover {{
    background-color: #1e66f5;
}}

/* ==================== Labels ==================== */
QLabel {{
    color: #11111b;
    background-color: transparent;
}}

QLabel[heading="true"] {{
    font-size: 18px;
    font-weight: bold;
    color: #11111b;
}}

QLabel[subheading="true"] {{
    font-size: 14px;
    color: #3c3f58;
}}

QLabel[muted="true"] {{
    color: #4c4f69;
    font-size: 11px;
}}

/* ==================== Status Bar ==================== */
QStatusBar {{
    background-color: #e6e9ef;
    border-top: 1px solid #ccd0da;
    color: #4c4f69;
}}

/* ==================== Dialog ==================== */
QDialog {{
    background-color: #eff1f5;
}}

/* ==================== Text Edit / Plain Text ==================== */
QPlainTextEdit, QTextEdit {{
    background-color: #e6e9ef;
    color: #40a02b;
    border: 1px solid #ccd0da;
    border-radius: 4px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    selection-background-color: #1e66f5;
    selection-color: #eff1f5;
}}

/* ==================== Tooltips ==================== */
QToolTip {{
    background-color: #ccd0da;
    color: #11111b;
    border: 1px solid #bcc0cc;
    padding: 4px;
    border-radius: 4px;
}}

/* ==================== Frame ==================== */
QFrame[frameShape="4"] {{
    color: #ccd0da;
    max-height: 1px;
}}

QFrame[frameShape="5"] {{
    color: #ccd0da;
    max-width: 1px;
}}
"""
