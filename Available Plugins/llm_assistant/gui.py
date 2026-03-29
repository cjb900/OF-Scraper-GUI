"""
gui.py — Widgets for the LLM Assistant plugin.

Classes:
  ModelSelectDialog   — first-run model picker (shown like missing-deps popup)
  DepsInstallDialog   — installs torch + transformers via pip/pipx/UV
  ModelDownloadDialog — downloads and loads the chosen LLM with progress
  AssistantCommandBar — compact single-row bar injected into action/area pages
  LLMAssistantTab     — full-page chat panel in the main sidebar stack
"""

import html
import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QTextEdit,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger("ofscraper_plugin.llm_assistant.gui")

_SCRAPE_INTENT_RE = re.compile(
    r"\b(scrape|download|start|go|run|fetch|get)\b", re.IGNORECASE
)

# Matches "from <username>" or "for <username>" in user text
_USERNAME_RE = re.compile(
    r"\b(?:from|for)\s+@?([\w][\w.\-]*)\b", re.IGNORECASE
)

# Words that look like a username after "from/for" but are not
_USERNAME_STOPWORDS = frozenset({
    "all", "any", "the", "a", "an", "me", "my", "you", "your",
    "everyone", "everyone", "us", "them",
})

# Area keywords that can appear in natural-language commands
_AREA_KEYWORDS: dict[str, str] = {
    "purchased": "Purchased", "purchase": "Purchased",
    "timeline": "Timeline", "post": "Timeline", "posts": "Timeline",
    "messages": "Messages", "message": "Messages",
    "dm": "Messages", "dms": "Messages", "chat": "Messages",
    "pinned": "Pinned",
    "archived": "Archived", "archive": "Archived",
    "stories": "Stories", "story": "Stories",
    "highlights": "Highlights", "highlight": "Highlights",
    "profile": "Profile",
    "streams": "Streams", "stream": "Streams", "live": "Streams",
}


def _ensure_start_scraping(tool_calls: list, user_text: str) -> list:
    """
    Safety net: if the user clearly asked to start scraping but the LLM
    forgot set_action / set_usernames / set_areas / start_scraping,
    inject them automatically using simple text parsing.

    - Always ensures set_action:download comes first.
    - Extracts username from "from/for NAME" if LLM omitted set_usernames.
    - Extracts area keywords (purchased, timeline, …) if LLM omitted set_areas.
    - Only fires when other tool calls are present (so pure navigation
      like 'go to settings' doesn't trigger a scrape).
    """
    if not tool_calls:
        return tool_calls
    if not _SCRAPE_INTENT_RE.search(user_text):
        return tool_calls

    result = list(tool_calls)

    # ── 1. Ensure set_action:download is first ──────────────────────────
    has_action = any(tc.get("name") == "set_action" for tc in result)
    if not has_action:
        result.insert(0, {"name": "set_action", "args": {"action": "download"}})

    # ── 2. Inject set_usernames if LLM omitted it ───────────────────────
    has_usernames = any(tc.get("name") == "set_usernames" for tc in result)
    if not has_usernames:
        m = _USERNAME_RE.search(user_text)
        if m:
            raw = m.group(1).strip().lower()
            if raw not in _USERNAME_STOPWORDS:
                usernames = ["ALL"] if raw == "all" else [raw]
                # Insert right after set_action
                insert_idx = next(
                    (i + 1 for i, tc in enumerate(result)
                     if tc.get("name") == "set_action"),
                    1,
                )
                result.insert(insert_idx, {
                    "name": "set_usernames",
                    "args": {"usernames": usernames},
                })
                log.debug("_ensure_start_scraping: injected set_usernames(%s)", usernames)

    # ── 3. Inject set_areas if LLM omitted it ───────────────────────────
    has_areas = any(tc.get("name") == "set_areas" for tc in result)
    if not has_areas:
        found: set[str] = set()
        for word in re.findall(r"\b\w+\b", user_text.lower()):
            if word in _AREA_KEYWORDS:
                found.add(_AREA_KEYWORDS[word])
        if found:
            # Insert before start_scraping (or at end)
            insert_idx = next(
                (i for i, tc in enumerate(result)
                 if tc.get("name") == "start_scraping"),
                len(result),
            )
            result.insert(insert_idx, {
                "name": "set_areas",
                "args": {"areas": list(found)},
            })
            log.debug("_ensure_start_scraping: injected set_areas(%s)", found)

    # ── 4. Ensure start_scraping is last ────────────────────────────────
    has_start = any(tc.get("name") == "start_scraping" for tc in result)
    if not has_start:
        result.append({"name": "start_scraping", "args": {}})

    return result


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _check_missing_deps() -> list[str]:
    """Return names of packages that cannot be imported."""
    missing = []
    try:
        import llama_cpp  # noqa: F401
    except ImportError:
        missing.append("llama-cpp-python")
    try:
        import huggingface_hub  # noqa: F401
    except ImportError:
        missing.append("huggingface-hub")
    return missing


def _detect_installer() -> tuple[str, list[str]]:
    """
    Inspect sys.executable to decide which package manager installed ofscraper.

    Returns (installer_name, base_install_command_list).

    Priority:
      1. pipx  — exe lives inside pipx/venvs/
      2. UV    — exe lives inside uv/tools/ (Windows: AppData/uv, Linux: ~/.local/share/uv)
      3. pip   — fallback: sys.executable -m pip install
    """
    exe = str(Path(sys.executable)).replace("\\", "/").lower()

    # pipx: typically ~/.local/pipx/venvs/ofscraper/ or %USERPROFILE%\.local\pipx\
    if "pipx/venvs" in exe:
        pipx = shutil.which("pipx") or "pipx"
        return "pipx", [pipx, "inject", "ofscraper"]

    # UV tool: ~/.local/share/uv/tools/ or %APPDATA%\uv\tools\
    uv = shutil.which("uv")
    if uv:
        uv_markers = ["uv/tools", "uv\\tools", "/uv/data/tools"]
        if any(m in exe for m in uv_markers):
            return "uv", [uv, "tool", "inject", "ofscraper"]

    # Default: pip in the current interpreter's environment
    return "pip", [sys.executable, "-m", "pip", "install"]

_MODELS = [
    {
        "id":       "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "filename": "qwen2.5-0.5b-instruct-q8_0.gguf",
        "display":  "Qwen2.5 0.5B  Q8_0  (~530 MB RAM) — fastest",
        "desc":     "Fast on CPU. Good for simple commands. Downloads ~530 MB.",
    },
    {
        "id":       "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "display":  "Qwen2.5 1.5B  Q4_K_M  (~1.1 GB RAM) — recommended",
        "desc":     "Recommended. Better accuracy, still fast on CPU. Downloads ~1.1 GB.",
    },
    {
        "id":       "Qwen/Qwen2.5-3B-Instruct-GGUF",
        "filename": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "display":  "Qwen2.5 3B  Q4_K_M  (~2.0 GB RAM) — best quality",
        "desc":     "Most accurate. Needs ~2+ GB free RAM. Downloads ~2.0 GB.",
    },
]


# ---------------------------------------------------------------------------
# Background threads
# ---------------------------------------------------------------------------

class _InstallThread(QThread):
    """Runs a pip/pipx/uv install command and streams stdout line-by-line."""
    output = pyqtSignal(str)
    done   = pyqtSignal(bool, str)   # success, error_message

    def __init__(self, cmd: list[str]):
        super().__init__()
        self._cmd = cmd

    def run(self):
        try:
            proc = subprocess.Popen(
                self._cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in proc.stdout:
                self.output.emit(line.rstrip())
            proc.wait()
            if proc.returncode == 0:
                self.done.emit(True, "")
            else:
                self.done.emit(False, f"Process exited with code {proc.returncode}")
        except Exception as e:
            self.done.emit(False, str(e))


_WELCOME_HTML = """
<p><b style="font-size:14px;">🤖 LLM Assistant</b></p>
<p>Type plain-English commands to control the scraper.<br>
The assistant runs entirely <b>offline</b> using a local embedded AI model.</p>
<p><b>Example commands:</b></p>
<ul>
  <li><i>"Scrape all media from &lt;username&gt;"</i></li>
  <li><i>"Download only free images from ALL users posted this year"</i></li>
  <li><i>"Enable daemon mode every 2 hours and scan timeline and messages"</i></li>
  <li><i>"Reset settings, target &lt;username&gt;, then start scraping"</i></li>
  <li><i>"What areas are currently selected?"</i></li>
</ul>
<p style="color:gray;">Click <b>Load Model</b> to initialise the AI engine.<br>
The first run will download the model (~1–6 GB depending on size).</p>
"""


# ---------------------------------------------------------------------------
# Dependency install dialog
# ---------------------------------------------------------------------------

class DepsInstallDialog(QDialog):
    """
    Shown when torch / transformers are not installed.
    Detects whether ofscraper was installed via pip, pipx, or UV and runs
    the correct inject/install command, streaming live output.
    """

    def __init__(self, missing_packages: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM Assistant — Install Dependencies")
        self.setMinimumSize(560, 420)
        self.setModal(True)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint
        )

        self._success       = False
        self._install_thread = None
        installer_name, base_cmd = _detect_installer()
        self._cmd = base_cmd + missing_packages

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(20, 20, 20, 20)

        title = QLabel("📦  Missing AI Dependencies")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        root.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        pkgs_str = " + ".join(f"<b>{p}</b>" for p in missing_packages)
        info = QLabel(
            f"The LLM Assistant requires {pkgs_str} which "
            f"{'are' if len(missing_packages) > 1 else 'is'} not currently installed.<br><br>"
            f"Detected installer: <b>{installer_name}</b><br>"
            f"Install command: <code>{html.escape(' '.join(self._cmd))}</code>"
        )
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(info)

        warn = QLabel(
            "⚠  llama-cpp-python includes pre-built binaries (~100 MB). "
            "huggingface-hub is small (~2 MB). A stable internet connection is recommended."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet("color: #f9e2af; font-size: 11px;")
        root.addWidget(warn)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep2)

        log_lbl = QLabel("Install log:")
        log_lbl.setStyleSheet("font-size: 10px; color: gray;")
        root.addWidget(log_lbl)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Courier New", 9))
        self._log.setStyleSheet(
            "QTextEdit { background: #1e1e2e; color: #cdd6f4; "
            "border: 1px solid #45475a; border-radius: 4px; }"
        )
        self._log.setMinimumHeight(130)
        root.addWidget(self._log, stretch=1)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        self._bar.setTextVisible(False)
        self._bar.setVisible(False)
        root.addWidget(self._bar)

        btn_row = QHBoxLayout()
        self._install_btn = QPushButton("Install Now")
        self._install_btn.setFixedHeight(32)
        self._install_btn.clicked.connect(self._start_install)
        btn_row.addWidget(self._install_btn)

        self._cancel_btn = QPushButton("Skip / Cancel")
        self._cancel_btn.setFixedHeight(32)
        self._cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel_btn)
        root.addLayout(btn_row)

    # ------------------------------------------------------------------

    def _start_install(self):
        self._install_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._bar.setVisible(True)
        self._log.clear()
        self._log.append(f"$ {' '.join(self._cmd)}\n")

        self._install_thread = _InstallThread(self._cmd)
        self._install_thread.output.connect(self._on_output)
        self._install_thread.done.connect(self._on_done)
        self._install_thread.start()

    def _on_output(self, line: str):
        self._log.append(line)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_done(self, success: bool, err: str):
        self._bar.setVisible(False)
        self._success = success
        # Re-enable close button
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowCloseButtonHint
        )
        self.show()

        if success:
            self._log.append("\n✅ Installation complete! Continuing…")
            self._cancel_btn.setText("Continue →")
            self._cancel_btn.setEnabled(True)
            self._cancel_btn.clicked.disconnect()
            self._cancel_btn.clicked.connect(self.accept)
            # Auto-proceed after 2 s so the user sees the success message
            # but doesn't need to manually click Continue.
            QTimer.singleShot(2000, self.accept)
        else:
            self._log.append(f"\n❌ Installation failed: {err}")
            self._log.append(
                "\nYou can install manually and then reload OF-Scraper:\n"
                "  pipx inject ofscraper llama-cpp-python huggingface-hub\n"
                "  (or: pip install llama-cpp-python huggingface-hub)"
            )
            self._install_btn.setText("Retry")
            self._install_btn.setEnabled(True)
            self._cancel_btn.setText("Close")
            self._cancel_btn.setEnabled(True)

    def was_successful(self) -> bool:
        return self._success


# ---------------------------------------------------------------------------
# LLM load / inference threads
# ---------------------------------------------------------------------------

class _LoadThread(QThread):
    status = pyqtSignal(str)
    done   = pyqtSignal()
    error  = pyqtSignal(str)

    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    def run(self):
        try:
            self.engine.load(progress_callback=lambda m: self.status.emit(m))
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))


class _InferenceThread(QThread):
    status  = pyqtSignal(str)
    partial = pyqtSignal(str)   # live token stream
    result  = pyqtSignal(str)
    error   = pyqtSignal(str)

    def __init__(self, engine, gui_state, user_message):
        super().__init__()
        self.engine       = engine
        self.gui_state    = gui_state
        self.user_message = user_message

    def run(self):
        try:
            self.status.emit("Thinking…")
            text = self.engine.generate(
                self.gui_state,
                self.user_message,
                stream_callback=lambda t: self.partial.emit(t),
            )
            self.result.emit(text)
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Model selection dialog (first-run)
# ---------------------------------------------------------------------------

class ModelSelectDialog(QDialog):
    """
    Shown the first time the plugin is enabled so the user can choose
    which Qwen model to download.  Mirrors the style of the missing-deps
    dialog used by other plugins.
    """

    def __init__(self, current_model_id: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM Assistant — Choose AI Model")
        self.setMinimumWidth(500)
        self.setModal(True)

        default = next(
            (m for m in _MODELS if m["id"] == current_model_id),
            _MODELS[1],  # default to 1.5B recommended
        )
        self.selected_model_id       = default["id"]
        self.selected_model_filename = default["filename"]

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 20, 20, 20)

        title = QLabel("🤖  LLM Assistant — First Time Setup")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        root.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        intro = QLabel(
            "The LLM Assistant needs a local AI model to understand your commands.\n"
            "Choose a size below — the model downloads once and runs completely offline.\n"
            "Uses llama-cpp-python for fast CPU inference (no GPU required)."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self._group = QButtonGroup(self)
        for i, model in enumerate(_MODELS):
            rb = QRadioButton()
            rb.setChecked(model["id"] == default["id"])

            row = QHBoxLayout()
            row.addWidget(rb)
            col = QVBoxLayout()
            col.setSpacing(1)
            name_lbl = QLabel(f"<b>{model['display']}</b>")
            name_lbl.setFont(QFont("Segoe UI", 11))
            desc_lbl = QLabel(model["desc"])
            desc_lbl.setStyleSheet("color: gray; font-size: 11px;")
            col.addWidget(name_lbl)
            col.addWidget(desc_lbl)
            row.addLayout(col)
            row.addStretch()

            container = QWidget()
            container.setLayout(row)
            root.addWidget(container)

            self._group.addButton(rb, i)
            rb.toggled.connect(lambda checked, m=model: self._on_toggle(checked, m))

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep2)

        note = QLabel(
            "📦  Models are stored in ~/.cache/huggingface/hub/ and reused on every launch."
        )
        note.setStyleSheet("color: gray; font-size: 10px;")
        note.setWordWrap(True)
        root.addWidget(note)

        btns = QDialogButtonBox()
        btns.addButton("Save Preference", QDialogButtonBox.ButtonRole.AcceptRole)
        btns.addButton("Skip for Now",    QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _on_toggle(self, checked: bool, model: dict):
        if checked:
            self.selected_model_id       = model["id"]
            self.selected_model_filename = model["filename"]


# ---------------------------------------------------------------------------
# Model download / load progress dialog
# ---------------------------------------------------------------------------

class ModelDownloadDialog(QDialog):
    """
    Shown immediately after the user picks a model in ModelSelectDialog.
    Runs _LoadThread and displays progress until the model is ready.
    """

    def __init__(self, plugin, model_id: str, model_filename: str, main_window, on_done=None, parent=None):
        super().__init__(parent)
        self._plugin         = plugin
        self._model_id       = model_id
        self._model_filename = model_filename
        self._mw             = main_window
        self._on_done_cb     = on_done
        self._load_thread = None

        self.setWindowTitle("LLM Assistant — Downloading Model")
        self.setMinimumWidth(480)
        self.setModal(True)
        # Disable the X button while downloading
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint
        )

        from PyQt6.QtWidgets import QProgressBar
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(20, 20, 20, 20)

        title = QLabel(f"Downloading model")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        root.addWidget(title)

        model_lbl = QLabel(f"{model_id}  [{model_filename}]")
        model_lbl.setStyleSheet("color: gray; font-size: 11px;")
        model_lbl.setWordWrap(True)
        root.addWidget(model_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        self._status_lbl = QLabel("Starting…")
        self._status_lbl.setWordWrap(True)
        root.addWidget(self._status_lbl)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)   # start indeterminate
        self._bar.setTextVisible(True)
        self._bar.setFormat("%p%")
        root.addWidget(self._bar)

        note = QLabel(
            "The model downloads once to ~/.cache/huggingface/hub/ "
            "and is reused on every subsequent launch."
        )
        note.setStyleSheet("color: gray; font-size: 10px;")
        note.setWordWrap(True)
        root.addWidget(note)

        self._close_btn = QPushButton("Please wait…")
        self._close_btn.setEnabled(False)
        self._close_btn.clicked.connect(self.accept)
        root.addWidget(self._close_btn)

    def start(self):
        """Begin the load thread.  Call after show()."""
        from .llm_engine import LLMEngine
        from .tool_binder import ToolBinder

        self._plugin.engine = LLMEngine(self._model_id, self._model_filename)
        self._plugin.binder = ToolBinder(self._mw)

        self._load_thread = _LoadThread(self._plugin.engine)
        self._load_thread.status.connect(self._on_status)
        self._load_thread.done.connect(self._on_done)
        self._load_thread.error.connect(self._on_error)
        self._load_thread.start()

    def _on_status(self, msg: str):
        self._status_lbl.setText(msg)
        # If msg contains a percentage from _HFProgressTqdm, make bar determinate
        # Format: "↓ filename  X / Y MB  (P%)"
        import re
        m = re.search(r"\((\d+)%\)", msg)
        if m:
            pct = int(m.group(1))
            self._bar.setRange(0, 100)
            self._bar.setValue(pct)
        elif "memory" in msg.lower() or "tokenizer" in msg.lower() or "cached" in msg.lower():
            # Back to indeterminate for the CPU-loading phase
            self._bar.setRange(0, 0)

    def _on_done(self):
        self._bar.setRange(0, 1)
        self._bar.setValue(1)
        self._status_lbl.setText("✅ Model ready!")
        # Re-enable window close
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowCloseButtonHint
        )
        self.show()
        self._close_btn.setText("Close")
        self._close_btn.setEnabled(True)
        if self._on_done_cb:
            try:
                self._on_done_cb()
            except Exception:
                pass

    def _on_error(self, err: str):
        self._bar.setRange(0, 1)
        self._bar.setValue(0)
        self._status_lbl.setText(
            f"❌ Download failed: {err}\n\n"
            "Make sure llama-cpp-python and huggingface-hub are installed:\n"
            "  pip install llama-cpp-python huggingface-hub"
        )
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowCloseButtonHint
        )
        self.show()
        self._close_btn.setText("Close")
        self._close_btn.setEnabled(True)


# ---------------------------------------------------------------------------
# Compact command bar — injected into action_page and area_page
# ---------------------------------------------------------------------------

class AssistantCommandBar(QWidget):
    """
    A single-row 'Ask AI' bar that sits at the top of the Action and
    Area selector pages when the plugin is enabled.

    Shares the engine/binder via the Plugin object so loading the model
    in the main tab immediately makes the bars functional too.
    """

    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self._plugin       = plugin   # access plugin.engine / plugin.binder
        self._infer_thread = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)

        bar = QHBoxLayout()
        bar.setSpacing(6)

        icon = QLabel("🤖")
        icon.setFixedWidth(22)
        bar.addWidget(icon)

        self._input = QLineEdit()
        self._input.setPlaceholderText(
            "Ask AI…  e.g. 'scrape <username> for all images'"
        )
        self._input.setFixedHeight(28)
        self._input.returnPressed.connect(self._on_send)
        bar.addWidget(self._input, stretch=1)

        self._btn = QPushButton("Ask ▶")
        self._btn.setMinimumWidth(72)
        self._btn.setFixedHeight(28)
        self._btn.clicked.connect(self._on_send)
        bar.addWidget(self._btn)

        layout.addLayout(bar)

        # Inline result label (auto-hides after 6 s)
        self._result_lbl = QLabel("")
        self._result_lbl.setWordWrap(True)
        self._result_lbl.setStyleSheet("font-size: 11px; color: #a6e3a1; padding-left: 30px;")
        self._result_lbl.setVisible(False)
        layout.addWidget(self._result_lbl)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(lambda: self._result_lbl.setVisible(False))

    # ------------------------------------------------------------------

    def _on_send(self):
        text = self._input.text().strip()
        if not text:
            return

        engine = getattr(self._plugin, "engine", None)
        binder = getattr(self._plugin, "binder", None)

        if not engine or not engine.is_loaded:
            self._show_result(
                "⚠ Model not loaded — open AI Assistant tab and click Load Model.",
                color="#f38ba8",
            )
            return

        if self._infer_thread and self._infer_thread.isRunning():
            self._show_result("Still processing previous request…", color="gray")
            return

        self._input.clear()
        self._btn.setEnabled(False)
        self._show_result("Thinking…", color="gray")

        gui_state = {}
        try:
            if binder:
                gui_state = binder.get_gui_state()
        except Exception:
            pass

        self._last_user_text = text
        self._infer_thread = _InferenceThread(engine, gui_state, text)
        self._infer_thread.partial.connect(
            lambda t: self._show_result(t[:160] + ("…" if len(t) > 160 else ""), color="gray")
        )
        self._infer_thread.result.connect(lambda raw: self._on_result(raw, binder))
        self._infer_thread.error.connect(lambda e: self._show_result(f"Error: {e}", color="#f38ba8"))
        self._infer_thread.finished.connect(lambda: self._btn.setEnabled(True))
        self._infer_thread.start()

    def _on_result(self, raw_text: str, binder):
        from .llm_engine import LLMEngine
        tool_calls, message = LLMEngine.parse_tool_calls(raw_text)
        tool_calls = _ensure_start_scraping(
            tool_calls, getattr(self, "_last_user_text", "")
        )
        exec_results: list[str] = []
        if tool_calls and binder:
            exec_results = binder.execute_all(tool_calls)
        summary = "  |  ".join(exec_results) if exec_results else (message.strip() or raw_text.strip())
        self._show_result(summary[:160] + ("…" if len(summary) > 160 else ""))

    def _show_result(self, text: str, color: str = "#a6e3a1"):
        self._result_lbl.setStyleSheet(
            f"font-size: 11px; color: {color}; padding-left: 30px;"
        )
        self._result_lbl.setText(html.escape(text))
        self._result_lbl.setVisible(True)
        self._hide_timer.start(6000)


# ---------------------------------------------------------------------------
# Main tab — full chat panel
# ---------------------------------------------------------------------------

class LLMAssistantTab(QWidget):
    """Full-page chat interface in the sidebar stack."""

    def __init__(self, plugin, main_window, data_dir):
        super().__init__()
        self._plugin   = plugin
        self._mw       = main_window
        self._data_dir = data_dir

        self._load_thread  = None
        self._infer_thread = None

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(6)

        # ── Model selector row ──────────────────────────────────────────
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Model:"))

        from PyQt6.QtWidgets import QComboBox
        self._model_combo = QComboBox()
        self._model_combo.setToolTip(
            "GGUF quantized models via llama-cpp-python — fast CPU inference.\n"
            "0.5B Q8  (~530 MB): Fastest, good for simple commands.\n"
            "1.5B Q4  (~1.1 GB): Recommended balance of speed and accuracy.\n"
            "3B   Q4  (~2.0 GB): Best quality, needs ~2+ GB free RAM."
        )
        for model in _MODELS:
            self._model_combo.addItem(model["display"], userData=model)

        # Pre-select saved preference if any
        saved = getattr(self._plugin, "_saved_model_id", None)
        if saved:
            for i in range(self._model_combo.count()):
                data = self._model_combo.itemData(i)
                if isinstance(data, dict) and data.get("id") == saved:
                    self._model_combo.setCurrentIndex(i)
                    break

        model_row.addWidget(self._model_combo, stretch=1)

        self._load_btn = QPushButton("Load Model")
        self._load_btn.setStyleSheet("padding: 4px 12px;")
        self._load_btn.clicked.connect(self._on_load_model)
        model_row.addWidget(self._load_btn)

        self._unload_btn = QPushButton("Unload")
        self._unload_btn.setStyleSheet("padding: 4px 12px;")
        self._unload_btn.setEnabled(False)
        self._unload_btn.clicked.connect(self._on_unload_model)
        model_row.addWidget(self._unload_btn)

        root.addLayout(model_row)

        # ── Status bar ──────────────────────────────────────────────────
        self._status_lbl = QLabel("Model not loaded — click Load Model to begin.")
        self._status_lbl.setStyleSheet("color: gray; font-size: 11px;")
        self._status_lbl.setWordWrap(True)
        root.addWidget(self._status_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        # ── Chat history ────────────────────────────────────────────────
        self._chat = QTextBrowser()
        self._chat.setOpenExternalLinks(False)
        self._chat.setReadOnly(True)
        self._chat.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._chat.setHtml(_WELCOME_HTML)
        root.addWidget(self._chat, stretch=1)

        # ── Current state summary ───────────────────────────────────────
        self._state_lbl = QLabel("")
        self._state_lbl.setStyleSheet("color: gray; font-size: 10px;")
        self._state_lbl.setWordWrap(True)
        root.addWidget(self._state_lbl)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep2)

        # ── Input row ───────────────────────────────────────────────────
        input_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText(
            "Type a command…  e.g. 'scrape <username> for all media'"
        )
        self._input.setFont(QFont("Segoe UI", 11))
        self._input.returnPressed.connect(self._on_send)
        input_row.addWidget(self._input, stretch=1)

        self._send_btn = QPushButton("Send ▶")
        self._send_btn.setFixedWidth(80)
        self._send_btn.setEnabled(False)
        self._send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self._send_btn)

        root.addLayout(input_row)

        QTimer.singleShot(500, self._refresh_state_label)

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    def _on_load_model(self):
        model_data = self._model_combo.currentData()
        if not isinstance(model_data, dict):
            model_data = _MODELS[1]
        model_id       = model_data["id"]
        model_filename = model_data["filename"]

        # Check deps before starting — if missing, show install dialog first
        missing = _check_missing_deps()
        if missing:
            deps_dlg = DepsInstallDialog(missing_packages=missing, parent=self)
            if not deps_dlg.exec():
                return   # cancelled or failed

        self._load_btn.setEnabled(False)
        self._model_combo.setEnabled(False)
        self._set_status(
            f"Loading {model_filename}…  (first run downloads the model)"
        )

        from .llm_engine import LLMEngine
        from .tool_binder import ToolBinder

        self._plugin.engine = LLMEngine(model_id, model_filename)
        self._plugin.binder = ToolBinder(self._mw)

        self._load_thread = _LoadThread(self._plugin.engine)
        self._load_thread.status.connect(self._set_status)
        self._load_thread.done.connect(self._on_load_done)
        self._load_thread.error.connect(self._on_load_error)
        self._load_thread.start()

    def _on_load_done(self):
        self._set_status("✅ Model loaded and ready.")
        self._send_btn.setEnabled(True)
        self._unload_btn.setEnabled(True)
        self._load_btn.setText("Reload")
        self._load_btn.setEnabled(True)
        self._model_combo.setEnabled(False)
        self._append_system("Model ready!  Type a command below.")

    def _on_load_error(self, err: str):
        self._set_status(f"❌ Load failed: {err}")
        self._load_btn.setEnabled(True)
        self._model_combo.setEnabled(True)
        self._append_system(
            f"Failed to load model: {err}\n\n"
            "Make sure llama-cpp-python and huggingface-hub are installed:\n"
            "  pip install llama-cpp-python huggingface-hub"
        )

    def _on_unload_model(self):
        if self._plugin.engine:
            try:
                self._plugin.engine.unload()
            except Exception:
                pass
        self._plugin.engine = None
        self._plugin.binder = None
        self._send_btn.setEnabled(False)
        self._unload_btn.setEnabled(False)
        self._load_btn.setText("Load Model")
        self._load_btn.setEnabled(True)
        self._model_combo.setEnabled(True)
        self._set_status("Model unloaded.")
        self._append_system("Model unloaded.")

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def _on_send(self):
        text = self._input.text().strip()
        if not text:
            return
        engine = getattr(self._plugin, "engine", None)
        binder = getattr(self._plugin, "binder", None)
        if not engine or not engine.is_loaded:
            self._append_system("Please load the model first (click 'Load Model').")
            return
        if self._infer_thread and self._infer_thread.isRunning():
            self._append_system("Still processing — please wait…")
            return

        self._input.clear()
        self._append_user(text)
        self._send_btn.setEnabled(False)
        self._set_status("Processing…")

        gui_state = {}
        try:
            if binder:
                gui_state = binder.get_gui_state()
        except Exception:
            pass

        self._last_user_text = text
        self._infer_thread = _InferenceThread(engine, gui_state, text)
        self._infer_thread.status.connect(self._set_status)
        self._infer_thread.partial.connect(
            lambda t: self._set_status("Generating: " + t[-60:].replace("\n", " "))
        )
        self._infer_thread.result.connect(self._on_result)
        self._infer_thread.error.connect(self._on_infer_error)
        self._infer_thread.finished.connect(
            lambda: self._send_btn.setEnabled(
                bool(getattr(self._plugin, "engine", None) and
                     getattr(self._plugin.engine, "is_loaded", False))
            )
        )
        self._infer_thread.start()

    def _on_result(self, raw_text: str):
        from .llm_engine import LLMEngine
        binder = getattr(self._plugin, "binder", None)
        tool_calls, message = LLMEngine.parse_tool_calls(raw_text)
        tool_calls = _ensure_start_scraping(
            tool_calls, getattr(self, "_last_user_text", "")
        )
        exec_results: list[str] = []
        if tool_calls and binder:
            exec_results = binder.execute_all(tool_calls)

        parts: list[str] = []
        for r in exec_results:
            parts.append(f"• {html.escape(r)}")
        if message and message.strip():
            parts.append(f"<br><i>{html.escape(message.strip())}</i>")
        if not parts:
            parts.append(html.escape(raw_text.strip() or "(no response)"))

        self._append_assistant("<br>".join(parts))
        self._set_status("Ready.")
        self._refresh_state_label()

    def _on_infer_error(self, err: str):
        self._append_system(f"Inference error: {html.escape(err)}")
        self._set_status("Error — see above.")

    # ------------------------------------------------------------------
    # Chat display helpers
    # ------------------------------------------------------------------

    def _append_user(self, text: str):
        self._chat.append(
            f'<p><b style="color:#89b4fa;">You:</b> {html.escape(text)}</p>'
        )

    def _append_assistant(self, html_text: str):
        self._chat.append(
            f'<p><b style="color:#a6e3a1;">Assistant:</b> {html_text}</p>'
        )

    def _append_system(self, text: str):
        self._chat.append(
            f'<p style="color:gray;font-size:11px;"><i>{html.escape(str(text))}</i></p>'
        )

    def _set_status(self, msg: str):
        self._status_lbl.setText(msg)

    def _refresh_state_label(self):
        try:
            binder = getattr(self._plugin, "binder", None)
            if not binder:
                return
            s = binder.get_gui_state()
            areas = ", ".join(s.get("areas") or ["(none)"])
            users = ", ".join(s.get("usernames") or ["(none)"])
            action = s.get("action", "download")
            daemon_str = (
                f"daemon every {s.get('daemon_interval', 30):.0f} min"
                if s.get("daemon") else "no daemon"
            )
            self._state_lbl.setText(
                f"State: action={action} | users={users} | "
                f"areas={areas} | {daemon_str}"
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Plugin lifecycle
    # ------------------------------------------------------------------

    def cleanup(self):
        engine = getattr(self._plugin, "engine", None)
        if engine:
            try:
                engine.unload()
            except Exception:
                pass
