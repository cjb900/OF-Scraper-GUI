import logging
import os
import shutil
import subprocess
import sys

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.styles import c
from ofscraper.gui.widgets.styled_button import StyledButton

log = logging.getLogger("shared")

# Bundled script location: ofscraper/gui/scripts/drm_keydive.py
_BUNDLED_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "drm_keydive.py")
_BUNDLED_SCRIPT = os.path.normpath(_BUNDLED_SCRIPT)

_REQUIREMENTS_TEXT = """\
SYSTEM REQUIREMENTS
───────────────────
  OS:       Windows 10/11  OR  Debian-based Linux (Ubuntu 20.04+, KDE Neon, PikaOS)
            macOS is NOT supported.
  CPU:      x86-64 processor
  RAM:      8 GB minimum (16 GB recommended)
  Disk:     8 GB free space (SDK + emulator image + APKs)
  Internet: Required — downloads ~3 GB of tools on first run

  Hardware virtualization (VT-x / KVM) is strongly recommended.
  Without it the script falls back to software emulation which may
  take 45–90 minutes instead of 10–20 minutes.

REQUIRED PYTHON PACKAGES
────────────────────────
  pip install requests

  Only the 'requests' package needs to be installed manually.
  frida, frida-tools, and all other dependencies (Android SDK,
  JDK 17, Frida server, KeyDive, Kaltura APK) are downloaded
  and installed automatically by the script on first run.

OUTPUT FILES
────────────
  client_id.bin    — Widevine client identification blob
  private_key.pem  — Widevine device private key

  After successful extraction you will be offered the option to
  save these paths to config.json and set Key Mode to "manual".\
"""


class _ScriptRunner(QThread):
    """Runs drm_keydive.py in a subprocess and streams output line by line."""

    line_ready = pyqtSignal(str)
    finished = pyqtSignal(int)  # exit code

    def __init__(self, script_path: str, output_dir: str):
        super().__init__()
        self.script_path = script_path
        self.output_dir = output_dir

    def run(self):
        cmd = [sys.executable, self.script_path, "--out-dir", self.output_dir]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                cwd=os.path.dirname(self.script_path),
            )
            for line in proc.stdout:
                self.line_ready.emit(line.rstrip())
            proc.wait()
            self.finished.emit(proc.returncode)
        except Exception as e:
            self.line_ready.emit(f"ERROR launching script: {e}")
            self.finished.emit(1)


class DRMKeyPage(QWidget):
    """DRM Key Creation page — runs drm_keydive.py and optionally updates config.json."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._runner = None
        self._last_output_dir = None
        self._setup_ui()
        self._try_prefill_script()

    def _try_prefill_script(self):
        """Pre-fill the script path with the bundled script if it exists."""
        if os.path.isfile(_BUNDLED_SCRIPT):
            self.script_input.setText(_BUNDLED_SCRIPT)

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        # ── Header ────────────────────────────────────────────────────────────
        header = QLabel("DRM Key Creation")
        header.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        header.setProperty("heading", True)
        layout.addWidget(header)

        subtitle = QLabel(
            "Generate Widevine L3 keys using an Android emulator. "
            "Produces client_id.bin and private_key.pem for use with OF-Scraper. "
            "Docker is not supported for DRM key generation; use a normal host system instead."
        )
        subtitle.setProperty("subheading", True)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # ── Requirements box ──────────────────────────────────────────────────
        req_frame = QFrame()
        req_frame.setFrameShape(QFrame.Shape.StyledPanel)
        req_frame.setObjectName("reqFrame")
        req_layout = QVBoxLayout(req_frame)
        req_layout.setContentsMargins(16, 12, 16, 12)
        req_layout.setSpacing(4)

        req_title = QLabel("Requirements & Information")
        req_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        req_layout.addWidget(req_title)

        req_body = QLabel(_REQUIREMENTS_TEXT)
        req_body.setFont(QFont("Consolas", 9))
        req_body.setWordWrap(False)
        req_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        req_layout.addWidget(req_body)

        layout.addWidget(req_frame)

        layout.addSpacing(8)

        # ── Script path ───────────────────────────────────────────────────────
        script_row = QHBoxLayout()
        script_lbl = QLabel("Extraction Script:")
        script_lbl.setFixedWidth(140)
        script_row.addWidget(script_lbl)
        self.script_input = QLineEdit()
        self.script_input.setPlaceholderText("Path to drm_keydive.py ...")
        self.script_input.setClearButtonEnabled(True)
        self.script_input.setToolTip(
            "Full path to drm_keydive.py.\n"
            "The bundled copy is detected automatically if found."
        )
        script_row.addWidget(self.script_input)
        script_browse = StyledButton("Browse")
        script_browse.clicked.connect(self._browse_script)
        script_row.addWidget(script_browse)
        layout.addLayout(script_row)

        # ── Output directory ──────────────────────────────────────────────────
        out_row = QHBoxLayout()
        out_lbl = QLabel("Output Folder:")
        out_lbl.setFixedWidth(140)
        out_row.addWidget(out_lbl)
        self.output_input = QLineEdit()
        self.output_input.setPlaceholderText("Folder where keys will be saved (default: ~/.config/ofscraper/device)")
        self.output_input.setClearButtonEnabled(True)
        self.output_input.setToolTip(
            "Directory where client_id.bin and private_key.pem will be written.\n"
            "Leave blank to use the default: ~/.config/ofscraper/device"
        )
        out_row.addWidget(self.output_input)
        out_browse = StyledButton("Browse")
        out_browse.clicked.connect(self._browse_output)
        out_row.addWidget(out_browse)
        layout.addLayout(out_row)

        layout.addSpacing(8)

        # ── Warning ───────────────────────────────────────────────────────────
        self._warning_label = QLabel(
            "WARNING: First run downloads ~3 GB of tools and may take 45–90 min "
            "on systems without hardware virtualization (VT-x / KVM)."
        )
        self._warning_label.setStyleSheet(f"color: {c('warning')}; font-weight: bold;")
        self._warning_label.setWordWrap(True)
        layout.addWidget(self._warning_label)

        app_signals.theme_changed.connect(self._apply_theme)

        # ── Generate button ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.generate_btn = StyledButton("Generate Keys", primary=True)
        self.generate_btn.setFixedWidth(200)
        self.generate_btn.clicked.connect(self._on_generate)
        btn_row.addWidget(self.generate_btn)
        layout.addLayout(btn_row)

        # ── Live output log ───────────────────────────────────────────────────
        self.output_text = QPlainTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMaximumBlockCount(2000)
        self.output_text.setPlaceholderText("Script output will appear here...")
        self.output_text.setFont(QFont("Consolas", 9))
        self.output_text.setMinimumHeight(300)
        layout.addWidget(self.output_text)

    def _apply_theme(self, _is_dark=True):
        self._warning_label.setStyleSheet(f"color: {c('warning')}; font-weight: bold;")

    def _browse_script(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Extraction Script", "", "Python Scripts (*.py)"
        )
        if path:
            self.script_input.setText(path)

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_input.setText(folder)

    def _on_generate(self):
        script = self.script_input.text().strip()
        if not script:
            QMessageBox.warning(self, "Missing", "No extraction script path set.\n"
                                "The bundled script was not found — please browse to drm_keydive.py.")
            return
        if not os.path.isfile(script):
            QMessageBox.warning(self, "Not Found", f"Script not found:\n{script}")
            return

        # Use typed path or fall back to the script's own default
        output_dir = self.output_input.text().strip()
        if not output_dir:
            output_dir = os.path.normpath(os.path.expanduser("~/.config/ofscraper/device"))

        os.makedirs(output_dir, exist_ok=True)
        self._last_output_dir = output_dir

        self.output_text.clear()
        start_msg = f"Starting DRM key extraction...\nOutput directory: {output_dir}\n"
        self.output_text.appendPlainText(start_msg)
        for line in start_msg.rstrip().splitlines():
            try:
                log.info("[DRM] %s", line)
            except Exception:
                pass
        self.generate_btn.setEnabled(False)
        app_signals.status_message.emit("DRM key extraction in progress...")

        self._runner = _ScriptRunner(script, output_dir)
        self._runner.line_ready.connect(self._on_line)
        self._runner.finished.connect(self._on_finished)
        self._runner.start()

    def _on_line(self, line: str):
        self.output_text.appendPlainText(line)
        if line:
            try:
                log.info("[DRM] %s", line)
            except Exception:
                pass
        sb = self.output_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_finished(self, exit_code: int):
        self.generate_btn.setEnabled(True)
        if exit_code == 0:
            self.output_text.appendPlainText("\n✓ Key extraction completed successfully.")
            try:
                log.info("[DRM] Key extraction completed successfully")
            except Exception:
                pass
            app_signals.status_message.emit("DRM key extraction complete")
            self._offer_config_update()
            self._offer_cleanup()
        else:
            self.output_text.appendPlainText(f"\n✗ Script exited with code {exit_code}.")
            try:
                log.error("[DRM] Script exited with code %s", exit_code)
            except Exception:
                pass
            app_signals.status_message.emit("DRM key extraction failed")
            QMessageBox.critical(
                self,
                "Extraction Failed",
                f"The extraction script exited with code {exit_code}.\n"
                "Check the output log for details.",
            )

    def _offer_config_update(self):
        if not self._last_output_dir:
            return

        client_id = os.path.join(self._last_output_dir, "client_id.bin")
        private_key = os.path.join(self._last_output_dir, "private_key.pem")

        missing = [p for p in (client_id, private_key) if not os.path.isfile(p)]
        if missing:
            QMessageBox.warning(
                self,
                "Key Files Not Found",
                "Extraction reported success but the key files were not found:\n"
                + "\n".join(missing)
                + "\n\nConfig was not updated.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Update Configuration",
            "Keys were saved successfully!\n\n"
            f"  Client ID:   {client_id}\n"
            f"  Private Key: {private_key}\n\n"
            "Would you like to update config.json with these paths\n"
            "and set Key Mode to manual?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._update_config(client_id, private_key)
            app_signals.config_updated.emit()
            QMessageBox.information(
                self,
                "Config Updated",
                "config.json has been updated:\n"
                "  • key-mode-default → manual\n"
                f"  • client-id → {client_id}\n"
                f"  • private-key → {private_key}",
            )
            app_signals.status_message.emit("Config updated with DRM keys")
        except Exception as e:
            log.debug(f"Config update failed: {e}", exc_info=True)
            QMessageBox.critical(self, "Config Update Failed", f"Could not update config.json:\n{e}")

    def _offer_cleanup(self):
        """Ask the user if they want to remove the directories created during key extraction."""
        home = os.path.expanduser("~")
        avd_name = "widevine_avd"
        candidates = [
            (os.path.join(home, "widevine-sdk"),
             "Android SDK, JDK 17, and emulator binaries (~2–3 GB)"),
            (os.path.join(home, "widevine-work"),
             "KeyDive venv, Frida server, Kaltura APK, and work files"),
            (os.path.join(home, ".android", "avd", f"{avd_name}.avd"),
             "Android emulator image (~1–2 GB)"),
            (os.path.join(home, ".android", "avd", f"{avd_name}.ini"),
             "AVD registration file"),
        ]

        present = [(path, desc) for path, desc in candidates if os.path.exists(path)]
        if not present:
            return

        lines = "\n".join(f"  • {path}\n    ({desc})" for path, desc in present)
        reply = QMessageBox.question(
            self,
            "Remove Extracted Files?",
            "The following directories/files were created during DRM key extraction.\n"
            "Would you like to remove them to free up disk space?\n\n"
            + lines +
            "\n\nOnly click Yes if you no longer need these files.\n"
            "If you plan to generate keys again in the future, clicking No will\n"
            "allow the next run to skip downloading everything again.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        errors = []
        for path, _ in present:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except Exception as e:
                errors.append(f"{path}: {e}")

        if errors:
            QMessageBox.warning(
                self,
                "Cleanup Incomplete",
                "Some items could not be removed:\n\n" + "\n".join(errors),
            )
        else:
            QMessageBox.information(
                self,
                "Cleanup Complete",
                "All selected files and directories have been removed.",
            )

    def _update_config(self, client_id: str, private_key: str):
        from ofscraper.utils.config.file import open_config, write_config
        import ofscraper.utils.config.config as config_module

        config = open_config()
        cdm = config.setdefault("cdm_options", {})
        cdm["key-mode-default"] = "manual"
        cdm["client-id"] = client_id
        cdm["private-key"] = private_key
        write_config(config)
        # Clear the module-level cache so the next read_config() call re-reads the file
        config_module.config = None
