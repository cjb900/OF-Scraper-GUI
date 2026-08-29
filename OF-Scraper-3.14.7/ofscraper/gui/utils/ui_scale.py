"""GUI font scaling — design sizes are relative to a 13px baseline.

Persist preference as ``gui_font_size`` in ``gui_settings.json``.
Hardcoded ``setFont`` / QSS sizes should go through ``apply_font`` / ``scale_px``
so a single sidebar control can resize the whole UI.
"""

from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QWidget

log = logging.getLogger("shared")

DESIGN_BASE = 13
ALLOWED_SIZES = (12, 13, 14, 16, 18, 20)
_PROP = "_gui_font_design"

_current = DESIGN_BASE


def allowed_sizes() -> tuple[int, ...]:
    return ALLOWED_SIZES


def get_gui_font_size() -> int:
    return int(_current)


def snap_font_size(size: Any) -> int:
    try:
        size = int(size)
    except Exception:
        size = DESIGN_BASE
    if size in ALLOWED_SIZES:
        return size
    return min(ALLOWED_SIZES, key=lambda s: abs(s - size))


def set_gui_font_size(size: int, *, persist: bool = False) -> int:
    """Set the active GUI font size (snapped). Optionally persist to gui_settings."""
    global _current
    size = snap_font_size(size)
    _current = size
    if persist:
        try:
            from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings

            settings = load_gui_settings()
            settings["gui_font_size"] = size
            # Keep Help preference aligned with global UI size.
            settings["help_font_size"] = size
            save_gui_settings(settings, quiet=True)
        except Exception as e:
            log.debug(f"[GUI] Could not persist gui_font_size: {e}")
    return size


def load_gui_font_size_from_settings() -> int:
    """Load size from gui_settings (migrates legacy help_font_size if needed)."""
    size = DESIGN_BASE
    try:
        from ofscraper.gui.utils.gui_settings import load_gui_settings

        s = load_gui_settings()
        if "gui_font_size" in s:
            size = s.get("gui_font_size", DESIGN_BASE)
        elif "help_font_size" in s:
            size = s.get("help_font_size", DESIGN_BASE)
    except Exception:
        size = DESIGN_BASE
    return set_gui_font_size(size, persist=False)


def scale_px(design_px: float) -> int:
    """Scale a design pixel size (relative to 13px) to the active GUI size."""
    try:
        design_px = float(design_px)
    except Exception:
        design_px = float(DESIGN_BASE)
    return max(8, int(round(design_px * _current / DESIGN_BASE)))


def scale_pt(design_pt: float) -> int:
    """Scale a design point size (relative to 13) to the active GUI size."""
    return scale_px(design_pt)


def qss_font_vars(base: int | None = None) -> dict[str, int]:
    """Placeholder values for theme QSS templates."""
    global _current
    prev = _current
    if base is not None:
        _current = snap_font_size(base)
    try:
        return {
            "font_base": scale_px(13),
            "font_14": scale_px(14),
            "font_18": scale_px(18),
            "font_11": scale_px(11),
            "font_12": scale_px(12),
            "font_12_5": scale_px(12.5),
        }
    finally:
        if base is not None:
            _current = prev


def gui_font(
    family: str,
    design_pt: float,
    weight: QFont.Weight = QFont.Weight.Normal,
) -> QFont:
    return QFont(family, scale_pt(design_pt), weight)


def apply_font(
    widget,
    family: str,
    design_pt: float,
    weight: QFont.Weight = QFont.Weight.Normal,
) -> None:
    """setFont with a remembered design size so refresh_scaled_fonts can update it.

    Works for QWidget and for item types that support setFont (QTableWidgetItem,
    QListWidgetItem). Design metadata is only stored on QObject subclasses.
    """
    try:
        from PyQt6.QtCore import QObject

        if isinstance(widget, QObject):
            widget.setProperty(_PROP, (str(family), float(design_pt), int(weight)))
    except Exception:
        pass
    try:
        widget.setFont(gui_font(family, design_pt, weight))
    except Exception:
        pass


def refresh_scaled_fonts(root: QWidget | None = None) -> int:
    """Re-apply fonts recorded via apply_font under *root* (default: all top-levels)."""
    updated = 0
    widgets: list[QWidget] = []
    try:
        if root is not None:
            widgets.append(root)
            widgets.extend(root.findChildren(QWidget))
        else:
            app = QApplication.instance()
            if app is None:
                return 0
            for w in app.topLevelWidgets():
                widgets.append(w)
                widgets.extend(w.findChildren(QWidget))
    except Exception:
        return 0

    seen: set[int] = set()
    for w in widgets:
        try:
            wid = id(w)
            if wid in seen:
                continue
            seen.add(wid)
            design = w.property(_PROP)
            if not design:
                continue
            family, design_pt, weight = design
            w.setFont(gui_font(str(family), float(design_pt), QFont.Weight(int(weight))))
            updated += 1
        except Exception:
            continue
    return updated


def apply_application_font() -> None:
    """Set QApplication default font from the active GUI size (design 13)."""
    try:
        app = QApplication.instance()
        if app is None:
            return
        app.setFont(gui_font("Segoe UI", DESIGN_BASE))
    except Exception as e:
        log.debug(f"[GUI] apply_application_font failed: {e}")
