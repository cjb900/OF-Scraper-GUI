import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSlot, QTimer
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
    c,
    DARK_SIDEBAR_BG,
    LIGHT_SIDEBAR_BG,
    DARK_SEP_COLOR,
    LIGHT_SEP_COLOR,
    DARK_LOGO_COLOR,
    LIGHT_LOGO_COLOR,
)
from ofscraper.gui.utils.workflow import GUIWorkflow
from ofscraper.gui.widgets.styled_button import NavButton

log = logging.getLogger("shared")


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

        # Load saved theme preference (dark by default)
        try:
            from ofscraper.gui.utils.gui_settings import load_gui_settings
            _saved = load_gui_settings()
            self._is_dark = _saved.get("theme", "dark") == "dark"
            self._verbose_log = bool(_saved.get("verbose_log", False))
        except Exception:
            self._is_dark = True
            self._verbose_log = False
        set_theme(self._is_dark)
        if self._verbose_log:
            self._apply_verbose_log(True)

        # Initialize the workflow runner that bridges GUI → scraper backend
        self.workflow = GUIWorkflow(manager)

        self._setup_ui()
        # _setup_ui hardcodes dark visuals; fix up if light mode is preferred
        if not self._is_dark:
            self._apply_theme_visuals(emit_signal=False)
        # Sync verbose button label to loaded preference
        if self._verbose_log:
            self._verbose_btn.setText("Verbose Log: On")
        self._connect_signals()

        # Load custom plugins and let them patch the UI if desired
        from ofscraper.plugins.manager import plugin_manager
        plugin_manager.discover_and_load()
        plugin_manager.dispatch_event("on_ui_setup", self)

        self._navigate("scraper")
        # After the window is created and painted, show missing dependency notices once.
        QTimer.singleShot(250, self._maybe_show_missing_dependency_notice)
        # Optional: if CLI args fully specify a scrape run, auto-start in GUI mode.
        QTimer.singleShot(350, self._maybe_autostart_from_cli_args)

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

        # Require usernames and areas to auto-start; action defaults to 'download'.
        # Check both 'actions' (Click dest) and legacy 'action' attribute.
        raw_actions = (
            getattr(args, "actions", None) or getattr(args, "action", None) or []
        )
        raw_users = getattr(args, "usernames", None) or []
        raw_posts = getattr(args, "posts", None) or []
        raw_da = getattr(args, "download_area", None) or []
        raw_la = getattr(args, "like_area", None) or []

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

        actions = {a.strip().lower() for a in _flatten_strs(raw_actions) if str(a).strip()}
        usernames = {u.strip().lower() for u in _flatten_strs(raw_users) if str(u).strip()}
        has_download_areas = bool(_flatten_strs(raw_posts) or _flatten_strs(raw_da))
        has_like_areas = bool(_flatten_strs(raw_la))
        has_areas = has_download_areas or has_like_areas

        # No usernames or areas → nothing to auto-start
        if not usernames or not has_areas:
            return

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
        )

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

        # Load models in the background, then auto-select, then start scraping.
        try:
            from ofscraper.gui.utils.thread_worker import Worker
            from PyQt6.QtCore import QThreadPool, QTimer as _QT
        except Exception:
            return

        if not (self.manager and getattr(self.manager, "model_manager", None)):
            return

        def _fetch_models():
            self.manager.model_manager.all_subs_retriver()
            return getattr(self.manager.model_manager, "all_subs_obj", None) or []

        def _on_models(models):
            try:
                models = list(models or [])
                if not models:
                    return
                # Apply excluded usernames from CLI args (if any)
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
                    # Fall back to normal flow if no matches.
                    log.warning("[GUI] Auto-start: no matching models found for usernames")
                    return

                # Seed action selection into the GUI workflow (without triggering the
                # AreaSelectorPage model loader twice).
                try:
                    app_signals.action_selected.emit(set(actions))
                except Exception:
                    pass

                app_signals.models_selected.emit(selected_models)

                # After the table page is shown, start scraping automatically.
                def _start():
                    try:
                        self.table_page._on_start_scraping()
                    except Exception:
                        pass

                _QT.singleShot(0, _start)
            except Exception:
                return

        worker = Worker(_fetch_models)
        worker.signals.finished.connect(_on_models)
        try:
            QThreadPool.globalInstance().start(worker)
        except Exception:
            # If the threadpool isn't available, do nothing (normal GUI flow remains).
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
        _logo_html = "<pre style='color:#89b4fa; font-family:Consolas,monospace; font-size:5pt; margin:0;'>" + "\n".join(_html.escape(l) for l in _logo_lines) + "</pre>"
        title_label = QLabel(_logo_html)
        title_label.setTextFormat(Qt.TextFormat.RichText)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("padding: 4px 0 12px 0;")
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
            ("scraper", "Scraper"),
            ("auth", "Authentication"),
            ("config", "Configuration"),
            ("drm", "DRM Key Creation"),
            ("profiles", "Profiles"),
            ("merge", "Merge DBs"),
            ("help", "Help / README"),
        ]

        for page_id, label in nav_items:
            btn = NavButton(label)
            self._nav_group.addButton(btn)
            self._nav_buttons[page_id] = btn
            nav_layout.addWidget(btn)
            btn.clicked.connect(lambda checked, pid=page_id: self._navigate(pid))

        nav_layout.addStretch()

        # Theme toggle button
        self._theme_btn = QPushButton("Light Mode")
        self._theme_btn.setFixedHeight(28)
        self._theme_btn.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 2px 8px; }"
        )
        self._theme_btn.clicked.connect(self._toggle_theme)
        nav_layout.addWidget(self._theme_btn)

        # Verbose log toggle button
        self._verbose_btn = QPushButton("Verbose Log: Off")
        self._verbose_btn.setFixedHeight(28)
        self._verbose_btn.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 2px 8px; }"
        )
        self._verbose_btn.clicked.connect(self._toggle_verbose_log)
        nav_layout.addWidget(self._verbose_btn)

        nav_layout.addSpacing(4)

        # Version label at bottom of nav
        try:
            from ofscraper.__version__ import __version__
            ver_label = QLabel(f"v{__version__}")
        except Exception:
            ver_label = QLabel("v3.12.9")
        ver_label.setProperty("muted", True)
        ver_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        """Switch between dark and light themes, then offer to save as default."""
        self._is_dark = not self._is_dark
        set_theme(self._is_dark)
        self._apply_theme_visuals()
        self._prompt_save_theme()

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
            for h in logger.handlers:
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
            for h in logger.handlers:
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
        _logo_html = (
            f"<pre style='color:{logo_color}; font-family:Consolas,monospace; "
            f"font-size:5pt; margin:0;'>"
            + "\n".join(_html.escape(l) for l in _logo_lines)
            + "</pre>"
        )
        self._title_label.setText(_logo_html)

        if emit_signal:
            app_signals.theme_changed.emit(self._is_dark)

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

        self._add_page("scraper", self.scraper_stack)
        self._add_page("auth", AuthPage(manager=self.manager))
        self._add_page("config", ConfigPage(manager=self.manager))
        self._add_page("drm", DRMKeyPage(manager=self.manager))
        self._add_page("profiles", ProfilePage(manager=self.manager))
        self._add_page("merge", MergePage(manager=self.manager))
        self._add_page("help", HelpPage(manager=self.manager))

    def _add_page(self, page_id, widget):
        self._pages[page_id] = widget
        self.stack.addWidget(widget)

    def _connect_signals(self):
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

    def _navigate(self, page_id):
        if page_id in self._pages:
            self.stack.setCurrentWidget(self._pages[page_id])
            # Update nav button states
            if page_id in self._nav_buttons:
                self._nav_buttons[page_id].setChecked(True)

    @pyqtSlot(str)
    def _on_navigate_signal(self, page_id):
        self._navigate(page_id)

    @pyqtSlot(str)
    def _on_help_anchor_requested(self, anchor):
        """Navigate to Help page and scroll to requested anchor."""
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

    def _maybe_show_missing_dependency_notice(self):
        """Popup a single combined notice if FFmpeg or manual CDM key paths are missing."""
        # Ensure we only show once per session
        if getattr(self, "_missing_deps_notice_shown", False):
            return
        self._missing_deps_notice_shown = True

        try:
            from ofscraper.utils.config.config import read_config

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

        # Missing/invalid FFmpeg path: show notice if empty OR points to a non-file.
        ffmpeg_raw = (str(ffmpeg_path).strip() if ffmpeg_path is not None else "")
        missing_ffmpeg = True
        if ffmpeg_raw:
            try:
                p = Path(ffmpeg_raw)
                missing_ffmpeg = not p.is_file()
            except Exception:
                missing_ffmpeg = True
        # CDM key check: warn whenever manual key files are not configured/valid,
        # regardless of the current key mode.  Users on cdrm/cdrm2/keydb should
        # still be prompted to set up manual keys as a fallback.
        cdm_opts = cfg.get("cdm_options") if isinstance(cfg.get("cdm_options"), dict) else {}
        key_mode = str(cdm_opts.get("key-mode-default") or "cdrm").lower().strip() or "cdrm"
        client_raw = str(cdm_client).strip() if cdm_client is not None else ""
        priv_raw = str(cdm_private).strip() if cdm_private is not None else ""
        missing_manual_cdm = True
        if client_raw and priv_raw:
            try:
                missing_manual_cdm = not (Path(client_raw).is_file() and Path(priv_raw).is_file())
            except Exception:
                missing_manual_cdm = True

        if not (missing_ffmpeg or missing_manual_cdm):
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
                    # Focus first missing field; prefer client-id
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

            dlg = MissingDepsDialog(
                missing_ffmpeg=missing_ffmpeg,
                missing_manual_cdm=missing_manual_cdm,
                key_mode=key_mode,
                on_open_ffmpeg=open_ffmpeg,
                on_open_cdm=open_cdm,
                on_open_drm=open_drm,
                parent=self,
            )
            dlg.exec()
        except Exception as e:
            log.debug(f"Missing deps dialog failed: {e}")
