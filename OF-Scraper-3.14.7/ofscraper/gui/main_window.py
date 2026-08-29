import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSlot, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.styles import (
    get_dark_theme_qss,
    get_light_theme_qss,
    set_theme,
    DARK_SIDEBAR_BG,
    LIGHT_SIDEBAR_BG,
    DARK_SEP_COLOR,
    LIGHT_SEP_COLOR,
    DARK_LOGO_COLOR,
    LIGHT_LOGO_COLOR,
)
from ofscraper.gui.utils.ui_scale import (
    DESIGN_BASE,
    allowed_sizes,
    apply_application_font,
    get_gui_font_size,
    load_gui_font_size_from_settings,
    refresh_scaled_fonts,
    scale_px,
    set_gui_font_size,
)
from ofscraper.gui.utils.workflow import GUIWorkflow
from ofscraper.gui.widgets.styled_button import NavButton

log = logging.getLogger("shared")

# Sidebar ASCII logo stays fixed so GUI text scaling cannot distort it.
_LOGO_PT = 5


class MainWindow(QMainWindow):
    """Central application window with navigation sidebar and stacked pages."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("OF-Scraper")
        self.setMinimumSize(1200, 750)
        self.resize(1400, 850)

        self._pages = {}
        self._nav_buttons = {}

        # Load saved theme preference (dark by default) + GUI font size
        try:
            from ofscraper.gui.utils.gui_settings import load_gui_settings
            _saved = load_gui_settings()
            self._is_dark = _saved.get("theme", "dark") == "dark"
            self._verbose_log = bool(_saved.get("verbose_log", False))
            from ofscraper.gui.utils.privacy_mode import load_privacy_mode_from_settings

            self._privacy_mode = load_privacy_mode_from_settings()
        except Exception:
            self._is_dark = True
            self._verbose_log = False
            self._privacy_mode = False
        try:
            load_gui_font_size_from_settings()
            apply_application_font()
        except Exception:
            pass
        set_theme(self._is_dark)
        if self._verbose_log:
            self._apply_verbose_log(True)

        # Initialize the workflow runner that bridges GUI → scraper backend
        self.workflow = GUIWorkflow(manager)

        self._setup_ui()
        # Always apply theme QSS so font-size placeholders match gui_font_size
        self._apply_theme_visuals(emit_signal=False)
        # Sync verbose button label to loaded preference
        if self._verbose_log:
            self._verbose_btn.setText("Verbose Log: On")
        # Sync privacy button (emit so pages apply masking after creation)
        try:
            from ofscraper.gui.utils.privacy_mode import set_privacy_mode

            set_privacy_mode(self._privacy_mode, persist=False, emit=True)
            self._privacy_btn.setText(
                f"Privacy: {'On' if self._privacy_mode else 'Off'}"
            )
        except Exception:
            pass
        self._connect_signals()

        # Load custom plugins and let them patch the UI if desired
        from ofscraper.plugins.manager import plugin_manager
        plugin_manager.discover_and_load()
        plugin_manager.dispatch_event("on_ui_setup", self)

        self._navigate("scraper")
        # Startup dialogs: Welcome first (if needed), then missing FFmpeg/CDM — never stack both.
        QTimer.singleShot(250, self._maybe_run_startup_dialogs)
        # Optional: if CLI args fully specify a scrape run, auto-start in GUI mode.
        QTimer.singleShot(350, self._maybe_autostart_from_cli_args)
        # Quiet PyPI update check (only prompts when a newer release exists).
        QTimer.singleShot(1400, self._maybe_check_for_updates)

    def _maybe_autostart_from_cli_args(self):
        """If invoked with --gui and sufficient CLI args, skip the GUI wizard and start scraping.

        Mirrors TUI behavior: when action/areas/usernames/daemon are provided, the app can
        begin scraping immediately without additional prompts/clicks.
        """
        try:
            import ofscraper.utils.args.accessors.read as read_args
            import ofscraper.utils.args.accessors.areas as areas_accessor
        except Exception:
            return

        try:
            args = read_args.retriveArgs()
        except Exception:
            return

        if not bool(getattr(args, "gui", False)):
            return

        # Require usernames (or a userlist) and areas to auto-start; action defaults to 'download'.
        # Check both 'actions' (Click dest) and legacy 'action' attribute.
        raw_actions = (
            getattr(args, "actions", None) or getattr(args, "action", None) or []
        )
        raw_users = getattr(args, "usernames", None) or []
        raw_posts = getattr(args, "posts", None) or []
        raw_da = getattr(args, "download_area", None) or []
        raw_la = getattr(args, "like_area", None) or []
        raw_userlist = getattr(args, "userlist", None) or []

        def _flatten_strs(v):
            out = []
            if v is None:
                return out
            if isinstance(v, (str, bytes)):
                return [str(v)]
            try:
                for item in v:
                    if isinstance(item, (list, set, tuple)):
                        out.extend([str(x) for x in item])
                    else:
                        out.append(str(item))
            except Exception:
                out.append(str(v))
            return out

        # Detect a user-specified list filter (excluding ofscraper's reserved names)
        try:
            import ofscraper.utils.of_env.of_env as _of_env
            _reserved = {
                (_of_env.getattr("OFSCRAPER_RESERVED_LIST") or "").lower(),
                (_of_env.getattr("OFSCRAPER_RESERVED_LIST_ALT") or "").lower(),
            }
        except Exception:
            _reserved = {"ofscraper.main", "main"}
        active_userlist = [
            u.lower() for u in _flatten_strs(raw_userlist)
            if u.strip() and u.strip().lower() not in _reserved
        ]

        actions = {a.strip().lower() for a in _flatten_strs(raw_actions) if str(a).strip()}
        usernames = {u.strip().lower() for u in _flatten_strs(raw_users) if str(u).strip()}
        has_download_areas = bool(_flatten_strs(raw_posts) or _flatten_strs(raw_da))
        has_like_areas = bool(_flatten_strs(raw_la))
        has_areas = has_download_areas or has_like_areas

        # Need either usernames or a userlist (and areas) to auto-start.
        # --ul without -u means "all models from that list".
        if (not usernames and not active_userlist) or not has_areas:
            return
        if not usernames and active_userlist:
            usernames = {"all"}

        # Infer action when --action/--actions not explicitly passed:
        # if only like_area is set → like; otherwise → download.
        if not actions:
            if has_like_areas and not has_download_areas:
                actions = {"like"}
            else:
                actions = {"download"}

        log.info(
            f"[GUI] Auto-start detected from CLI args: actions={sorted(actions)}, "
            f"usernames={('ALL' if 'all' in usernames else sorted(usernames))}"
            + (f", userlist={active_userlist}" if active_userlist else "")
        )

        # Apply the userlist to settings so the model fetch uses the correct filter.
        if active_userlist:
            try:
                import ofscraper.utils.settings as _autostart_settings
                _autostart_settings.update_settings()
            except Exception:
                pass

        # Compute final areas using the area accessors directly (bypasses
        # get_final_posts_area() which needs settings.actions to already be set).
        try:
            final_areas: set = set()
            if "download" in actions:
                final_areas.update(areas_accessor.get_download_area() or set())
            if "like" in actions or "unlike" in actions:
                final_areas.update(areas_accessor.get_like_area() or set())
            # Fallback: if neither produced areas (e.g. empty posts list), skip
            if not final_areas:
                return
        except Exception:
            final_areas = set()

        # Normalize label naming differences between CLI and GUI.
        if "Label" in final_areas and "Labels" not in final_areas:
            final_areas.discard("Label")
            final_areas.add("Labels")

        # Configure the Area Selector page state (areas + daemon).
        try:
            # Ensure the scraper sidebar is the active page (so widgets exist/rendered).
            self._navigate("scraper")
            self.scraper_stack.setCurrentWidget(self.area_page)
        except Exception:
            pass

        try:
            # Apply scrape-paid from CLI (prevents GUI defaults from clobbering it)
            self.area_page.scrape_paid_check.setChecked(
                bool(getattr(args, "scrape_paid", False))
            )
        except Exception:
            pass

        try:
            # Apply areas selection
            if final_areas:
                for area, cb in getattr(self.area_page, "_area_checks", {}).items():
                    cb.setChecked(area in final_areas)
        except Exception:
            pass

        # Daemon (minutes)
        try:
            daemon_val = getattr(args, "daemon", None)
            if daemon_val is not None and float(daemon_val) > 0:
                self.area_page.daemon_check.setChecked(True)
                self.area_page.daemon_interval.setValue(float(daemon_val))
            else:
                self.area_page.daemon_check.setChecked(False)
        except Exception:
            pass

        # Allow dupes (allow_dupe_downloads)
        try:
            allow_dupes_val = bool(getattr(args, "allow_dupe_downloads", False))
            self.area_page.allow_dupes_check.setChecked(allow_dupes_val)
            keep_msg_paid = bool(
                allow_dupes_val
                and getattr(args, "keep_message_purchased_dupes", False)
            )
            self.area_page.keep_msg_purchased_dupes_check.setEnabled(allow_dupes_val)
            self.area_page.keep_msg_purchased_dupes_check.setChecked(keep_msg_paid)
        except Exception:
            pass

        # Daemon discord ping
        try:
            discord_ping_val = bool(getattr(args, "discord_ping", False))
            self.area_page.daemon_discord_ping_check.setChecked(discord_ping_val)
        except Exception:
            pass

        # Discord webhook level (--discord / -dc). Must flip the GUI checkbox so
        # workflow._discord_level is not left OFF (scrape summaries / @here depend on it).
        try:
            discord_level = str(getattr(args, "discord_level", None) or "").strip().upper()
            if discord_level in ("LOW", "NORMAL"):
                self.area_page._block_discord_prompt = True
                if self.area_page.discord_updates_check.isEnabled():
                    self.area_page.discord_updates_check.setChecked(True)
                    self.area_page.discord_level_combo.setCurrentText(discord_level)
                self.area_page._block_discord_prompt = False
        except Exception:
            try:
                self.area_page._block_discord_prompt = False
            except Exception:
                pass

        # Video quality combo box
        try:
            quality_val = getattr(args, "quality", None)
            if quality_val:
                for i in range(self.area_page.quality_combo.count()):
                    if self.area_page.quality_combo.itemText(i).strip().lower() == str(quality_val).strip().lower():
                        self.area_page.quality_combo.setCurrentIndex(i)
                        break
        except Exception:
            pass

        # Load models in the background, then auto-select, then start scraping.
        try:
            from ofscraper.gui.utils.thread_worker import Worker
            from PyQt6.QtCore import QThreadPool, QTimer as _QT
        except Exception:
            return

        if not (self.manager and getattr(self.manager, "model_manager", None)):
            return

        def _fetch_models():
            from ofscraper.gui.utils.model_fetch import (
                fetch_subscription_models,
                publish_handoff,
                wait_for_ui_ack,
            )

            try:
                dicts = fetch_subscription_models(
                    userlist=active_userlist if active_userlist else None
                )
                publish_handoff(gen=1, payload=dicts)
                wait_for_ui_ack()
                return len(dicts or [])
            except Exception as e:
                publish_handoff(gen=1, error=str(e))
                wait_for_ui_ack()
                raise

        def _apply_quick_start():
            try:
                from ofscraper.gui.utils.model_fetch import handoff_ready

                worker = getattr(self, "_quick_start_worker", None)
                ready = handoff_ready(1)
                if not ready and (worker is None or not getattr(worker, "done", False)):
                    return
                try:
                    self._quick_start_poll.stop()
                except Exception:
                    pass
                # Defer so cleanup can ack the waiting worker cleanly.
                _QT.singleShot(150, _finish_quick_start)
            except Exception:
                return

        def _finish_quick_start():
            try:
                worker = getattr(self, "_quick_start_worker", None)
                from ofscraper.gui.utils.model_fetch import (
                    cleanup_model_fetch_environment,
                    dicts_to_models,
                    take_handoff,
                )

                handoff = take_handoff(1)
                try:
                    cleanup_model_fetch_environment()
                except Exception:
                    pass
                if handoff is None:
                    err = getattr(worker, "error_msg", None) if worker else None
                    if err:
                        log.warning(f"[GUI] Auto-start model fetch failed: {err}")
                    return
                if handoff.get("error"):
                    log.warning(
                        f"[GUI] Auto-start model fetch failed: {handoff['error']}"
                    )
                    return
                models = dicts_to_models(handoff.get("payload"))
                if self.manager and getattr(self.manager, "model_manager", None):
                    self.manager.model_manager.all_subs_dict = models or []
                try:
                    models = self.manager.model_manager._apply_filters()
                except Exception as e:
                    log.warning(f"[GUI] Auto-start filter error: {e}. Falling back to unfiltered models.")
                    models = list(models or [])
                if not models:
                    return
                excluded = set()
                try:
                    excluded = {
                        str(x).strip().lower()
                        for x in (getattr(args, "excluded_username", None) or [])
                        if str(x).strip()
                    }
                except Exception:
                    excluded = set()

                if "all" in usernames:
                    selected_models = [
                        m
                        for m in models
                        if getattr(m, "name", "").strip().lower() not in excluded
                    ]
                else:
                    want = set(usernames)
                    selected_models = [
                        m
                        for m in models
                        if getattr(m, "name", "").strip().lower() in want
                        and getattr(m, "name", "").strip().lower() not in excluded
                    ]
                if not selected_models:
                    log.warning("[GUI] Auto-start: no matching models found for usernames")
                    return

                try:
                    app_signals.action_selected.emit(set(actions))
                except Exception:
                    pass

                app_signals.models_selected.emit(selected_models)

                def _start():
                    try:
                        # Unattended CLI auto-start (Docker GUI_ARGS): do not block on
                        # interactive confirm / disk / remote-key dialogs.
                        try:
                            import ofscraper.gui.utils.scrape_confirm as _sc_confirm

                            _sc_confirm._scrape_confirm_ack = True
                            _sc_confirm._session_skip = True
                        except Exception:
                            pass
                        try:
                            import ofscraper.gui.utils.disk_space_check as _disk_check

                            _disk_check._disk_check_ack = True
                            _disk_check._session_skip = True
                        except Exception:
                            pass
                        try:
                            import ofscraper.gui.utils.key_mode_warning as _key_warn

                            _key_warn._session_skip_scrape_warning = True
                        except Exception:
                            pass
                        self.table_page._on_start_scraping()
                    except Exception:
                        pass

                _QT.singleShot(0, _start)
            except Exception:
                return

        try:
            from ofscraper.gui.utils.model_fetch import (
                clear_handoff,
                prepare_model_fetch_environment,
            )

            clear_handoff()
            prepare_model_fetch_environment()
        except Exception:
            pass

        self._quick_start_worker = Worker(_fetch_models, emit_signals=False)
        self._quick_start_poll = _QT(self)
        self._quick_start_poll.setInterval(50)
        self._quick_start_poll.timeout.connect(_apply_quick_start)
        try:
            QThreadPool.globalInstance().start(self._quick_start_worker)
            self._quick_start_poll.start()
        except Exception:
            return

    def _setup_ui(self):
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # -- Left navigation sidebar --
        nav_frame = QFrame()
        nav_frame.setFixedWidth(190)
        nav_frame.setStyleSheet("QFrame { background-color: #181825; }")
        nav_layout = QVBoxLayout(nav_frame)
        nav_layout.setContentsMargins(8, 12, 8, 12)
        nav_layout.setSpacing(4)

        # Logo / title (ASCII art) — use HTML <pre> for correct monospace alignment
        import html as _html
        _logo_lines = [
            r"        __                                    ",
            r"  ___  / _|___  ___ _ __ __ _ _ __   ___ _ __ ",
            r" / _ \| |_/ __|/ __| '__/ _` | '_ \ / _ \ '__|",
            r"| (_) |  _\__ \ (__| | | (_| | |_) |  __/ |   ",
            r" \___/|_|_|___/\___|_|  \__,_| .__/ \___|_|   ",
            r"       / /     \ \      / /  |_|\ \           ",
            r"      | |       | |    | |       | |          ",
            r"      | |   _   | |    | |   _   | |          ",
            r"      | |  (_)  | |    | |  (_)  | |          ",
            r"       \_\     /_/      \_\     /_/           ",
        ]
        _logo_html = (
            f"<pre style='color:#89b4fa; font-family:Consolas,monospace; "
            f"font-size:{_LOGO_PT}pt; margin:0; line-height:1;'>"
            + "\n".join(_html.escape(l) for l in _logo_lines)
            + "</pre>"
        )
        title_label = QLabel(_logo_html)
        title_label.setTextFormat(Qt.TextFormat.RichText)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont("Consolas", _LOGO_PT))
        title_label.setStyleSheet("padding: 4px 0 12px 0;")
        title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        nav_layout.addWidget(title_label)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #313244;")
        nav_layout.addWidget(sep)
        nav_layout.addSpacing(8)

        # Nav buttons
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        nav_items = [
            ("scraper", "⚡ Scraper"),
            ("auth", "🔑 Authentication"),
            ("config", "⚙️ Configuration"),
            ("drm", "🔒 DRM Key Creation"),
            ("profiles", "👥 Profiles"),
            ("merge", "🔀 Merge DBs"),
            ("plugins", "🧩 Plugins"),
            ("help", "📖 Help / README"),
        ]

        for page_id, label in nav_items:
            btn = NavButton(label)
            self._nav_group.addButton(btn)
            self._nav_buttons[page_id] = btn
            nav_layout.addWidget(btn)
            btn.clicked.connect(lambda checked, pid=page_id: self._navigate(pid))

        nav_layout.addStretch()

        def _style_sidebar_util_btn(btn: QPushButton) -> None:
            """Identical chrome for Light / Verbose / Privacy / version."""
            btn.setFixedHeight(28)
            btn.setMinimumHeight(28)
            btn.setMaximumHeight(28)
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            fs = scale_px(11)
            btn.setStyleSheet(
                "QPushButton {"
                f" font-size: {fs}px;"
                " padding: 2px 8px;"
                " min-height: 28px;"
                " max-height: 28px;"
                "}"
            )

        self._style_sidebar_util_btn = _style_sidebar_util_btn

        # Theme toggle button
        self._theme_btn = QPushButton("Light Mode")
        _style_sidebar_util_btn(self._theme_btn)
        self._theme_btn.clicked.connect(self._toggle_theme)
        nav_layout.addWidget(self._theme_btn)

        # Keep theme button disabled during model fetch / scrape (avoids AV).
        self._busy_chrome_timer = QTimer(self)
        self._busy_chrome_timer.setInterval(250)
        self._busy_chrome_timer.timeout.connect(self._sync_busy_chrome)
        self._busy_chrome_timer.start()

        # Verbose log toggle button
        self._verbose_btn = QPushButton("Verbose Log: Off")
        _style_sidebar_util_btn(self._verbose_btn)
        self._verbose_btn.clicked.connect(self._toggle_verbose_log)
        nav_layout.addWidget(self._verbose_btn)

        # Privacy / demo mode — hide secrets & paths for screenshots
        self._privacy_btn = QPushButton("Privacy: Off")
        _style_sidebar_util_btn(self._privacy_btn)
        self._privacy_btn.setToolTip(
            "Privacy / demo mode: hide auth cookies, paths, Discord webhooks, "
            "and usernames in the UI (safe for screenshots)."
        )
        self._privacy_btn.clicked.connect(self._toggle_privacy_mode)
        nav_layout.addWidget(self._privacy_btn)

        # Version button (click → About). Same spacing as the toggles above —
        # no extra spacer so the stack stays uniform.
        try:
            from ofscraper.__version__ import __version__
            _ver_text = f"v{__version__}"
        except Exception:
            _ver_text = "v3.12.9"
        ver_label = QPushButton(_ver_text)
        ver_label.setFlat(False)
        _style_sidebar_util_btn(ver_label)
        ver_label.setCursor(Qt.CursorShape.PointingHandCursor)
        ver_label.setToolTip("About OF-Scraper — click for version, patch ID, and FFmpeg info")
        ver_label.clicked.connect(self._open_about_dialog)
        nav_layout.addWidget(ver_label)

        # Store references for theme switching
        self._nav_frame = nav_frame
        self._title_label = title_label
        self._nav_sep = sep
        self._ver_label = ver_label

        main_layout.addWidget(nav_frame)

        # Vertical separator
        vsep = QFrame()
        vsep.setFrameShape(QFrame.Shape.VLine)
        vsep.setStyleSheet(f"color: {DARK_SEP_COLOR};")
        self._vsep = vsep
        main_layout.addWidget(vsep)

        # -- Right content area (stacked pages) --
        self.stack = QStackedWidget()
        self.stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        main_layout.addWidget(self.stack)

        # Create pages (lazy imports to avoid circular deps)
        self._create_pages()

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _toggle_theme(self):
        """Switch between dark and light themes, then offer to save as default.

        Full stylesheet + theme_changed rebuilds hard-crash Qt on Windows when
        done during model-list fetch (seen in crash breadcrumbs as Light Mode
        click while model_fetch=1, then die after worker_done). Defer instead.
        """
        try:
            from ofscraper.gui.utils.crash_diagnostics import (
                gui_action,
                is_heavy_background_active,
            )

            if is_heavy_background_active():
                gui_action("theme_deferred", "model_fetch_or_scrape_active")
                self._pending_theme_toggle = True
                if getattr(self, "_theme_defer_timer", None) is None:
                    t = QTimer(self)
                    t.setInterval(200)
                    t.timeout.connect(self._flush_pending_theme)
                    self._theme_defer_timer = t
                self._theme_defer_timer.start()
                try:
                    app_signals.status_message.emit(
                        "Theme change waiting until model list / scrape finishes…"
                    )
                except Exception:
                    pass
                return
        except Exception:
            pass
        self._do_toggle_theme()

    def _flush_pending_theme(self):
        if not getattr(self, "_pending_theme_toggle", False):
            try:
                self._theme_defer_timer.stop()
            except Exception:
                pass
            return
        try:
            from ofscraper.gui.utils.crash_diagnostics import is_heavy_background_active

            if is_heavy_background_active():
                return
        except Exception:
            pass
        self._pending_theme_toggle = False
        try:
            self._theme_defer_timer.stop()
        except Exception:
            pass
        self._do_toggle_theme()

    def _do_toggle_theme(self):
        """Apply theme switch + optional save prompt (must not run during fetch)."""
        try:
            from ofscraper.gui.utils.crash_diagnostics import gui_action

            gui_action("theme_toggle", f"to_dark={not self._is_dark}")
        except Exception:
            pass
        self._is_dark = not self._is_dark
        set_theme(self._is_dark)
        self._apply_theme_visuals()
        self._prompt_save_theme()

    def _sync_busy_chrome(self):
        """Disable theme toggle while model fetch / scrape is in flight."""
        busy = False
        try:
            from ofscraper.gui.utils.crash_diagnostics import is_heavy_background_active

            busy = is_heavy_background_active()
        except Exception:
            busy = False
        btn = getattr(self, "_theme_btn", None)
        if btn is None:
            return
        btn.setEnabled(not busy)
        if busy:
            btn.setToolTip(
                "Disabled while the model list is loading or a scrape is running"
            )
        else:
            btn.setToolTip("")

    def _toggle_verbose_log(self):
        """Toggle verbose (DEBUG-level) logging on or off."""
        self._verbose_log = not self._verbose_log
        self._apply_verbose_log(self._verbose_log)
        try:
            from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings
            s = load_gui_settings()
            s["verbose_log"] = self._verbose_log
            save_gui_settings(s)
        except Exception:
            pass
        state = "On" if self._verbose_log else "Off"
        app_signals.status_message.emit(f"Verbose logging {state}")

    def _toggle_privacy_mode(self):
        """Toggle privacy / demo mode (mask secrets and paths in the UI)."""
        self._privacy_mode = not getattr(self, "_privacy_mode", False)
        try:
            from ofscraper.gui.utils.privacy_mode import set_privacy_mode

            set_privacy_mode(self._privacy_mode, persist=True, emit=True)
        except Exception:
            pass
        self._privacy_btn.setText(
            f"Privacy: {'On' if self._privacy_mode else 'Off'}"
        )
        state = "On" if self._privacy_mode else "Off"
        app_signals.status_message.emit(f"Privacy / demo mode {state}")

    def _apply_verbose_log(self, enable: bool):
        """Toggle verbose (DEBUG) logging on or off.

        When enabled:
          - Lowers the 'shared' logger and all existing handlers to DEBUG.
          - Opens a dedicated gui_verbose log file named
            ofscraper_gui_verbose_<profile>_<timestamp>.log in the same
            logging folder so it is clearly distinguished from normal runs.
        When disabled:
          - Restores original handler levels.
          - Closes and removes the gui_verbose file handler.
        """
        import logging as _logging
        logger = _logging.getLogger("shared")

        _GUI_VERBOSE_TAG = "_gui_verbose_handler"

        if enable:
            logger.setLevel(_logging.DEBUG)
            # Identify Discord handler type so we can skip it — verbose mode must
            # not lower the Discord handler's level, because that would cause all
            # log messages to be posted to the webhook regardless of the user's
            # "Send updates to Discord" checkbox setting.
            try:
                from ofscraper.utils.logs.classes.handlers.discord import (
                    DiscordHandler as _DiscordHandler,
                )
            except Exception:
                _DiscordHandler = None
            for h in logger.handlers:
                if _DiscordHandler and isinstance(h, _DiscordHandler):
                    continue  # never lower the Discord handler for verbose mode
                if h.level > _logging.DEBUG or h.level == _logging.NOTSET:
                    h._gui_prev_level = h.level
                    h.setLevel(_logging.DEBUG)

            # Add a dedicated gui_verbose file handler if not already present
            if not any(getattr(h, _GUI_VERBOSE_TAG, False) for h in logger.handlers):
                try:
                    import datetime as _dt
                    import ofscraper.utils.paths.common as _paths
                    import ofscraper.utils.config.data as _data
                    import ofscraper.utils.logs.classes.classes as _log_class

                    log_folder = _paths.get_log_folder()
                    profile = _data.get_main_profile()
                    timestamp = _dt.datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
                    log_dir = log_folder / f"{profile}_{_dt.date.today().strftime('%Y-%m-%d')}"
                    log_dir.mkdir(parents=True, exist_ok=True)
                    log_path = log_dir / f"ofscraper_gui_verbose_{profile}_{timestamp}.log"

                    fmt = r" %(asctime)s:[%(module)s.%(funcName)s:%(lineno)d]  %(message)s"
                    stream = open(log_path, "a", encoding="utf-8")
                    fh = _logging.StreamHandler(stream)
                    fh.setLevel(_logging.DEBUG)
                    fh.setFormatter(_logging.Formatter(fmt, "%Y-%m-%d %H:%M:%S"))
                    setattr(fh, _GUI_VERBOSE_TAG, True)
                    fh._gui_verbose_stream = stream
                    logger.addHandler(fh)
                    log.info(f"[GUI] Verbose log file: {log_path}")
                except Exception as e:
                    log.debug(f"[GUI] Could not create verbose log file: {e}")
        else:
            logger.setLevel(_logging.INFO)
            try:
                from ofscraper.utils.logs.classes.handlers.discord import (
                    DiscordHandler as _DiscordHandler,
                )
            except Exception:
                _DiscordHandler = None
            for h in logger.handlers:
                if _DiscordHandler and isinstance(h, _DiscordHandler):
                    continue  # Discord handler level is managed separately; don't touch it
                prev = getattr(h, "_gui_prev_level", _logging.INFO)
                h.setLevel(prev)

            # Remove and close the gui_verbose file handler
            for h in logger.handlers[:]:
                if getattr(h, _GUI_VERBOSE_TAG, False):
                    logger.removeHandler(h)
                    try:
                        stream = getattr(h, "_gui_verbose_stream", None)
                        h.close()
                        if stream:
                            stream.close()
                    except Exception:
                        pass

        # Update button text if widget already exists
        try:
            self._verbose_btn.setText(f"Verbose Log: {'On' if enable else 'Off'}")
        except AttributeError:
            pass

    def _apply_theme_visuals(self, emit_signal=True):
        """Apply all visual elements for the current theme (self._is_dark).

        Called both at startup (emit_signal=False, to avoid premature signal
        before pages are connected) and after every toggle (emit_signal=True).
        """
        import html as _html

        app = QApplication.instance()
        apply_application_font()
        if self._is_dark:
            app.setStyleSheet(get_dark_theme_qss())
            self._theme_btn.setText("Light Mode")
            sidebar_bg = DARK_SIDEBAR_BG
            sep_color = DARK_SEP_COLOR
            logo_color = DARK_LOGO_COLOR
        else:
            app.setStyleSheet(get_light_theme_qss())
            self._theme_btn.setText("Dark Mode")
            sidebar_bg = LIGHT_SIDEBAR_BG
            sep_color = LIGHT_SEP_COLOR
            logo_color = LIGHT_LOGO_COLOR

        # Update hardcoded sidebar and separator colors
        self._nav_frame.setStyleSheet(f"QFrame {{ background-color: {sidebar_bg}; }}")
        self._nav_sep.setStyleSheet(f"color: {sep_color};")
        self._vsep.setStyleSheet(f"color: {sep_color};")

        # Update logo color
        _logo_lines = [
            r"        __                                    ",
            r"  ___  / _|___  ___ _ __ __ _ _ __   ___ _ __ ",
            r" / _ \| |_/ __|/ __| '__/ _` | '_ \ / _ \ '__|",
            r"| (_) |  _\__ \ (__| | | (_| | |_) |  __/ |   ",
            r" \___/|_|_|___/\___|_|  \__,_| .__/ \___|_|   ",
            r"       / /     \ \      / /  |_|\ \           ",
            r"      | |       | |    | |       | |          ",
            r"      | |   _   | |    | |   _   | |          ",
            r"      | |  (_)  | |    | |  (_)  | |          ",
            r"       \_\     /_/      \_\     /_/           ",
        ]
        # Keep ASCII logo at a fixed point size — GUI text scaling must not
        # stretch/squash monospace art (and QLabel may not shrink after grow).
        _logo_html = (
            f"<pre style='color:{logo_color}; font-family:Consolas,monospace; "
            f"font-size:{_LOGO_PT}pt; margin:0; line-height:1;'>"
            + "\n".join(_html.escape(l) for l in _logo_lines)
            + "</pre>"
        )
        try:
            self._title_label.setFont(QFont("Consolas", _LOGO_PT))
            self._title_label.setMinimumSize(0, 0)
            self._title_label.setText(_logo_html)
            self._title_label.adjustSize()
        except Exception:
            pass

        # Keep util buttons on the same chrome (scaled font-size).
        try:
            for btn in (
                getattr(self, "_theme_btn", None),
                getattr(self, "_verbose_btn", None),
                getattr(self, "_privacy_btn", None),
                getattr(self, "_ver_label", None),
            ):
                if btn is not None and callable(getattr(self, "_style_sidebar_util_btn", None)):
                    self._style_sidebar_util_btn(btn)
        except Exception:
            pass

        try:
            refresh_scaled_fonts(self)
        except Exception:
            pass
        # Re-assert fixed logo font after refresh_scaled_fonts / app font change.
        try:
            self._title_label.setFont(QFont("Consolas", _LOGO_PT))
        except Exception:
            pass

        if emit_signal:
            app_signals.theme_changed.emit(self._is_dark)

    def _nudge_gui_font_size(self, delta: int):
        sizes = allowed_sizes()
        try:
            i = sizes.index(get_gui_font_size())
        except ValueError:
            i = 1
        ni = max(0, min(len(sizes) - 1, i + int(delta)))
        self._set_gui_font_size(sizes[ni])

    def _reset_gui_font_size(self):
        """Restore the default GUI text size (13 px)."""
        self._set_gui_font_size(DESIGN_BASE)

    def _set_gui_font_size(self, size: int):
        """Persist and apply a global GUI text size."""
        try:
            from ofscraper.gui.utils.crash_diagnostics import (
                gui_action,
                is_heavy_background_active,
            )

            if is_heavy_background_active():
                gui_action("font_size_deferred", f"size={size}")
                app_signals.status_message.emit(
                    "Text size change waiting until model list / scrape finishes…"
                )
                self._pending_font_size = int(size)
                if getattr(self, "_font_defer_timer", None) is None:
                    t = QTimer(self)
                    t.setInterval(200)
                    t.timeout.connect(self._flush_pending_font_size)
                    self._font_defer_timer = t
                self._font_defer_timer.start()
                return
        except Exception:
            pass
        self._apply_gui_font_size(size)

    def _flush_pending_font_size(self):
        if not hasattr(self, "_pending_font_size") or self._pending_font_size is None:
            try:
                self._font_defer_timer.stop()
            except Exception:
                pass
            return
        try:
            from ofscraper.gui.utils.crash_diagnostics import is_heavy_background_active

            if is_heavy_background_active():
                return
        except Exception:
            pass
        size = self._pending_font_size
        self._pending_font_size = None
        try:
            self._font_defer_timer.stop()
        except Exception:
            pass
        self._apply_gui_font_size(size)

    def _apply_gui_font_size(self, size: int):
        size = set_gui_font_size(size, persist=True)
        self._apply_theme_visuals(emit_signal=True)
        try:
            app_signals.font_size_changed.emit(size)
        except Exception:
            pass
        app_signals.status_message.emit(f"GUI text size: {size} px")

    def _prompt_save_theme(self):
        """Ask the user if they want to save the current theme as the default."""
        from PyQt6.QtWidgets import QMessageBox

        theme_name = "Dark" if self._is_dark else "Light"
        reply = QMessageBox.question(
            self,
            "Save Theme Preference",
            f"Set {theme_name} Mode as your default theme?\n\n"
            f"The preference will be saved to gui_settings.json in your "
            f"ofscraper config directory.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                from ofscraper.gui.utils.gui_settings import (
                    load_gui_settings,
                    save_gui_settings,
                )
                settings = load_gui_settings()
                settings["theme"] = "dark" if self._is_dark else "light"
                if save_gui_settings(settings):
                    log.info(
                        f"[GUI] Default theme saved: {'dark' if self._is_dark else 'light'}"
                    )
            except Exception as e:
                log.warning(f"[GUI] Could not save theme preference: {e}")

    def _create_pages(self):
        from ofscraper.gui.pages.action_page import ActionPage
        from ofscraper.gui.pages.model_selector_page import ModelSelectorPage
        from ofscraper.gui.pages.area_selector_page import AreaSelectorPage
        from ofscraper.gui.pages.table_page import TablePage
        from ofscraper.gui.pages.help_page import HelpPage
        from ofscraper.gui.pages.plugins_page import PluginsPage
        from ofscraper.gui.pages.url_input_page import UrlInputPage
        from ofscraper.gui.dialogs.auth_dialog import AuthPage
        from ofscraper.gui.dialogs.config_dialog import ConfigPage
        from ofscraper.gui.dialogs.profile_dialog import ProfilePage
        from ofscraper.gui.dialogs.merge_dialog import MergePage
        from ofscraper.gui.dialogs.drm_dialog import DRMKeyPage

        # Scraper workflow pages (nested in a sub-stack)
        self.scraper_stack = QStackedWidget()

        self.action_page = ActionPage(manager=self.manager)
        self.model_page = ModelSelectorPage(manager=self.manager)
        self.area_page = AreaSelectorPage(manager=self.manager)
        self.url_input_page = UrlInputPage(manager=self.manager)
        self.table_page = TablePage(manager=self.manager)

        self.scraper_stack.addWidget(self.action_page)
        self.scraper_stack.addWidget(self.model_page)
        self.scraper_stack.addWidget(self.area_page)
        self.scraper_stack.addWidget(self.url_input_page)
        self.scraper_stack.addWidget(self.table_page)
        self.scraper_stack.currentChanged.connect(self._on_scraper_stack_changed)

        self._add_page("scraper", self.scraper_stack)
        self._add_page("auth", AuthPage(manager=self.manager))
        self._add_page("config", ConfigPage(manager=self.manager))
        self._add_page("drm", DRMKeyPage(manager=self.manager))
        self._add_page("profiles", ProfilePage(manager=self.manager))
        self._add_page("merge", MergePage(manager=self.manager))
        self.plugins_page = PluginsPage(manager=self.manager)
        self._add_page("plugins", self.plugins_page)
        self._add_page("help", HelpPage(manager=self.manager))

    def _add_page(self, page_id, widget):
        self._pages[page_id] = widget
        self.stack.addWidget(widget)

    def _remove_page(self, page_id: str) -> bool:
        """Remove a stack page and its sidebar nav button (used when unloading plugins)."""
        removed = False
        page_id = str(page_id or "")
        if not page_id:
            return False

        # If we are viewing the page being removed, leave it first.
        try:
            current = self.stack.currentWidget()
            page = self._pages.get(page_id)
            if page is not None and current is page:
                self._navigate("scraper")
        except Exception:
            pass

        btn = self._nav_buttons.pop(page_id, None)
        if btn is not None:
            try:
                self._nav_group.removeButton(btn)
            except Exception:
                pass
            try:
                layout = self._nav_frame.layout()
                if layout is not None:
                    layout.removeWidget(btn)
            except Exception:
                pass
            try:
                btn.setParent(None)
                btn.deleteLater()
            except Exception:
                pass
            removed = True

        widget = self._pages.pop(page_id, None)
        if widget is not None:
            try:
                self.stack.removeWidget(widget)
            except Exception:
                pass
            try:
                widget.setParent(None)
                widget.deleteLater()
            except Exception:
                pass
            removed = True
        return removed

    def _connect_signals(self):
        try:
            from ofscraper.gui.utils.host_callbacks import ensure_gui_host

            ensure_gui_host()
        except Exception:
            pass
        app_signals.navigate_to_page.connect(self._on_navigate_signal)
        app_signals.status_message.connect(self._on_status_message)
        app_signals.error_occurred.connect(self._on_error)
        app_signals.help_anchor_requested.connect(self._on_help_anchor_requested)

        # Scraper workflow navigation
        app_signals.action_selected.connect(self._on_action_selected)
        app_signals.models_selected.connect(self._on_models_selected)
        app_signals.areas_selected.connect(self._on_areas_selected)
        app_signals.data_loading_finished.connect(self._on_data_loaded)
        app_signals.data_replace.connect(self._on_data_replace)
        app_signals.manual_urls_confirmed.connect(self._on_manual_urls_confirmed)
        app_signals.scraping_finished.connect(self._on_scraping_finished_plugins)

    def _on_scraping_finished_plugins(self):
        """Dispatch on_scrape_complete to all loaded plugins when a scrape session ends."""
        try:
            from ofscraper.plugins.manager import plugin_manager
            plugin_manager.dispatch_event("on_scrape_complete", {})
            # If no plugin registered async work, unblock the daemon countdown now.
            plugin_manager.post_scrape_complete_dispatch()
        except Exception:
            try:
                from ofscraper.plugins.manager import plugin_manager as _pm_err
                _pm_err.signal_post_scrape_done()
            except Exception:
                pass

    def _navigate(self, page_id):
        if page_id in self._pages:
            self.stack.setCurrentWidget(self._pages[page_id])
            # Update nav button states
            if page_id in self._nav_buttons:
                self._nav_buttons[page_id].setChecked(True)
            if page_id == "plugins":
                try:
                    page = self._pages.get("plugins")
                    if page is not None and hasattr(page, "refresh"):
                        page.refresh()
                except Exception:
                    pass
            elif page_id == "config":
                # Always re-check when opening Configuration (paths may still be empty).
                self._schedule_missing_dependency_notice(force=True)

    @pyqtSlot(str)
    def _on_navigate_signal(self, page_id):
        self._navigate(page_id)

    @pyqtSlot(int)
    def _on_scraper_stack_changed(self, index):
        """When the user reaches Select Content Areas & Filters, gate model fetch."""
        try:
            if self.scraper_stack.widget(index) is self.area_page:
                self._prepare_area_page_entry()
        except Exception:
            pass

    def _prepare_area_page_entry(self):
        """Show missing-deps (safe exec dialog) if needed, then start model fetch."""
        def _after_deps():
            try:
                page = getattr(self, "area_page", None)
                if page is None or not hasattr(page, "start_pending_model_load"):
                    return
                on_scraper = self.stack.currentWidget() is self._pages.get("scraper")
                on_areas = self.scraper_stack.currentWidget() is page
                if on_scraper and on_areas:
                    page.start_pending_model_load()
                else:
                    page._pending_model_load = True
            except Exception as e:
                log.debug(f"[GUI] Areas model-load gate failed: {e}")

        # Slight defer so the Areas page paints, then blocking safe dialog if needed.
        QTimer.singleShot(
            0,
            lambda: self._maybe_show_missing_dependency_notice(on_finished=_after_deps),
        )

    def _schedule_missing_dependency_notice(self, *, force: bool = False):
        """Defer missing-deps popup slightly so the target page can paint first."""
        QTimer.singleShot(
            200,
            lambda: self._maybe_show_missing_dependency_notice(force=force),
        )

    @pyqtSlot(str)
    def _on_help_anchor_requested(self, anchor):
        """Navigate to Help page and scroll to requested anchor (single Help page)."""
        try:
            self._navigate("help")
            help_page = self._pages.get("help")
            if help_page and hasattr(help_page, "scroll_to_anchor"):
                # Defer until the Help page has rendered its markdown.
                QTimer.singleShot(
                    0, lambda: help_page.scroll_to_anchor(str(anchor))
                )
        except Exception:
            pass

    def _open_about_dialog(self):
        """Open or raise the single About window."""
        try:
            from ofscraper.gui.dialogs.about_dialog import show_about_dialog

            show_about_dialog(parent=self)
        except Exception as e:
            log.debug(f"About dialog failed: {e}")

    @pyqtSlot(str)
    def _on_status_message(self, message):
        self.status_bar.showMessage(message, 5000)

    @pyqtSlot(str, str)
    def _on_error(self, title, message):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(self, title, message)

    @pyqtSlot(set)
    def _on_action_selected(self, actions):
        """Move from action page to area/filter configuration page, or URL input page."""
        if actions == {"manual_url"}:
            self.scraper_stack.setCurrentWidget(self.url_input_page)
        else:
            self.scraper_stack.setCurrentWidget(self.area_page)

    @pyqtSlot(list)
    def _on_manual_urls_confirmed(self, urls):
        """URLs confirmed — navigate to table page and start scraping."""
        self.scraper_stack.setCurrentWidget(self.table_page)
        self.table_page.sidebar.setVisible(False)
        app_signals.status_message.emit(f"Scraping {len(urls)} post(s)...")

    @pyqtSlot(list)
    def _on_models_selected(self, models):
        """Move from model selection to table page."""
        self.scraper_stack.setCurrentWidget(self.table_page)
        self.table_page.sidebar.setVisible(True)
        self.table_page.toggle_sidebar_btn.setChecked(True)
        # Copy filter state from area page to table page sidebar
        self.area_page.copy_filter_state_to(self.table_page.sidebar)
        _check_modes = {"post_check", "msg_check", "paid_check", "story_check"}
        _current = getattr(self.area_page, "_current_actions", set()) or set()
        if bool(_current & _check_modes):
            app_signals.status_message.emit("Checking — fetching data, please wait...")
        else:
            app_signals.status_message.emit("Click Start Scraping to begin")

    @pyqtSlot(list)
    def _on_areas_selected(self, areas):
        """Areas selected — begin scraping."""
        app_signals.status_message.emit("Loading data...")

    @pyqtSlot(list)
    def _on_data_loaded(self, table_data):
        """Data loaded for a user — append to table."""
        self.table_page.append_data(table_data)

    def _on_data_replace(self, table_data):
        """DB fallback loaded — replace table with authoritative DB rows."""
        self.table_page.load_data(table_data)

    def go_to_scraper_step(self, step_index):
        """Navigate to a specific step in the scraper workflow."""
        if 0 <= step_index < self.scraper_stack.count():
            self.scraper_stack.setCurrentIndex(step_index)

    def _maybe_run_startup_dialogs(self):
        """First-run Welcome only (once).

        Missing FFmpeg / manual DRM keys are not shown at launch — they appear when
        the user opens Configuration or reaches Select Content Areas & Filters.
        """
        if getattr(self, "_startup_dialogs_attempted", False):
            return
        self._startup_dialogs_attempted = True
        self._first_run_welcome_attempted = True

        try:
            from ofscraper.gui.dialogs.welcome_dialog import (
                should_show_first_run_welcome,
                show_welcome_dialog,
            )

            if should_show_first_run_welcome():
                show_welcome_dialog(parent=self)
        except Exception as e:
            log.debug(f"[GUI] First-run welcome failed: {e}")

    def _maybe_show_first_run_welcome(self):
        """Backward-compatible alias; startup uses ``_maybe_run_startup_dialogs``."""
        self._maybe_run_startup_dialogs()

    def _maybe_check_for_updates(self):
        """Background PyPI check; prompt only when a newer release is available."""
        if getattr(self, "_update_check_started", False):
            return
        self._update_check_started = True
        try:
            from ofscraper.gui.utils.thread_worker import Worker
            from ofscraper.gui.utils.version_check import check_for_updates
            from PyQt6.QtCore import QThreadPool

            worker = Worker(check_for_updates)
            self._startup_update_worker = worker
            worker.signals.finished.connect(self._on_startup_update_check)
            worker.signals.error.connect(
                lambda _msg: None
            )  # silent on startup network errors
            QThreadPool.globalInstance().start(worker)
        except Exception as e:
            log.debug(f"[GUI] Startup update check failed to start: {e}")

    def _on_startup_update_check(self, result):
        try:
            from ofscraper.gui.utils.version_check import should_prompt_startup

            if not should_prompt_startup(result):
                return
        except Exception:
            return

        latest = getattr(result, "latest", None) or ""
        current = getattr(result, "current", "") or ""
        url = getattr(result, "project_url", None) or "https://pypi.org/project/ofscraper/"
        msg = getattr(result, "message", None) or (
            f"A newer OF-Scraper version is available: {latest} (you have {current})."
        )

        try:
            app_signals.status_message.emit(msg)
            app_signals.show_notification.emit("OF-Scraper update", msg)
        except Exception:
            pass

        from PyQt6.QtWidgets import QMessageBox
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl

        box = QMessageBox(self)
        box.setWindowTitle("Update available")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(msg)
        box.setInformativeText(
            "Open the PyPI project page to review the release, "
            "or dismiss this version so you are not prompted again until another release."
        )
        open_btn = box.addButton("Open PyPI", QMessageBox.ButtonRole.AcceptRole)
        dismiss_btn = box.addButton(
            "Dismiss this version", QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(open_btn)
        box.exec()

        clicked = box.clickedButton()
        if clicked is open_btn:
            QDesktopServices.openUrl(QUrl(url))
        elif clicked is dismiss_btn and latest:
            try:
                from ofscraper.gui.utils.version_check import dismiss_update_version

                dismiss_update_version(latest)
            except Exception:
                pass

    def _maybe_show_missing_dependency_notice(self, on_finished=None, force: bool = False):
        """Popup a single combined notice if FFmpeg or manual CDM key paths are missing.

        Shown when opening Configuration or Select Content Areas & Filters (not at launch).
        Normally once per session; Configuration uses ``force=True`` so an empty
        FFmpeg path still prompts every time you open that page.

        Uses blocking ``exec()`` on a simple label-based dialog (no QTextBrowser).
        """
        def _done():
            self._missing_deps_gate_cleared = True
            if not callable(on_finished):
                return

            def _safe_finish():
                try:
                    on_finished()
                except Exception as e:
                    log.debug(f"[GUI] missing-deps on_finished failed: {e}")

            QTimer.singleShot(0, _safe_finish)

        if getattr(self, "_missing_deps_notice_shown", False) and not force:
            _done()
            return

        try:
            from ofscraper.utils.config.config import read_config, reset_config_cache

            reset_config_cache()
            cfg = read_config(update=False) or {}
        except Exception:
            cfg = {}

        ffmpeg_path = None
        try:
            if isinstance(cfg.get("binary_options"), dict):
                ffmpeg_path = (cfg.get("binary_options") or {}).get("ffmpeg")
        except Exception:
            pass
        cdm_client = (
            (cfg.get("cdm_options") or {}).get("client-id")
            if isinstance(cfg.get("cdm_options"), dict)
            else None
        )
        cdm_private = (
            (cfg.get("cdm_options") or {}).get("private-key")
            if isinstance(cfg.get("cdm_options"), dict)
            else None
        )

        ffmpeg_raw = (str(ffmpeg_path).strip() if ffmpeg_path is not None else "")
        missing_ffmpeg = True
        if ffmpeg_raw:
            try:
                missing_ffmpeg = not Path(ffmpeg_raw).is_file()
            except Exception:
                missing_ffmpeg = True

        cdm_opts = cfg.get("cdm_options") if isinstance(cfg.get("cdm_options"), dict) else {}
        key_mode = str(cdm_opts.get("key-mode-default") or "manual").lower().strip() or "manual"
        client_raw = str(cdm_client).strip() if cdm_client is not None else ""
        priv_raw = str(cdm_private).strip() if cdm_private is not None else ""
        missing_manual_cdm = True
        if client_raw and priv_raw:
            try:
                missing_manual_cdm = not (Path(client_raw).is_file() and Path(priv_raw).is_file())
            except Exception:
                missing_manual_cdm = True

        if not (missing_ffmpeg or missing_manual_cdm):
            _done()
            return

        def open_ffmpeg():
            try:
                self._navigate("config")
                page = self._pages.get("config")
                if page and hasattr(page, "go_to_config_field"):
                    page.go_to_config_field("Download", "ffmpeg")
            except Exception:
                pass

        def open_cdm():
            try:
                self._navigate("config")
                page = self._pages.get("config")
                if page and hasattr(page, "go_to_config_field"):
                    field = "client-id" if not bool(client_raw) else "private-key"
                    page.go_to_config_field("CDM", field)
            except Exception:
                pass

        def open_drm():
            try:
                self._navigate("drm")
            except Exception:
                pass

        try:
            from ofscraper.gui.dialogs.missing_deps_dialog import MissingDepsDialog
            from ofscraper.gui.utils.window_registry import close_if_open

            try:
                close_if_open("missing_deps")
            except Exception:
                pass

            dlg = MissingDepsDialog(
                missing_ffmpeg=missing_ffmpeg,
                missing_manual_cdm=missing_manual_cdm,
                key_mode=key_mode,
                parent=self,
            )
            self._missing_deps_dlg = dlg
            self._missing_deps_notice_shown = True
            chosen = None
            try:
                dlg.exec()
                chosen = getattr(dlg, "chosen_action", None)
            finally:
                try:
                    dlg.hide()
                except Exception:
                    pass
                self._missing_deps_dlg = None

            # Navigate only after the modal is gone.
            if chosen == "ffmpeg":
                open_ffmpeg()
            elif chosen == "cdm":
                open_cdm()
            elif chosen == "drm":
                open_drm()

            _done()
        except Exception as e:
            log.warning(f"Missing deps dialog failed: {e}")
            # Last-resort visible prompt so a broken custom dialog never
            # silently skips the missing-FFmpeg/CDM warning.
            try:
                from PyQt6.QtWidgets import QMessageBox

                parts = []
                if missing_ffmpeg:
                    parts.append("• FFmpeg path is missing or invalid")
                if missing_manual_cdm:
                    parts.append("• Manual DRM key paths are missing or invalid")
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Icon.Warning)
                box.setWindowTitle("Missing configuration paths")
                box.setText(
                    "Required paths are missing from config.json:\n\n"
                    + "\n".join(parts)
                    + "\n\nOpen Configuration to set them."
                )
                cfg_btn = box.addButton(
                    "Open Configuration", QMessageBox.ButtonRole.AcceptRole
                )
                box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
                box.exec()
                if box.clickedButton() is cfg_btn:
                    open_ffmpeg() if missing_ffmpeg else open_cdm()
            except Exception as e2:
                log.warning(f"Missing deps fallback QMessageBox failed: {e2}")
            _done()
