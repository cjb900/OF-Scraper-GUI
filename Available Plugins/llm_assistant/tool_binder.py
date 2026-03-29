"""
tool_binder.py — Maps LLM tool calls to live GUI actions.

Holds a reference to main_window and drives its widgets / signals directly.
All methods are called from the GUI thread after inference finishes.
"""

import logging

log = logging.getLogger("ofscraper_plugin.llm_assistant.tools")

_ALL_AREAS = [
    "Timeline", "Messages", "Pinned", "Archived",
    "Stories", "Highlights", "Purchased", "Profile", "Streams",
]

# Loose aliases the LLM might produce → canonical area name
_AREA_ALIASES: dict[str, str | None] = {
    "timeline": "Timeline", "post": "Timeline", "posts": "Timeline",
    "messages": "Messages", "message": "Messages", "msg": "Messages",
    "dms": "Messages", "dm": "Messages", "chat": "Messages",
    "pinned": "Pinned",
    "archived": "Archived", "archive": "Archived",
    "stories": "Stories", "story": "Stories",
    "highlights": "Highlights", "highlight": "Highlights",
    "purchased": "Purchased", "bought": "Purchased",
    "profile": "Profile",
    "streams": "Streams", "stream": "Streams", "live": "Streams",
}


class ToolBinder:
    """Executes LLM tool-call dicts against the live main_window instance."""

    def __init__(self, main_window):
        self.mw = main_window

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute_all(self, tool_calls: list[dict]) -> list[str]:
        """Run every tool call; returns a list of human-readable result strings."""
        results = []
        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("args") or {}
            try:
                result = self._dispatch(name, args)
                results.append(result)
                log.info("Tool '%s' OK: %s", name, result)
            except Exception as e:
                msg = f"⚠ '{name}' failed: {e}"
                log.error(msg)
                results.append(msg)
        return results

    def get_gui_state(self) -> dict:
        """Read current GUI selections into a plain dict for LLM context."""
        state: dict = {
            "action": "download",
            "usernames": [],
            "areas": [],
            "media_types": ["Images", "Videos"],
            "price_filter": "all",
            "daemon": False,
            "daemon_interval": 30,
        }
        try:
            area_page = getattr(self.mw, "area_page", None)
            if area_page:
                checks = getattr(area_page, "_area_checks", {}) or {}
                state["areas"] = [k for k, cb in checks.items() if cb.isChecked()]

                dc = getattr(area_page, "daemon_check", None)
                state["daemon"] = bool(dc and dc.isChecked())
                di = getattr(area_page, "daemon_interval", None)
                if di:
                    state["daemon_interval"] = di.value()
        except Exception:
            pass

        try:
            wf = getattr(self.mw, "workflow", None)
            if wf:
                models = getattr(wf, "_selected_models", None) or []
                state["usernames"] = [getattr(m, "name", "") for m in models] or []
                acts = getattr(wf, "_selected_actions", set()) or set()
                if acts:
                    state["action"] = "+".join(sorted(acts))
        except Exception:
            pass

        return state

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, name: str, args: dict) -> str:
        handlers = {
            "set_action":       self._set_action,
            "set_usernames":    self._set_usernames,
            "set_areas":        self._set_areas,
            "set_media_types":  self._set_media_types,
            "set_price_filter": self._set_price_filter,
            "set_daemon":       self._set_daemon,
            "set_date_filter":  self._set_date_filter,
            "navigate_to":      self._navigate_to,
            "reset_settings":   self._reset_settings,
            "start_scraping":   self._start_scraping,
        }
        fn = handlers.get(name)
        if fn is None:
            return f"Unknown tool: {name}"
        return fn(args)

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _set_action(self, args: dict) -> str:
        action = str(args.get("action", "download")).lower().replace(" ", "_")
        action_map: dict[str, set] = {
            "download":      {"download"},
            "like":          {"like"},
            "unlike":        {"unlike"},
            "download_like": {"download", "like"},
            "download+like": {"download", "like"},
        }
        actions = action_map.get(action, {"download"})
        try:
            from ofscraper.gui.signals import app_signals
            app_signals.action_selected.emit(actions)
        except Exception as e:
            log.warning("action_selected signal failed: %s", e)
        # Also keep area_page in sync
        try:
            ap = getattr(self.mw, "area_page", None)
            if ap and hasattr(ap, "_current_actions"):
                ap._current_actions = actions
        except Exception:
            pass
        return f"Action set to: {action}"

    def _set_usernames(self, args: dict) -> str:
        raw = args.get("usernames", [])
        if isinstance(raw, str):
            raw = [raw]
        usernames = [str(u).strip() for u in raw if str(u).strip()]
        if not usernames:
            return "No usernames provided"
        # Store for _start_scraping to pick up after area_page's async model load.
        # Do NOT call all_subs_retriver() here — area_page owns that fetch and runs
        # it in a worker thread; blocking the GUI thread would race with it.
        self._pending_usernames = usernames
        log.info("Usernames queued (will select after model load): %s", usernames)
        return f"Usernames queued: {usernames}"

    def _set_areas(self, args: dict) -> str:
        raw = args.get("areas", [])
        if isinstance(raw, str):
            raw = [raw]

        resolved: set[str] = set()
        for a in raw:
            key = a.strip().lower()
            if key == "all":
                resolved.update(_ALL_AREAS)
            else:
                canonical = _AREA_ALIASES.get(key, a.strip().title())
                if canonical in _ALL_AREAS:
                    resolved.add(canonical)

        if not resolved:
            return f"No valid areas recognised in: {raw}"

        try:
            ap = getattr(self.mw, "area_page", None)
            if ap:
                checks = getattr(ap, "_area_checks", {}) or {}
                for area, cb in checks.items():
                    cb.setChecked(area in resolved)
        except Exception as e:
            return f"Could not set areas: {e}"

        return f"Areas set to: {sorted(resolved)}"

    def _set_media_types(self, args: dict) -> str:
        raw = args.get("types", [])
        if isinstance(raw, str):
            raw = [raw]
        type_map = {
            "image": "Images", "images": "Images",
            "photo": "Images", "photos": "Images",
            "video": "Videos", "videos": "Videos",
            "audio": "Audios", "audios": "Audios",
            "music": "Audios", "sound": "Audios",
        }
        resolved = [type_map.get(t.strip().lower(), t.strip().title()) for t in raw]
        valid = {"Images", "Videos", "Audios"}
        resolved = [t for t in resolved if t in valid]
        if not resolved:
            return f"No valid media types in: {raw}"
        try:
            from ofscraper.gui.signals import app_signals
            app_signals.mediatypes_configured.emit(resolved)
        except Exception as e:
            return f"Could not set media types: {e}"
        return f"Media types set to: {resolved}"

    def _set_price_filter(self, args: dict) -> str:
        f = str(args.get("filter", "all")).lower()
        try:
            ap = getattr(self.mw, "area_page", None)
            if ap:
                spc = getattr(ap, "scrape_paid_check", None)
                if spc:
                    spc.setChecked(f != "free")
        except Exception as e:
            return f"Could not set price filter: {e}"
        return f"Price filter set to: {f}"

    def _set_daemon(self, args: dict) -> str:
        enabled = bool(args.get("enabled", False))
        interval = float(args.get("interval_minutes", 60))
        try:
            ap = getattr(self.mw, "area_page", None)
            if ap:
                dc = getattr(ap, "daemon_check", None)
                di = getattr(ap, "daemon_interval", None)
                if dc:
                    dc.setChecked(enabled)
                if di and enabled:
                    di.setValue(max(1.0, interval))
        except Exception as e:
            return f"Could not set daemon: {e}"
        status = f"ON ({interval:.0f} min)" if enabled else "OFF"
        return f"Daemon {status}"

    def _set_date_filter(self, args: dict) -> str:
        after = args.get("after") or None
        before = args.get("before") or None
        try:
            from ofscraper.gui.signals import app_signals
            payload = {
                "enabled": bool(after or before),
                "from_date": after,
                "to_date": before,
            }
            app_signals.date_range_configured.emit(payload)
        except Exception as e:
            return f"Could not set date filter: {e}"
        parts = []
        if after:
            parts.append(f"after {after}")
        if before:
            parts.append(f"before {before}")
        return "Date filter: " + (", ".join(parts) if parts else "cleared")

    def _navigate_to(self, args: dict) -> str:
        section_map = {
            "scraper": "scraper", "main": "scraper",
            "auth": "auth", "authentication": "auth",
            "config": "config", "configuration": "config", "settings": "config",
            "profiles": "profiles", "profile": "profiles",
            "merge": "merge", "mergedbs": "merge",
            "help": "help", "readme": "help",
        }
        section = str(args.get("section", "scraper")).lower()
        page_id = section_map.get(section, "scraper")
        try:
            self.mw._navigate(page_id)
        except Exception as e:
            return f"Navigation failed: {e}"
        return f"Navigated to '{page_id}'"

    def _reset_settings(self, args: dict) -> str:
        try:
            ap = getattr(self.mw, "area_page", None)
            if ap:
                if hasattr(ap, "reset_to_defaults"):
                    ap.reset_to_defaults()
                else:
                    for cb in (getattr(ap, "_area_checks", {}) or {}).values():
                        cb.setChecked(False)
                    dc = getattr(ap, "daemon_check", None)
                    if dc:
                        dc.setChecked(False)
        except Exception as e:
            return f"Reset partially failed: {e}"
        return "Settings reset to defaults"

    def _start_scraping(self, args: dict) -> str:
        try:
            from PyQt6.QtCore import QTimer
            table_page = getattr(self.mw, "table_page", None)
            if not table_page:
                return "Table page not available"

            pending = getattr(self, "_pending_usernames", None)

            if pending:
                # area_page is loading models asynchronously in a worker thread.
                # Poll every 500 ms until it finishes, then filter models and start.
                ap = getattr(self.mw, "area_page", None)
                _attempts = [0]

                def _try_select_and_start():
                    _attempts[0] += 1
                    still_loading = ap and getattr(ap, "_models_loading", False)
                    mm = getattr(
                        getattr(self.mw, "manager", None), "model_manager", None
                    )
                    all_models = list(getattr(mm, "all_subs_obj", None) or []) if mm else []

                    if still_loading and not all_models and _attempts[0] < 40:
                        # Not ready yet — try again in 500 ms (max 20 s wait)
                        QTimer.singleShot(500, _try_select_and_start)
                        return

                    # Models available (or timed out) — apply username filter
                    if all_models and pending:
                        want = {u.lower() for u in pending}
                        if "all" in want:
                            selected = all_models
                        else:
                            selected = [
                                m for m in all_models
                                if getattr(m, "name", "").lower() in want
                            ]
                        if selected:
                            try:
                                from ofscraper.gui.signals import app_signals
                                app_signals.models_selected.emit(selected)
                                log.info(
                                    "AI: models_selected emitted for %d user(s): %s",
                                    len(selected),
                                    [getattr(m, "name", "?") for m in selected],
                                )
                            except Exception as sig_err:
                                log.warning("models_selected emit failed: %s", sig_err)
                        else:
                            log.warning(
                                "AI: no models matched %s in %d loaded models",
                                pending, len(all_models),
                            )

                    self._pending_usernames = None
                    # Give models_selected signal time to be processed, then start
                    QTimer.singleShot(300, table_page._on_start_scraping)

                self.mw._navigate("scraper")
                QTimer.singleShot(500, _try_select_and_start)
                return "Waiting for model list, then scraping…"

            # No pending username filter — navigate to table and start directly
            self.mw._navigate("scraper")
            ss = getattr(self.mw, "scraper_stack", None)
            if ss:
                ss.setCurrentWidget(table_page)
            QTimer.singleShot(100, table_page._on_start_scraping)
            return "Scraping started!"
        except Exception as e:
            return f"Could not start scraping: {e}"
