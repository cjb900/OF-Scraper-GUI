"""Pre-scrape job size / ETA confirmation for the GUI.

Shows a summary before large or high-impact scrapes so users can cancel
before wiping DBs, rescraping everything, or starting huge multi-model runs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QMessageBox, QWidget

log = logging.getLogger("shared")

# Session-only skip for typical jobs (not destructive).
_session_skip = False
# One-shot: table/page already confirmed; workflow must not re-prompt.
_scrape_confirm_ack = False


@dataclass
class ScrapeJobSummary:
    actions: list[str] = field(default_factory=list)
    model_names: list[str] = field(default_factory=list)
    areas: list[str] = field(default_factory=list)
    mediatypes: list[str] = field(default_factory=list)
    manual_url_count: int = 0
    scrape_paid: bool = False
    scrape_labels: bool = False
    allow_dupes: bool = False
    rescrape_all: bool = False
    delete_db: bool = False
    delete_downloads: bool = False
    daemon_enabled: bool = False
    daemon_interval_min: float = 0.0
    date_from: str | None = None
    date_to: str | None = None
    check_mode: bool = False

    @property
    def model_count(self) -> int:
        return len(self.model_names)

    @property
    def area_count(self) -> int:
        return len(self.areas)

    @property
    def is_destructive(self) -> bool:
        return bool(self.delete_db or self.delete_downloads)

    @property
    def is_high_impact(self) -> bool:
        return bool(
            self.is_destructive
            or self.rescrape_all
            or self.allow_dupes
            or self.scrape_paid
            or self.daemon_enabled
        )


def reset_session_skip() -> None:
    global _session_skip, _scrape_confirm_ack
    _session_skip = False
    _scrape_confirm_ack = False


def _privacy_name(name: str) -> str:
    try:
        from ofscraper.gui.utils.privacy_mode import is_privacy_mode

        if is_privacy_mode():
            return "[Hidden for Privacy]"
    except Exception:
        pass
    return name


def estimate_eta(summary: ScrapeJobSummary) -> str:
    """Rough wall-time band for user awareness (not a precise forecast)."""
    models = max(summary.model_count, 1 if summary.manual_url_count else 0)
    if summary.manual_url_count and not models:
        # Manual URL jobs scale with entry count.
        n = summary.manual_url_count
        low = max(1, n // 20)
        high = max(low + 1, n // 5)
    else:
        areas = max(summary.area_count, 1)
        low = max(1, models * max(1, areas // 3))
        high = max(low + 1, models * max(2, areas) * 2)
        if summary.rescrape_all or summary.delete_db:
            low = max(low, models * 5)
            high = max(high * 3, low + 5)
        if summary.scrape_paid:
            high = int(high * 1.5) + 5
        if summary.check_mode:
            high = int(high * 1.25) + 2
        if summary.manual_url_count:
            high += max(1, summary.manual_url_count // 10)

    if high >= 180:
        return f"Rough ETA: ~{low}–{high} min (possibly several hours for large libraries)"
    if high >= 60:
        return f"Rough ETA: ~{low}–{high} min (large job — time varies with content volume)"
    return f"Rough ETA: ~{low}–{high} min (estimate only; actual time depends on content)"


def should_prompt(summary: ScrapeJobSummary) -> bool:
    """Whether to show the confirm dialog for this job."""
    global _session_skip, _scrape_confirm_ack

    if _scrape_confirm_ack:
        return False

    # Always confirm destructive actions.
    if summary.is_destructive:
        return True

    try:
        from ofscraper.gui.utils.gui_settings import load_gui_settings

        if bool(load_gui_settings().get("skip_scrape_confirm")):
            return False
    except Exception:
        pass

    if _session_skip:
        return False

    if summary.is_high_impact:
        return True
    if summary.model_count >= 2:
        return True
    if summary.area_count >= 4:
        return True
    if summary.manual_url_count >= 10:
        return True
    if summary.check_mode and summary.model_count >= 1:
        return True
    return False


def format_summary_html(summary: ScrapeJobSummary) -> str:
    names = [_privacy_name(n) for n in summary.model_names]
    if len(names) <= 8:
        models_txt = ", ".join(names) if names else "(none)"
    else:
        models_txt = (
            f"{len(names)} models ("
            + ", ".join(names[:5])
            + f", … +{len(names) - 5} more)"
        )

    actions = ", ".join(summary.actions) if summary.actions else "(default download)"
    areas = ", ".join(summary.areas) if summary.areas else "(none / N/A)"
    media = ", ".join(summary.mediatypes) if summary.mediatypes else "(config default)"

    flags = []
    if summary.scrape_paid:
        flags.append("Scrape entire paid page")
    if summary.scrape_labels:
        flags.append("Scrape labels")
    if summary.allow_dupes:
        flags.append("Allow duplicates")
    if summary.rescrape_all:
        flags.append("<b>Rescrape everything</b>")
    if summary.delete_db:
        flags.append("<b style='color:#f38ba8'>Delete model DB</b>")
    if summary.delete_downloads:
        flags.append("<b style='color:#f38ba8'>Delete downloaded files</b>")
    if summary.daemon_enabled:
        flags.append(f"Daemon every {summary.daemon_interval_min:g} min")
    if summary.manual_url_count:
        flags.append(f"Manual URLs/IDs: {summary.manual_url_count}")
    if summary.date_from or summary.date_to:
        flags.append(
            f"Date filter: {summary.date_from or '…'} → {summary.date_to or '…'}"
        )

    flags_html = (
        "<ul>" + "".join(f"<li>{f}</li>" for f in flags) + "</ul>"
        if flags
        else "<p><i>No high-impact advanced options.</i></p>"
    )

    return (
        f"<p><b>Actions:</b> {actions}<br/>"
        f"<b>Models ({summary.model_count}):</b> {models_txt}<br/>"
        f"<b>Areas ({summary.area_count}):</b> {areas}<br/>"
        f"<b>Media types:</b> {media}</p>"
        f"<p><b>Options:</b></p>{flags_html}"
        f"<p>{estimate_eta(summary)}</p>"
        "<p>ETA is a rough guide only — OF-Scraper cannot know exact media volume "
        "until the scrape runs.</p>"
    )


def build_summary_from_workflow(workflow) -> ScrapeJobSummary:
    """Build a summary from GUIWorkflow state (check / manual / areas path)."""
    actions = sorted(str(a) for a in (getattr(workflow, "_selected_actions", None) or set()))
    models = getattr(workflow, "_selected_models", None) or []
    names = []
    for m in models:
        n = getattr(m, "name", None) or str(m)
        if n:
            names.append(n)
    advanced = getattr(workflow, "_advanced", None) or {}
    date = getattr(workflow, "_date_range", None) or {}
    check_modes = getattr(workflow, "_CHECK_MODES", set()) or set()
    date_enabled = bool(isinstance(date, dict) and date.get("enabled"))
    return ScrapeJobSummary(
        actions=actions,
        model_names=names,
        areas=list(getattr(workflow, "_selected_areas", None) or []),
        mediatypes=list(getattr(workflow, "_selected_mediatypes", None) or []),
        manual_url_count=len(getattr(workflow, "_manual_urls", None) or []),
        scrape_paid=bool(getattr(workflow, "_scrape_paid", False)),
        scrape_labels=False,
        allow_dupes=bool(advanced.get("allow_dupe_downloads")),
        rescrape_all=bool(advanced.get("rescrape_all")),
        delete_db=bool(advanced.get("delete_model_db")),
        delete_downloads=bool(advanced.get("delete_downloads")),
        daemon_enabled=bool(getattr(workflow, "_daemon_enabled", False)),
        daemon_interval_min=float(getattr(workflow, "_daemon_interval", 0) or 0),
        date_from=(date.get("from_date") if date_enabled else None),
        date_to=(date.get("to_date") if date_enabled else None),
        check_mode=bool(set(actions) & set(check_modes)),
    )


def build_summary_from_table_start(table_page, area_page) -> ScrapeJobSummary:
    """Build a summary from the table Start Scraping click path."""
    main = table_page.window()
    workflow = getattr(main, "workflow", None)
    if workflow is not None:
        # Prefer live area-page toggles (just about to be emitted).
        summary = build_summary_from_workflow(workflow)
    else:
        summary = ScrapeJobSummary()

    try:
        summary.areas = list(area_page.get_selected_areas() or [])
    except Exception:
        pass

    try:
        actions = getattr(area_page, "_current_actions", None)
        if actions:
            summary.actions = sorted(str(a) for a in actions)
            check_modes = {"post_check", "msg_check", "paid_check", "story_check"}
            summary.check_mode = bool(set(summary.actions) & check_modes)
    except Exception:
        pass

    try:
        summary.scrape_paid = bool(
            getattr(area_page, "scrape_paid_check", None)
            and area_page.scrape_paid_check.isChecked()
        )
        summary.scrape_labels = bool(
            getattr(area_page, "scrape_labels_check", None)
            and area_page.scrape_labels_check.isChecked()
        )
    except Exception:
        pass

    try:
        summary.allow_dupes = bool(
            getattr(area_page, "allow_dupes_check", None)
            and area_page.allow_dupes_check.isChecked()
        )
        summary.rescrape_all = bool(
            getattr(area_page, "rescrape_all_check", None)
            and area_page.rescrape_all_check.isChecked()
        )
        summary.delete_db = bool(
            getattr(area_page, "delete_db_check", None)
            and area_page.delete_db_check.isChecked()
        )
        summary.delete_downloads = bool(
            getattr(area_page, "delete_downloads_check", None)
            and area_page.delete_downloads_check.isChecked()
        )
    except Exception:
        pass

    try:
        summary.daemon_enabled = bool(area_page.is_daemon_enabled())
        if summary.daemon_enabled:
            summary.daemon_interval_min = float(area_page.get_daemon_interval() or 0)
    except Exception:
        pass

    try:
        mt = getattr(area_page, "get_selected_mediatypes", None)
        if callable(mt):
            summary.mediatypes = list(mt() or [])
    except Exception:
        pass

    try:
        fs = getattr(table_page, "sidebar", None)
        if fs is not None:
            after_on = bool(getattr(fs, "after_enabled", None) and fs.after_enabled.isChecked())
            before_on = bool(getattr(fs, "before_enabled", None) and fs.before_enabled.isChecked())
            if after_on:
                summary.date_from = fs.get_after_date_str()
            if before_on:
                summary.date_to = fs.get_before_date_str()
    except Exception:
        pass

    return summary


def confirm_scrape_job(
    parent: QWidget | None,
    summary: ScrapeJobSummary,
    *,
    mark_ack: bool = True,
) -> bool:
    """Show confirm dialog when needed. Return True to proceed."""
    global _session_skip, _scrape_confirm_ack

    if _scrape_confirm_ack:
        _scrape_confirm_ack = False
        return True

    if not should_prompt(summary):
        return True

    msg = QMessageBox(parent)
    msg.setIcon(
        QMessageBox.Icon.Warning if summary.is_destructive else QMessageBox.Icon.Question
    )
    msg.setWindowTitle("Confirm scrape")
    msg.setTextFormat(Qt.TextFormat.RichText)
    msg.setText("<b>Review this scrape before starting</b>")
    msg.setInformativeText(format_summary_html(summary))
    msg.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    msg.setDefaultButton(
        QMessageBox.StandardButton.No
        if summary.is_destructive
        else QMessageBox.StandardButton.Yes
    )
    yes = msg.button(QMessageBox.StandardButton.Yes)
    if yes is not None:
        yes.setText("Start Scraping")
    no = msg.button(QMessageBox.StandardButton.No)
    if no is not None:
        no.setText("Cancel")

    skip_cb = None
    if not summary.is_destructive:
        skip_cb = QCheckBox(
            "Don't ask again for typical jobs (still warn for delete DB/files)"
        )
        msg.setCheckBox(skip_cb)

    result = msg.exec()
    if result != QMessageBox.StandardButton.Yes:
        log.info("[GUI] Scrape confirm declined")
        _scrape_confirm_ack = False
        return False

    if skip_cb is not None and skip_cb.isChecked():
        _session_skip = True
        try:
            from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings

            s = load_gui_settings()
            s["skip_scrape_confirm"] = True
            save_gui_settings(s)
            log.info("[GUI] Scrape confirm suppressed (gui_settings.skip_scrape_confirm)")
        except Exception as e:
            log.debug(f"[GUI] Could not persist skip_scrape_confirm: {e}")

    if mark_ack:
        _scrape_confirm_ack = True
    return True
