"""Host↔core scrape event contract (SubScraper IDownloadEventHandler-style).

GUI and (later) CLI implement the same thin callbacks so status, progress,
phase, and cancel live in one place instead of scattered signal emits.
"""
from __future__ import annotations

import threading
from typing import Optional, Protocol, runtime_checkable

_lock = threading.RLock()
_current_host: Optional["ScrapeHostCallbacks"] = None


@runtime_checkable
class ScrapeHostCallbacks(Protocol):
    """Minimal host contract for scrape/download orchestration."""

    def on_status(self, message: str) -> None:
        """Surface a short status line to the user."""

    def on_progress(self, completed: int, total: int, label: str = "") -> None:
        """Update overall download progress counts."""

    def on_phase(self, phase: str) -> None:
        """Lifecycle phase: ready | running | cancelling | daemon | complete.

        ``scraping`` is accepted as an alias for ``running``.
        """

    def is_cancelled(self) -> bool:
        """True when the host has requested cooperative cancel."""

    def on_item_started(self, username: str) -> None:
        """Optional: model/item processing began."""

    def on_item_result(self, username: str, ok: bool, error: str = "") -> None:
        """Optional per-model / per-item outcome (GUI may ignore or aggregate)."""


class NullHostCallbacks:
    """No-op host used when no GUI/CLI callbacks are installed."""

    def on_status(self, message: str) -> None:
        return

    def on_progress(self, completed: int, total: int, label: str = "") -> None:
        return

    def on_phase(self, phase: str) -> None:
        return

    def is_cancelled(self) -> bool:
        return False

    def on_item_started(self, username: str) -> None:
        return

    def on_item_result(self, username: str, ok: bool, error: str = "") -> None:
        return


class GuiHostCallbacks:
    """Qt GUI host: routes events through ``app_signals`` + cancel event."""

    def on_status(self, message: str) -> None:
        try:
            from ofscraper.gui.signals import app_signals
            from ofscraper.gui.utils.privacy_mode import redact_status_message

            app_signals.status_message.emit(redact_status_message(str(message or "")))
        except Exception:
            pass

    def on_progress(self, completed: int, total: int, label: str = "") -> None:
        try:
            from ofscraper.gui.utils.progress_bridge import update_overall_progress

            update_overall_progress(int(completed), int(total))
            if label:
                from ofscraper.gui.signals import app_signals
                from ofscraper.gui.utils.privacy_mode import redact_status_message

                app_signals.status_message.emit(redact_status_message(str(label)))
        except Exception:
            try:
                from ofscraper.gui.signals import app_signals

                app_signals.overall_progress_updated.emit(int(completed), int(total))
            except Exception:
                pass

    def on_phase(self, phase: str) -> None:
        try:
            from ofscraper.gui.signals import app_signals

            p = str(phase or "ready").strip().lower()
            if p == "scraping":
                p = "running"
            app_signals.scrape_phase_changed.emit(p)
        except Exception:
            pass

    def is_cancelled(self) -> bool:
        try:
            from ofscraper.gui.utils.workflow import is_gui_cancelled

            return bool(is_gui_cancelled())
        except Exception:
            return False

    def on_item_started(self, username: str) -> None:
        try:
            from ofscraper.gui.signals import app_signals

            name = str(username or "").strip()
            if name:
                app_signals.model_item_started.emit(name)
        except Exception:
            pass

    def on_item_result(self, username: str, ok: bool, error: str = "") -> None:
        try:
            from ofscraper.gui.signals import app_signals

            name = str(username or "").strip()
            if name:
                app_signals.model_item_result.emit(
                    name, bool(ok), str(error or "")
                )
        except Exception:
            pass


_NULL = NullHostCallbacks()


def get_host() -> ScrapeHostCallbacks:
    """Return the active host callbacks (never None)."""
    with _lock:
        return _current_host or _NULL


def set_host(host: Optional[ScrapeHostCallbacks]) -> None:
    """Install (or clear) the active host callbacks for the scrape thread."""
    global _current_host
    with _lock:
        _current_host = host


def ensure_gui_host() -> GuiHostCallbacks:
    """Install GuiHostCallbacks if nothing is set; return the GUI host."""
    with _lock:
        if isinstance(_current_host, GuiHostCallbacks):
            return _current_host
        host = GuiHostCallbacks()
        _current_host = host
        return host
