import glob
import json
import os
import shutil
from pathlib import Path

from PyQt6.QtCore import QEvent, Qt, QSize, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QIcon, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .database import MediaItem, canonical_media_path, normalize_tag_pairs
from .main import CAPTION_TYPES, CAPTION_LENGTHS

_TAGS_ROLE = Qt.ItemDataRole.UserRole + 1
_PATH_ROLE = Qt.ItemDataRole.UserRole + 2

# ---------------------------------------------------------------------------
# Synonym groups — loaded from synonyms.json next to this file.
# Searching any term in a group matches all terms in the same group.
# Multi-word phrases (e.g. "blow job", "on all fours") are fully supported.
# ---------------------------------------------------------------------------

def _load_synonym_groups() -> list[set[str]]:
    """Load synonym groups from synonyms.json (same directory as this file)."""
    try:
        syn_path = Path(__file__).parent / "synonyms.json"
        with open(syn_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            # Dict format: {category: [terms, ...]} — skip the _comment key
            return [set(v) for k, v in data.items() if k != "_comment" and isinstance(v, list)]
        if isinstance(data, list):
            return [set(group) for group in data if isinstance(group, list)]
    except Exception:
        pass
    return []


_SYNONYM_GROUPS: list[set[str]] = _load_synonym_groups()


def _expand_search(keyword: str) -> set[str]:
    """Return the keyword plus all synonyms from its group (if any)."""
    kw = keyword.strip().lower()
    if not kw:
        return set()
    for group in _SYNONYM_GROUPS:
        if kw in group:
            return group
    return {kw}


def _parse_search_tokens(keyword: str) -> list[set[str]]:
    """
    Parse a search string into synonym-expanded term groups for AND matching.

    Greedily matches the longest known synonym phrase at each position before
    falling back to single-word literal tokens.  This ensures multi-word
    phrases like 'blow job' or 'on all fours' are treated as one unit and
    expanded to their full synonym group.
    """
    words = keyword.strip().lower().split()
    result: list[set[str]] = []
    i = 0
    while i < len(words):
        best_length = 0
        best_group: set[str] | None = None
        # Try longest phrase first (greedy match)
        for length in range(len(words) - i, 0, -1):
            phrase = " ".join(words[i:i + length])
            for grp in _SYNONYM_GROUPS:
                if phrase in grp:
                    best_length = length
                    best_group = grp
                    break
            if best_group is not None:
                break
        if best_group is not None:
            result.append(best_group)
            i += best_length
        else:
            # No synonym match — use the word as a literal search term
            result.append({words[i]})
            i += 1
    return result


def _gallery_scan_progress_qss():
    """Match ofscraper.gui.widgets.progress_panel.ProgressSummaryBar (blue chunk #1d4ed8)."""
    try:
        from ofscraper.gui.styles import c
        return (
            f"QProgressBar {{ border: 1px solid {c('surface1')}; border-radius: 4px;"
            f" background-color: {c('surface0')}; color: #f8fafc; text-align: center; padding: 0px; }}"
            f" QProgressBar::chunk {{ background-color: #1d4ed8; border-radius: 4px; }}"
        )
    except Exception:
        return (
            "QProgressBar { border: 1px solid #45475a; border-radius: 4px;"
            " background-color: #313244; color: #f8fafc; text-align: center; padding: 0px; }"
            " QProgressBar::chunk { background-color: #1d4ed8; border-radius: 4px; }"
        )


# ---------------------------------------------------------------------------
# Scan thread
# ---------------------------------------------------------------------------

class ScanFolderThread(QThread):
    progress = pyqtSignal(int, int)
    scan_finished = pyqtSignal(int, int, bool)

    def __init__(self, plugin, files, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self.files = list(files)
        self._cancel = False

    def cancel_scan(self):
        self._cancel = True

    def run(self):
        added = 0
        total = len(self.files)
        cancelled = False
        try:
            for i, fp in enumerate(self.files):
                if self._cancel:
                    cancelled = True
                    break
                canon = canonical_media_path(fp)
                if not os.path.isfile(canon):
                    self.progress.emit(i + 1, total)
                    continue
                try:
                    r = self.plugin.try_ingest_existing_path(canon)
                    if r == "added":
                        added += 1
                except Exception as e:
                    import logging
                    logging.getLogger("ofscraper_plugin.joycaption_tagger").error(
                        "Scan error for %s: %s", canon, e
                    )
                self.progress.emit(i + 1, total)
        finally:
            self.scan_finished.emit(added, total, cancelled)


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------

class SettingsDialog(QDialog):
    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self.setWindowTitle("JoyCaption Tagger — Settings")
        self.setMinimumWidth(500)

        layout = QFormLayout(self)

        # ComfyUI URL
        url_row = QHBoxLayout()
        self.url_edit = QLineEdit(self.plugin.settings.get("comfyui_url", "http://localhost:8188"))
        self.test_btn = QPushButton("Test")
        self.test_btn.setFixedWidth(60)
        self.test_btn.clicked.connect(self._test_connection)
        url_row.addWidget(self.url_edit)
        url_row.addWidget(self.test_btn)
        layout.addRow("ComfyUI URL:", url_row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray;")
        layout.addRow("", self.status_label)

        # Caption type
        self.caption_type_combo = QComboBox()
        for ct in CAPTION_TYPES:
            self.caption_type_combo.addItem(ct)
        saved_ct = self.plugin.settings.get("caption_type", "Descriptive")
        idx = self.caption_type_combo.findText(saved_ct)
        if idx >= 0:
            self.caption_type_combo.setCurrentIndex(idx)
        layout.addRow("Caption Type:", self.caption_type_combo)

        # Caption length
        self.caption_len_combo = QComboBox()
        for cl in CAPTION_LENGTHS:
            self.caption_len_combo.addItem(cl)
        saved_cl = self.plugin.settings.get("caption_length", "long")
        idx = self.caption_len_combo.findText(saved_cl)
        if idx >= 0:
            self.caption_len_combo.setCurrentIndex(idx)
        layout.addRow("Caption Length:", self.caption_len_combo)

        # Extra options (comma-separated flags like "Do not include...")
        self.extra_edit = QLineEdit(
            ", ".join(self.plugin.settings.get("extra_options", []))
        )
        self.extra_edit.setPlaceholderText("e.g. Do not include low quality, Do not use vague language")
        layout.addRow("Extra Options:", self.extra_edit)

        # Name input (for people/characters)
        self.name_edit = QLineEdit(self.plugin.settings.get("name_input", ""))
        self.name_edit.setPlaceholderText("Optional — name of subject")
        layout.addRow("Subject Name:", self.name_edit)

        # Timeout
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(10, 600)
        self.timeout_spin.setSuffix(" s")
        self.timeout_spin.setValue(int(self.plugin.settings.get("timeout", 120)))
        layout.addRow("Timeout:", self.timeout_spin)

        # Top-K
        self.topk_spin = QSpinBox()
        self.topk_spin.setRange(1, 100)
        self.topk_spin.setValue(int(self.plugin.settings.get("tag_top_k", 20)))
        self.topk_spin.setToolTip(
            "Max caption parts to store. For tag-list modes this limits individual tags; "
            "for descriptive modes the full caption is always stored as the first entry."
        )
        layout.addRow("Max stored parts:", self.topk_spin)

        # Auto-tag
        self.auto_tag_cb = QCheckBox("Auto-tag images on download")
        self.auto_tag_cb.setChecked(bool(self.plugin.settings.get("auto_tag_images", True)))
        layout.addRow("", self.auto_tag_cb)

        # Smart folders
        self.smart_folders_cb = QCheckBox("Enable Smart Folders")
        self.smart_folders_cb.setChecked(bool(self.plugin.settings.get("smart_folders", False)))
        layout.addRow("", self.smart_folders_cb)

        sf_row = QHBoxLayout()
        self.sf_path_edit = QLineEdit(
            self.plugin.settings.get("smart_folder_path", str(self.plugin.data_dir / "Smart_Tags"))
        )
        sf_browse = QPushButton("Browse")
        sf_browse.setFixedWidth(70)
        sf_browse.clicked.connect(self._browse_smart_folder)
        sf_row.addWidget(self.sf_path_edit)
        sf_row.addWidget(sf_browse)
        layout.addRow("Smart Folder Path:", sf_row)

        # Workflow file selector
        self.workflow_combo = QComboBox()
        self._populate_workflows()
        saved_wf = self.plugin.settings.get("workflow_file", "joycaption.json")
        idx = self.workflow_combo.findText(saved_wf)
        if idx >= 0:
            self.workflow_combo.setCurrentIndex(idx)
        layout.addRow("Workflow:", self.workflow_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _populate_workflows(self):
        wf_dir = self.plugin.data_dir / "workflows"
        bundled = Path(__file__).parent / "workflows"
        seen = set()
        for d in [wf_dir, bundled]:
            for p in sorted(d.glob("*.json")) if d.exists() else []:
                if p.name not in seen:
                    self.workflow_combo.addItem(p.name)
                    seen.add(p.name)
        if self.workflow_combo.count() == 0:
            self.workflow_combo.addItem("joycaption.json")

    def _test_connection(self):
        from .comfyui_client import ComfyUIClient
        url = self.url_edit.text().strip()
        client = ComfyUIClient(url)
        if client.check_connection():
            self.status_label.setStyleSheet("color: green;")
            self.status_label.setText("Connected!")
        else:
            self.status_label.setStyleSheet("color: red;")
            self.status_label.setText("Cannot reach ComfyUI. Check URL and that the server is running.")

    def _browse_smart_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Smart Folder Location", self.sf_path_edit.text())
        if d:
            self.sf_path_edit.setText(d)

    def _save_and_accept(self):
        extra_raw = [x.strip() for x in self.extra_edit.text().split(",") if x.strip()]
        self.plugin.settings.update({
            "comfyui_url": self.url_edit.text().strip(),
            "caption_type": self.caption_type_combo.currentText(),
            "caption_length": self.caption_len_combo.currentText(),
            "extra_options": extra_raw,
            "name_input": self.name_edit.text().strip(),
            "timeout": self.timeout_spin.value(),
            "tag_top_k": self.topk_spin.value(),
            "auto_tag_images": self.auto_tag_cb.isChecked(),
            "smart_folders": self.smart_folders_cb.isChecked(),
            "smart_folder_path": self.sf_path_edit.text().strip(),
            "workflow_file": self.workflow_combo.currentText(),
        })
        try:
            with open(self.plugin.settings_path, "w", encoding="utf-8") as f:
                json.dump(self.plugin.settings, f, indent=2)
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))
            return
        # Invalidate workflow cache so changes take effect immediately.
        self.plugin._invalidate_workflow_cache()
        self.accept()


# ---------------------------------------------------------------------------
# Main gallery tab
# ---------------------------------------------------------------------------

class JoyCaptionTab(QWidget):
    request_refresh = pyqtSignal()

    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self._scan_thread: ScanFolderThread | None = None
        self._preview_full_pixmap = None
        self._full_view_row = 0
        self._active_model_filter: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        # Top bar: search + buttons
        top_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by caption / tag… (space = AND, e.g. 'pussy table')")
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(lambda: self._filter_gallery(self.search_input.text()))
        self.search_input.textChanged.connect(lambda _: self._search_timer.start())
        top_bar.addWidget(QLabel("Search:"))
        top_bar.addWidget(self.search_input)

        self.scan_btn = QPushButton("📁 Scan Folder")
        self.scan_btn.clicked.connect(self._start_scan)
        top_bar.addWidget(self.scan_btn)

        self._btn_models = QPushButton("👤 Models")
        self._btn_models.setToolTip("Browse images by model")
        self._btn_models.clicked.connect(self._show_models_page)
        top_bar.addWidget(self._btn_models)

        btn_settings = QPushButton("⚙️ Settings")
        btn_settings.clicked.connect(self._open_settings)
        top_bar.addWidget(btn_settings)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.clicked.connect(self._load_gallery)
        top_bar.addWidget(btn_refresh)

        # Active model filter indicator (hidden until a model is selected)
        self._model_filter_widget = QWidget()
        _mfw = QHBoxLayout(self._model_filter_widget)
        _mfw.setContentsMargins(4, 0, 0, 0)
        _mfw.setSpacing(2)
        self._model_filter_label = QLabel("")
        self._model_filter_label.setStyleSheet("font-weight: bold;")
        _mfw_clear = QPushButton("✕ All Images")
        _mfw_clear.setToolTip("Clear model filter — return to full gallery")
        _mfw_clear.clicked.connect(self._clear_model_filter)
        _mfw.addWidget(self._model_filter_label)
        _mfw.addWidget(_mfw_clear)
        self._model_filter_widget.setVisible(False)
        top_bar.addWidget(self._model_filter_widget)

        root.addLayout(top_bar)

        # Selected-file label
        self.selected_label = QLabel("No image selected")
        root.addWidget(self.selected_label)

        # ── Gallery page ──────────────────────────────────────────────
        self.gallery = QListWidget()
        self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setIconSize(QSize(150, 150))
        self.gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery.setSpacing(10)
        self.gallery.setToolTip("Click a thumbnail for full-size view. ← → to browse. Esc to return.")
        self.gallery.itemClicked.connect(self._on_gallery_item_clicked)

        # ── Full-view page ────────────────────────────────────────────
        self._preview_scroll = QScrollArea()
        self._preview_scroll.setWidgetResizable(False)
        self._preview_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_image_label = QLabel()
        self._preview_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_scroll.setWidget(self._preview_image_label)
        self._preview_scroll.viewport().installEventFilter(self)

        self._preview_dims_label = QLabel("")
        self._preview_tags_label = QLabel("")
        self._preview_tags_label.setWordWrap(True)
        self._preview_tags_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        full_nav = QHBoxLayout()
        self._btn_back = QPushButton("← Back to gallery")
        self._btn_back.clicked.connect(self._back_to_gallery)
        self._btn_prev = QPushButton("← Previous")
        self._btn_prev.clicked.connect(self._full_view_prev)
        self._btn_next = QPushButton("Next →")
        self._btn_next.clicked.connect(self._full_view_next)
        self._btn_open_viewer = QPushButton("🖼 Open in Viewer")
        self._btn_open_viewer.setToolTip("Open this image in the system default image viewer")
        self._btn_open_viewer.clicked.connect(self._open_in_viewer)
        self._pos_label = QLabel("")
        full_nav.addWidget(self._btn_back)
        full_nav.addWidget(self._btn_prev)
        full_nav.addWidget(self._btn_next)
        full_nav.addStretch()
        full_nav.addWidget(self._btn_open_viewer)
        full_nav.addWidget(self._pos_label)

        full_page = QWidget()
        full_layout = QVBoxLayout(full_page)
        full_layout.setContentsMargins(0, 0, 0, 0)
        full_layout.setSpacing(8)
        full_layout.addLayout(full_nav)
        full_layout.addWidget(self._preview_scroll, stretch=1)
        full_layout.addWidget(self._preview_dims_label)
        full_layout.addWidget(QLabel("Caption / Tags"))
        full_layout.addWidget(self._preview_tags_label)

        # ── Models page ───────────────────────────────────────────────
        models_page = QWidget()
        models_layout = QVBoxLayout(models_page)
        models_layout.setContentsMargins(0, 0, 0, 0)
        models_layout.setSpacing(6)
        models_top = QHBoxLayout()
        btn_models_back = QPushButton("← Back to Gallery")
        btn_models_back.clicked.connect(lambda: self._gallery_stack.setCurrentIndex(0))
        models_top.addWidget(btn_models_back)
        models_top.addStretch()
        btn_redetect = QPushButton("🔍 Re-detect model names")
        btn_redetect.setToolTip(
            "Update model names for all gallery entries where none was detected.\n"
            "Run this after scanning folders if the Models list appears empty."
        )
        btn_redetect.clicked.connect(self._redetect_model_names)
        models_top.addWidget(btn_redetect)
        models_layout.addLayout(models_top)
        self._models_list = QListWidget()
        self._models_list.setViewMode(QListWidget.ViewMode.IconMode)
        self._models_list.setIconSize(QSize(80, 80))
        self._models_list.setGridSize(QSize(120, 130))
        self._models_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._models_list.setSpacing(12)
        self._models_list.setWordWrap(True)
        self._models_list.setMovement(QListWidget.Movement.Static)
        self._models_list.itemClicked.connect(self._on_model_selected)
        models_layout.addWidget(self._models_list, stretch=1)

        # ── Stacked widget ────────────────────────────────────────────
        self._gallery_stack = QStackedWidget()
        self._gallery_stack.addWidget(self.gallery)   # index 0
        self._gallery_stack.addWidget(full_page)      # index 1
        self._gallery_stack.addWidget(models_page)    # index 2
        root.addWidget(self._gallery_stack, stretch=1)

        # Keyboard shortcuts
        for seq, slot in (
            (QKeySequence("Left"), self._shortcut_prev),
            (QKeySequence("Right"), self._shortcut_next),
            (QKeySequence("Esc"), self._shortcut_back),
        ):
            sc = QShortcut(seq, self)
            sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
            sc.activated.connect(slot)

        # ── Progress / status strip ───────────────────────────────────
        self._scan_progress_frame = QWidget()
        scan_row = QHBoxLayout(self._scan_progress_frame)
        scan_row.setContentsMargins(0, 4, 0, 0)
        scan_row.setSpacing(8)
        self._scan_progress_label = QLabel("")
        self._scan_progress_bar = QProgressBar()
        self._scan_progress_bar.setRange(0, 100)
        self._scan_progress_bar.setValue(0)
        self._scan_progress_bar.setTextVisible(True)
        self._scan_progress_bar.setFixedHeight(18)
        self._scan_progress_bar.setStyleSheet(_gallery_scan_progress_qss())
        self._scan_cancel_btn = QPushButton("Cancel")
        self._scan_cancel_btn.setFixedWidth(72)
        self._scan_cancel_btn.clicked.connect(self._cancel_scan)
        scan_row.addWidget(self._scan_progress_label)
        scan_row.addWidget(self._scan_progress_bar, stretch=1)
        scan_row.addWidget(self._scan_cancel_btn)
        self._scan_progress_frame.setVisible(False)
        root.addWidget(self._scan_progress_frame)

        self.status_label = QLabel("Ready.")
        root.addWidget(self.status_label)

        self.request_refresh.connect(self._load_gallery)
        QTimer.singleShot(200, self._load_gallery)

    # ------------------------------------------------------------------
    # Qt event filter (scroll area resize → re-fit preview)
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        if obj is self._preview_scroll.viewport() and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self._fit_preview_image)
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------

    def _shortcut_prev(self):
        if self._gallery_stack.currentIndex() == 1:
            self._full_view_prev()

    def _shortcut_next(self):
        if self._gallery_stack.currentIndex() == 1:
            self._full_view_next()

    def _shortcut_back(self):
        if self._gallery_stack.currentIndex() == 1:
            self._back_to_gallery()

    # ------------------------------------------------------------------
    # Gallery loading & filtering
    # ------------------------------------------------------------------

    def _load_gallery(self):
        self._filter_gallery(self.search_input.text())

    def _filter_gallery(self, keyword: str = ""):
        self.gallery.clear()
        try:
            query = MediaItem.select().order_by(MediaItem.created_at.desc())
            if self._active_model_filter:
                query = query.where(MediaItem.model_username == self._active_model_filter)
            items = list(query)
        except Exception as e:
            self.status_label.setText(f"DB error: {e}")
            return

        kw = keyword.strip().lower()
        # Parse into synonym-expanded term groups; ALL groups must match (AND logic).
        # Multi-word phrases like "blow job" are handled as a single unit.
        term_groups = _parse_search_tokens(kw) if kw else []
        shown = 0
        for item in items:
            tags = item.get_tags()
            pairs = normalize_tag_pairs(tags)
            tag_text = " ".join(t.lower() for t, _ in pairs)
            if term_groups and not all(
                any(term in tag_text for term in grp) for grp in term_groups
            ):
                continue
            lw_item = QListWidgetItem()
            path = item.file_path
            lw_item.setData(_PATH_ROLE, path)
            lw_item.setData(_TAGS_ROLE, tags)
            lw_item.setToolTip(Path(path).name)
            if os.path.isfile(path):
                pix = QPixmap(path)
                if not pix.isNull():
                    lw_item.setIcon(
                        QIcon(pix.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation))
                    )
            self.gallery.addItem(lw_item)
            shown += 1

        total = len(items)
        prefix = f"👤 {self._active_model_filter} — " if self._active_model_filter else ""
        if term_groups:
            self.status_label.setText(f"{prefix}{shown} / {total} images match")
        else:
            self.status_label.setText(f"{prefix}{total} images")

    # ------------------------------------------------------------------
    # Gallery → full view
    # ------------------------------------------------------------------

    def _on_gallery_item_clicked(self, item: QListWidgetItem):
        self._show_full_view_for_row(self.gallery.row(item))

    def _show_full_view_for_row(self, row: int):
        n = self.gallery.count()
        if row < 0 or row >= n:
            return
        self._full_view_row = row
        self.gallery.blockSignals(True)
        self.gallery.setCurrentRow(row)
        self.gallery.blockSignals(False)
        item = self.gallery.item(row)
        path = item.data(_PATH_ROLE) or ""
        self.selected_label.setText(f"Selected: {Path(path).name}" if path else "No image selected")
        self._populate_full_view(item)
        self._gallery_stack.setCurrentIndex(1)
        self._update_nav_state()
        QTimer.singleShot(0, self._fit_preview_image)

    def _back_to_gallery(self):
        self._gallery_stack.setCurrentIndex(0)
        cur = self.gallery.currentItem()
        if cur:
            self.gallery.scrollToItem(cur)

    def _full_view_prev(self):
        self._show_full_view_for_row(self._full_view_row - 1)

    def _full_view_next(self):
        self._show_full_view_for_row(self._full_view_row + 1)

    def _update_nav_state(self):
        n = self.gallery.count()
        r = self._full_view_row
        self._btn_prev.setEnabled(n > 0 and r > 0)
        self._btn_next.setEnabled(n > 0 and r < n - 1)
        self._pos_label.setText(f"{r + 1} / {n}" if n else "")
        item = self.gallery.item(r) if 0 <= r < n else None
        path = item.data(_PATH_ROLE) if item else None
        self._btn_open_viewer.setEnabled(bool(path and os.path.isfile(path)))

    def _open_in_viewer(self):
        item = self.gallery.item(self._full_view_row)
        if not item:
            return
        path = item.data(_PATH_ROLE) or ""
        if path and os.path.isfile(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _fit_preview_image(self):
        if self._preview_full_pixmap is None or self._preview_full_pixmap.isNull():
            return
        vp = self._preview_scroll.viewport().size()
        w, h = vp.width() - 12, vp.height() - 12
        if w < 32 or h < 32:
            return
        scaled = self._preview_full_pixmap.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_image_label.setPixmap(scaled)
        self._preview_image_label.setMinimumSize(scaled.size())
        self._preview_image_label.setMaximumSize(scaled.size())
        self._preview_image_label.resize(scaled.size())
        src = self._preview_full_pixmap
        if scaled.size() != src.size():
            self._preview_dims_label.setText(
                f"{src.width()}×{src.height()} px — preview scaled to fit panel"
            )
        else:
            self._preview_dims_label.setText(f"{src.width()}×{src.height()} px")

    def _populate_full_view(self, item: QListWidgetItem):
        path = item.data(_PATH_ROLE) or ""
        if not path or not os.path.isfile(path):
            self._preview_full_pixmap = None
            self._preview_image_label.setText("File missing")
            self._preview_dims_label.setText("")
            self._preview_tags_label.setText("")
            return
        pm = QPixmap(path)
        if pm.isNull():
            self._preview_full_pixmap = None
            self._preview_image_label.setText("Could not load image")
            self._preview_dims_label.setText("")
            self._preview_tags_label.setText("")
            return
        self._preview_full_pixmap = pm
        self._preview_image_label.setText("")
        tags = item.data(_TAGS_ROLE) or []
        pairs = normalize_tag_pairs(tags)
        if pairs:
            lines = [pairs[0][0]]
            if len(pairs) > 1:
                lines.append("")
                lines.append("Tags: " + ", ".join(t for t, _ in pairs[1:]))
            self._preview_tags_label.setText("\n".join(lines))
        else:
            self._preview_tags_label.setText("(no caption)")

    # ------------------------------------------------------------------
    # Models page
    # ------------------------------------------------------------------

    def _show_models_page(self):
        self._load_models_page()
        self._gallery_stack.setCurrentIndex(2)

    def _load_models_page(self):
        self._models_list.clear()
        try:
            from peewee import fn
            rows = (
                MediaItem
                .select(MediaItem.model_username, fn.COUNT(MediaItem.id).alias("cnt"))
                .where(MediaItem.model_username != "")
                .group_by(MediaItem.model_username)
                .order_by(MediaItem.model_username)
            )
            for row in rows:
                lw_item = QListWidgetItem(f"{row.model_username}\n({row.cnt} images)")
                lw_item.setData(Qt.ItemDataRole.UserRole, row.model_username)
                lw_item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
                avatar_path = self._find_model_avatar(row.model_username)
                if avatar_path:
                    pix = QPixmap(avatar_path)
                    if not pix.isNull():
                        size = 80
                        scaled = pix.scaled(
                            size, size,
                            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        x = (scaled.width() - size) // 2
                        y = (scaled.height() - size) // 2
                        lw_item.setIcon(QIcon(scaled.copy(x, y, size, size)))
                self._models_list.addItem(lw_item)
            if self._models_list.count() == 0:
                self._models_list.addItem(QListWidgetItem("No models found — scan a folder to populate"))
        except Exception as e:
            self._models_list.addItem(QListWidgetItem(f"Error loading models: {e}"))

    def _find_model_dir(self, file_path: str, username: str) -> str | None:
        """Find the model's base directory from a stored file path."""
        parts = Path(str(file_path)).parts
        for i, part in enumerate(parts):
            if part == username and i > 0:
                return str(Path(*parts[:i + 1]))
        return None

    def _find_model_avatar(self, username: str) -> str | None:
        """Find the avatar image for a model from their Profile/Images folder."""
        try:
            record = MediaItem.select().where(MediaItem.model_username == username).first()
            if not record:
                return None
            model_dir = self._find_model_dir(record.file_path, username)
            if not model_dir:
                return None
            profile_imgs = Path(model_dir) / "Profile" / "Images"
            if not profile_imgs.is_dir():
                return None
            # Prefer exact non-dated avatar first
            for name in ("avatar.jpeg", "avatar.jpg", "avatar.png", "avatar.webp"):
                p = profile_imgs / name
                if p.is_file():
                    return str(p)
            # Fall back to any avatar* file (undated sorts before dated)
            candidates = sorted(profile_imgs.glob("avatar*"))
            if candidates:
                return str(candidates[0])
        except Exception:
            pass
        return None

    def _on_model_selected(self, item: QListWidgetItem):
        username = item.data(Qt.ItemDataRole.UserRole)
        if not username:
            return
        self._active_model_filter = username
        self._model_filter_label.setText(f"👤 {username}")
        self._model_filter_widget.setVisible(True)
        self._gallery_stack.setCurrentIndex(0)
        self._load_gallery()

    def _clear_model_filter(self):
        self._active_model_filter = None
        self._model_filter_widget.setVisible(False)
        self._load_gallery()

    def _redetect_model_names(self):
        """Backfill model_username for all existing records that have an empty value."""
        from .database import extract_model_username
        try:
            records = list(MediaItem.select().where(MediaItem.model_username == ""))
            updated = 0
            for record in records:
                username = extract_model_username(record.file_path)
                if username:
                    record.model_username = username
                    record.save()
                    updated += 1
        except Exception as e:
            self.status_label.setText(f"Re-detect error: {e}")
            return
        self._load_models_page()
        self.status_label.setText(
            f"Re-detected {updated} model name(s) from {len(records)} untagged record(s)."
        )

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _open_settings(self):
        dlg = SettingsDialog(self.plugin, self)
        if dlg.exec():
            self._load_gallery()

    # ------------------------------------------------------------------
    # Scan folder
    # ------------------------------------------------------------------

    def _start_scan(self):
        folder = QFileDialog.getExistingDirectory(self, "Select folder to scan")
        if not folder:
            return

        from .comfyui_client import ComfyUIClient
        url = self.plugin.settings.get("comfyui_url", "http://localhost:8188")
        if not ComfyUIClient(url).check_connection():
            QMessageBox.critical(
                self,
                "ComfyUI not reachable",
                f"Cannot connect to ComfyUI at {url}.\n\n"
                "Please start your ComfyUI server (or Docker container) and "
                "verify the URL in Settings before scanning.",
            )
            return

        exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".jfif"}
        files = [str(p) for p in Path(folder).rglob("*") if p.suffix.lower() in exts]
        if not files:
            QMessageBox.information(self, "No images", "No supported images found in that folder.")
            return

        self._scan_thread = ScanFolderThread(self.plugin, files, self)
        self._scan_thread.progress.connect(self._on_scan_progress)
        self._scan_thread.scan_finished.connect(self._on_scan_finished)

        self._scan_progress_bar.setRange(0, len(files))
        self._scan_progress_bar.setValue(0)
        self._scan_progress_frame.setVisible(True)
        self.scan_btn.setEnabled(False)
        self._scan_progress_label.setText(f"Scanning 0 / {len(files)} …")

        self._scan_thread.start()

    def _cancel_scan(self):
        if self._scan_thread:
            self._scan_thread.cancel_scan()

    def _on_scan_progress(self, done, total):
        self._scan_progress_bar.setValue(done)
        self._scan_progress_label.setText(f"Scanning {done} / {total} …")

    def _on_scan_finished(self, added, total, cancelled):
        self._scan_progress_frame.setVisible(False)
        self.scan_btn.setEnabled(True)
        msg = f"{'Cancelled — ' if cancelled else ''}Added {added} / {total} images."
        self.status_label.setText(msg)
        self._load_gallery()
        self._scan_thread = None
