"""Manage DBs > PostgreSQL: switch from user_data.db files to upstream's
optional PostgreSQL database, move the files in, and back out.

The work is done by gui/utils/postgres_setup.py and upstream's own
postgres_import / postgres_export commands (POSTGRESQL.md).
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QProcess, QProcessEnvironment, QThreadPool
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.styles import c
from ofscraper.gui.utils import postgres_setup as pg
from ofscraper.gui.utils.privacy_mode import MaskedPathFields, redact_log_message
from ofscraper.gui.utils.thread_worker import Worker
from ofscraper.gui.widgets.styled_button import StyledButton

log = logging.getLogger("shared")

ABOUT = (
    "<b>What is this?</b> OF-Scraper normally keeps each creator's records "
    "(what was found, downloaded and unlocked) in a small <i>user_data.db</i> "
    "file of its own. Optionally it can keep every creator in one PostgreSQL "
    "database server instead.<br><br>"
    "<b>Why use it:</b> one place for every creator to query and back up "
    "(pg_dump); several computers or containers can scrape into the same "
    "library at once; other tools (Stash, dashboards, SQL) can read the data "
    "directly.<br><br>"
    "<b>Things to know:</b> you need a PostgreSQL 15+ server you run yourself; "
    "it isn't faster for a single computer; there are no automatic backup "
    "copies (use pg_dump); every profile shares the one database; Merge "
    "Databases still only works on user_data.db files; the standalone .exe "
    "can't use it. Your user_data.db files are never changed, and you can "
    "switch back at any time. See Help for the full list."
)

SITES = (("Every site", None), ("OnlyFans", "onlyfans"), ("Fansly", "fansly"))


class PostgresPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = None
        self._job = None  # (kind, folder) of the running command
        self._previewed = None  # folder whose import preview said it can go in
        self._export_previewed = None  # (folder, site) likewise
        self._scraping = False
        self._worker = None
        self._loaded = False
        self._setup_ui()
        self._paths = MaskedPathFields(self.import_folder, self.export_folder)
        self._update_buttons()
        app_signals.scrape_started.connect(lambda: self._set_scraping(True))
        app_signals.scraping_finished.connect(lambda: self._set_scraping(False))
        app_signals.theme_changed.connect(
            lambda *_: self.refresh_status() if self._loaded else None
        )

    def showEvent(self, event):
        # the settings (profile folder, database address) are read when the
        # tab is first shown, not when the Manage DBs page is built
        if not self._loaded:
            self._loaded = True
            if not self._paths.value(self.import_folder):
                self._paths.set_value(self.import_folder, pg.default_data_folder())
            self._fill_fields()
            self.refresh_status()
        super().showEvent(event)

    # --- layout ------------------------------------------------------------------

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(12)

        about = QLabel(ABOUT)
        about.setWordWrap(True)
        about.setProperty("subheading", True)
        layout.addWidget(about)

        # status
        status_box = QGroupBox("Status")
        status_layout = QVBoxLayout(status_box)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        status_layout.addWidget(self.status_label)
        driver_row = QHBoxLayout()
        self.driver_label = QLabel()
        self.driver_label.setWordWrap(True)
        driver_row.addWidget(self.driver_label, 1)
        self.install_btn = StyledButton("Install driver")
        self.install_btn.setToolTip(f"Runs: {pg.install_driver_plan().manual}")
        self.install_btn.clicked.connect(self._on_install_driver)
        driver_row.addWidget(self.install_btn)
        status_layout.addLayout(driver_row)
        layout.addWidget(status_box)

        # connection
        conn_box = QGroupBox("1. Connection")
        form = QFormLayout(conn_box)
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("localhost, 192.168.1.10, db.example.lan")
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(pg.DEFAULT_PORT)
        self.database_input = QLineEdit()
        self.database_input.setPlaceholderText("ofscraper")
        self.user_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.show_password = QCheckBox("Show")
        self.show_password.toggled.connect(
            lambda on: self.password_input.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        pw_row = QHBoxLayout()
        pw_row.addWidget(self.password_input, 1)
        pw_row.addWidget(self.show_password)
        form.addRow("Host:", self.host_input)
        form.addRow("Port:", self.port_input)
        form.addRow("Database:", self.database_input)
        form.addRow("User:", self.user_input)
        form.addRow("Password:", pw_row)
        note = QLabel(
            "The login must be able to create tables in that database. The "
            "address is saved to its own file next to config.json, readable "
            "only by you, never to config.json itself."
        )
        note.setWordWrap(True)
        note.setProperty("subheading", True)
        form.addRow(note)
        btns = QHBoxLayout()
        self.test_btn = StyledButton("Test connection")
        self.test_btn.clicked.connect(self._on_test)
        self.save_btn = StyledButton("Save and use PostgreSQL", primary=True)
        self.save_btn.clicked.connect(self._on_save)
        self.sqlite_btn = StyledButton("Use user_data.db files again")
        self.sqlite_btn.clicked.connect(self._on_use_sqlite)
        btns.addWidget(self.test_btn)
        btns.addStretch()
        btns.addWidget(self.sqlite_btn)
        btns.addWidget(self.save_btn)
        form.addRow(btns)
        layout.addWidget(conn_box)

        # import
        import_box = QGroupBox("2. Bring your user_data.db files in")
        import_layout = QVBoxLayout(import_box)
        import_note = QLabel(
            "Turning PostgreSQL on doesn't move anything: until your files are "
            "brought in, every creator looks new and everything downloads again. "
            "Preview first; nothing is written until you press Import. It's all "
            "or nothing, your files aren't changed, and a creator PostgreSQL "
            "already has is refused. Two files for one creator? Merge them first."
        )
        import_note.setWordWrap(True)
        import_note.setProperty("subheading", True)
        import_layout.addWidget(import_note)
        row = QHBoxLayout()
        row.addWidget(QLabel("Folder:"))
        self.import_folder = QLineEdit()
        self.import_folder.setPlaceholderText("Folder searched for user_data.db files (your profile's .data)")
        self.import_folder.textChanged.connect(lambda *_: self._invalidate_preview())
        row.addWidget(self.import_folder, 1)
        browse = StyledButton("Browse")
        browse.clicked.connect(lambda: self._browse(self.import_folder))
        row.addWidget(browse)
        import_layout.addLayout(row)
        self.skip_bad = QCheckBox("Skip files that can't be brought in (and list them)")
        self.skip_bad.toggled.connect(lambda *_: self._invalidate_preview())
        import_layout.addWidget(self.skip_bad)
        row = QHBoxLayout()
        row.addStretch()
        self.preview_import_btn = StyledButton("Preview import")
        self.preview_import_btn.clicked.connect(lambda: self._on_import(apply=False))
        self.import_btn = StyledButton("Import", primary=True)
        self.import_btn.clicked.connect(lambda: self._on_import(apply=True))
        row.addWidget(self.preview_import_btn)
        row.addWidget(self.import_btn)
        import_layout.addLayout(row)
        layout.addWidget(import_box)

        # export
        export_box = QGroupBox("Going back: write PostgreSQL out to user_data.db files")
        export_layout = QVBoxLayout(export_box)
        export_note = QLabel(
            "Turning PostgreSQL off returns to your old files without anything "
            "scraped since. Export first to keep it: each creator gets "
            "<folder>/<creator id>/user_data.db. PostgreSQL is only read, and "
            "an existing file is never overwritten, so use an empty folder. "
            "Pick one site at a time when both have rows."
        )
        export_note.setWordWrap(True)
        export_note.setProperty("subheading", True)
        export_layout.addWidget(export_note)
        row = QHBoxLayout()
        row.addWidget(QLabel("Folder:"))
        self.export_folder = QLineEdit()
        self.export_folder.setPlaceholderText("An empty folder for the exported files")
        self.export_folder.textChanged.connect(lambda *_: self._invalidate_preview())
        row.addWidget(self.export_folder, 1)
        browse = StyledButton("Browse")
        browse.clicked.connect(lambda: self._browse(self.export_folder))
        row.addWidget(browse)
        export_layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Site:"))
        self.site_combo = QComboBox()
        for label, value in SITES:
            self.site_combo.addItem(label, value)
        self.site_combo.currentIndexChanged.connect(lambda *_: self._invalidate_preview())
        row.addWidget(self.site_combo)
        row.addStretch()
        self.preview_export_btn = StyledButton("Preview export")
        self.preview_export_btn.clicked.connect(lambda: self._on_export(apply=False))
        self.export_btn = StyledButton("Export", primary=True)
        self.export_btn.clicked.connect(lambda: self._on_export(apply=True))
        row.addWidget(self.preview_export_btn)
        row.addWidget(self.export_btn)
        export_layout.addLayout(row)
        layout.addWidget(export_box)

        # output
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output:"))
        out_row.addStretch()
        self.cancel_btn = StyledButton("Cancel", danger=True)
        self.cancel_btn.clicked.connect(self._on_cancel)
        out_row.addWidget(self.cancel_btn)
        layout.addLayout(out_row)
        self.output_text = QPlainTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMaximumBlockCount(2000)
        self.output_text.setMinimumHeight(180)
        self.output_text.setPlaceholderText("Test, preview, import and export output appears here...")
        layout.addWidget(self.output_text)

    # --- state -------------------------------------------------------------------

    def _fill_fields(self):
        parts = pg.parse_url(pg.saved_url() or pg.active_url())
        if not parts:
            return
        self.host_input.setText(parts["host"])
        self.port_input.setValue(int(parts["port"]))
        self.database_input.setText(parts["database"])
        self.user_input.setText(parts["user"])
        self.password_input.setText(parts["password"])

    def refresh_status(self):
        active, saved = pg.active_url(), pg.saved_url()
        if active:
            now = f"This window uses <b>PostgreSQL</b> at {pg.describe(active)}."
        else:
            now = "This window uses <b>user_data.db files</b> (SQLite), the default."
        if saved and saved != active:
            now += f"<br>Saved: PostgreSQL at {pg.describe(saved)}. <b>Restart the GUI</b> to use it."
        elif active and not saved:
            now += (
                "<br>The address isn't from this window's settings (for example "
                "docker-compose.yml or your own env file), so change it there."
            )
        elif not active and not saved:
            pass
        self.status_label.setText(now)
        if pg.driver_installed():
            self.driver_label.setText("PostgreSQL driver: installed.")
            self.driver_label.setStyleSheet("")
            self.install_btn.setVisible(False)
        else:
            self.driver_label.setText(pg.driver_missing_text())
            self.driver_label.setStyleSheet(f"color: {c('warning')};")
            self.install_btn.setVisible(not pg.standalone_build())
        self._update_buttons()

    def _set_scraping(self, on):
        self._scraping = bool(on)
        self._update_buttons()

    def _invalidate_preview(self):
        self._previewed = None
        self._export_previewed = None
        self._update_buttons()

    def _update_buttons(self):
        busy = self._process is not None or self._worker is not None
        driver = pg.driver_installed()
        for btn in (self.test_btn, self.save_btn, self.sqlite_btn, self.install_btn,
                    self.preview_import_btn, self.preview_export_btn):
            btn.setEnabled(not busy)
        self.test_btn.setEnabled(not busy and driver)
        self.preview_export_btn.setEnabled(not busy and driver and not self._scraping)
        self.preview_import_btn.setEnabled(not busy and not self._scraping)
        self.import_btn.setEnabled(
            not busy and driver and not self._scraping
            and self._previewed == self._import_key()
        )
        self.export_btn.setEnabled(
            not busy and driver and not self._scraping
            and self._export_previewed == self._export_key()
        )
        self.cancel_btn.setEnabled(self._process is not None)

    def _import_key(self):
        return (self._paths.value(self.import_folder), self.skip_bad.isChecked())

    def _export_key(self):
        return (self._paths.value(self.export_folder), self.site_combo.currentData())

    def _say(self, text):
        for line in str(text).splitlines() or [""]:
            self.output_text.appendPlainText(redact_log_message(pg.masked(line, self._url())))

    def _url(self):
        return pg.saved_url() or pg.active_url()

    def _browse(self, edit):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", self._paths.value(edit))
        if folder:
            self._paths.set_value(edit, folder)

    # --- connection --------------------------------------------------------------

    def _entered_url(self):
        try:
            return pg.build_url(
                self.host_input.text(),
                self.port_input.value(),
                self.database_input.text(),
                self.user_input.text(),
                self.password_input.text(),
            )
        except ValueError as e:
            QMessageBox.warning(self, "PostgreSQL", str(e))
            return None

    def _run_in_background(self, fn, done):
        worker = Worker(fn)

        def finished(result):
            self._worker = None
            self._update_buttons()
            done(result, None)

        def failed(message):
            self._worker = None
            self._update_buttons()
            done(None, message)

        worker.signals.finished.connect(finished)
        worker.signals.error.connect(failed)
        self._worker = worker
        self._update_buttons()
        QThreadPool.globalInstance().start(worker)

    def _on_test(self, *_, then=None):
        url = self._entered_url()
        if not url:
            return
        self._say(f"\nTesting {pg.describe(url)}...")

        def done(result, error):
            if error:
                self._say(f"Couldn't use it: {error}")
                if then is None:
                    QMessageBox.warning(self, "PostgreSQL", pg.masked(error, url))
                return
            self._say(result)
            if then:
                then(url)

        self._run_in_background(lambda: pg.test_connection(url), done)

    def _on_save(self):
        if not pg.driver_installed():
            QMessageBox.warning(self, "PostgreSQL", pg.driver_missing_text())
            return
        self._on_test(then=self._save_tested)

    def _save_tested(self, url):
        answer = QMessageBox.question(
            self,
            "Use PostgreSQL",
            "The connection works. Save it and use PostgreSQL from the next start?\n\n"
            "Until you bring your user_data.db files in (step 2), every creator "
            "will look new to the scraper and everything would download again. "
            "Import before your next scrape.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            for line in pg.save(url):
                self._say(line)
        except Exception as e:
            self._say(f"Couldn't save: {e}")
            QMessageBox.critical(self, "PostgreSQL", str(e))
            return
        log.info(f"[PostgreSQL] saved the address for {pg.describe(url)}")
        app_signals.config_updated.emit()
        self.refresh_status()
        self._say(
            "Saved. Now preview and import your files (step 2), then restart "
            "the GUI (both tabs) to start using PostgreSQL."
        )

    def _on_use_sqlite(self):
        answer = QMessageBox.question(
            self,
            "Use user_data.db files",
            "Stop using PostgreSQL from the next start?\n\n"
            "The scraper goes back to your user_data.db files as they were "
            "before the switch, without anything scraped since. To keep that, "
            "export first (below) and merge the exported files into yours.\n\n"
            "Nothing in PostgreSQL is deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for line in pg.remove():
            self._say(line)
        app_signals.config_updated.emit()
        self.refresh_status()
        self._say("Done. Restart the GUI (both tabs) to use the user_data.db files.")

    def _on_install_driver(self):
        if pg.standalone_build():
            return
        plan = pg.install_driver_plan()
        if plan.command is None:
            tool = {"pipx": "pipx", "uv": "uv"}.get(plan.method, "pip")
            self._say(
                f"\nThis ofscraper was installed with {plan.method}, but {tool} wasn't found."
                f"\nRun this in a terminal, then restart the GUI:\n  {plan.manual}"
            )
            return
        self._start("install", None, plan.command, url=None, cwd=plan.cwd)

    # --- import / export ---------------------------------------------------------

    def _confirm_idle(self, what):
        if self._scraping:
            QMessageBox.warning(self, "PostgreSQL", f"Wait for the scrape to finish before {what}.")
            return False
        return (
            QMessageBox.question(
                self,
                "PostgreSQL",
                f"Before {what}, make sure no scrape is running in either tab "
                "(OnlyFans or Fansly), including daemon mode.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )

    def _on_import(self, apply):
        folder = self._paths.value(self.import_folder)
        if not folder:
            QMessageBox.warning(self, "PostgreSQL", "Choose the folder with your user_data.db files.")
            return
        url = self._url()
        if apply:
            if not url:
                QMessageBox.warning(self, "PostgreSQL", "Save the connection (step 1) first.")
                return
            if not self._confirm_idle("importing"):
                return
        command = pg.import_command(folder, apply=apply, skip_bad=self.skip_bad.isChecked())
        self._start("import-apply" if apply else "import-preview", self._import_key(), command, url)

    def _on_export(self, apply):
        folder = self._paths.value(self.export_folder)
        if not folder:
            QMessageBox.warning(self, "PostgreSQL", "Choose an empty folder for the exported files.")
            return
        url = self._url()
        if not url:
            QMessageBox.warning(self, "PostgreSQL", "There is no PostgreSQL connection saved to export from.")
            return
        if apply and not self._confirm_idle("exporting"):
            return
        command = pg.export_command(folder, apply=apply, site=self.site_combo.currentData())
        self._start("export-apply" if apply else "export-preview", self._export_key(), command, url)

    def _start(self, kind, key, command, url, cwd=None):
        if self._process is not None:
            return
        proc = QProcess(self)
        if cwd:
            proc.setWorkingDirectory(cwd)
        env = QProcessEnvironment()
        for k, v in pg.command_environment(url).items():
            env.insert(k, v)
        proc.setProcessEnvironment(env)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.readyReadStandardOutput.connect(self._read)
        proc.finished.connect(self._finished)
        proc.errorOccurred.connect(self._process_error)
        self._process = proc
        self._job = (kind, key)
        self._output = []
        self._say(f"\n$ {pg.shown_command(command)}")
        self._update_buttons()
        proc.start(command[0], command[1:])

    def _read(self):
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", "replace")
        self._output.append(data)
        self._say(data.rstrip("\n"))

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart and self._process is not None:
            self._say("Couldn't start the command.")
            self._process = None
            self._job = None
            self._update_buttons()

    def _finished(self, code, _status=None):
        kind, key = self._job or (None, None)
        output = "".join(getattr(self, "_output", []))
        self._process = None
        self._job = None
        if kind == "import-preview":
            # upstream's preview ends with this when there are files to bring in
            self._previewed = key if "with --apply to bring" in output else None
            if self._previewed:
                self._say("Preview done: press Import to bring these in.")
        elif kind == "import-apply":
            self._previewed = None
            if code == 0:
                self._say("Import finished.")
        elif kind == "export-preview":
            self._export_previewed = key if code == 0 else None
            if self._export_previewed:
                self._say("Preview done: press Export to write the files.")
        elif kind == "export-apply":
            self._export_previewed = None
        elif kind == "install":
            self._say("Driver installed." if code == 0 else "The install didn't finish.")
            if code == 0:
                self._say("Restart the GUI to use it.")
        if code not in (0, None):
            self._say(f"(exit code {code})")
        self.refresh_status()

    def _on_cancel(self):
        if self._process is not None:
            self._say("Cancelling... (an import that was cut short keeps nothing)")
            self._process.kill()
