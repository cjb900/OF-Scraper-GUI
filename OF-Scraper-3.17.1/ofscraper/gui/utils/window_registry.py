"""Track secondary GUI windows so Help/About/etc. don't stack duplicates.

SubScraper opens FAQ/About with ``new()+Show()`` and no tracking; Pika uses
this registry so a second open raises the existing window instead.
"""
from __future__ import annotations

import weakref
from typing import Callable, Optional

from PyQt6.QtWidgets import QWidget

_registry: dict[str, weakref.ReferenceType] = {}


def get_open(key: str) -> Optional[QWidget]:
    """Return the live widget for ``key``, or None if closed/missing."""
    ref = _registry.get(key)
    if ref is None:
        return None
    widget = ref()
    if widget is None:
        _registry.pop(key, None)
        return None
    try:
        # Deleted Qt objects can still be weakly referenced briefly.
        if not widget.isVisible() and widget.parent() is None:
            # Still valid — may be hidden; caller decides.
            pass
        _ = widget.windowTitle()
    except RuntimeError:
        _registry.pop(key, None)
        return None
    return widget


def register(key: str, widget: QWidget) -> None:
    """Remember ``widget`` under ``key``; clear the slot when destroyed."""
    if widget is None:
        return

    def _clear(_obj=None, *, _key=key):
        cur = _registry.get(_key)
        if cur is not None and cur() is None:
            _registry.pop(_key, None)
        elif cur is not None and cur() is widget:
            _registry.pop(_key, None)

    _registry[key] = weakref.ref(widget, _clear)
    try:
        widget.destroyed.connect(lambda *_: _registry.pop(key, None))
    except Exception:
        pass


def show_or_raise(
    key: str,
    factory: Callable[[], QWidget],
    *,
    raise_hidden: bool = True,
) -> QWidget:
    """Return existing window for ``key``, or create via ``factory`` and show it.

    If an instance exists, it is raised/activated instead of creating another.
    """
    existing = get_open(key)
    if existing is not None:
        try:
            if raise_hidden or existing.isVisible():
                existing.show()
                existing.raise_()
                existing.activateWindow()
            return existing
        except RuntimeError:
            _registry.pop(key, None)

    widget = factory()
    register(key, widget)
    try:
        widget.show()
        widget.raise_()
        widget.activateWindow()
    except Exception:
        pass
    return widget


def close_if_open(key: str) -> None:
    w = get_open(key)
    if w is None:
        return
    try:
        w.close()
    except Exception:
        pass
    _registry.pop(key, None)
