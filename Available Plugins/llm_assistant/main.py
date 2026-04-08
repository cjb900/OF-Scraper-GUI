#Enabled 1 / Disabled 0 - Set this plugin as enabled - Default value 1
plugin_enabled = 0

import json
from pathlib import Path

from ofscraper.plugins.base import BasePlugin

_SETTINGS_FILE = "settings.json"


class Plugin(BasePlugin):
    """
    LLM Assistant — natural-language control panel for OF-Scraper GUI.

    Adds an "🤖 AI Assistant" sidebar button that opens a chat panel.
    The user types plain-English commands; a locally-embedded GGUF model
    (via llama-cpp-python) translates them into GUI actions.

    No Ollama, no cloud API, no extra services required.
    """

    def on_load(self):
        self.log.info("LLM Assistant plugin loaded")
        self.data_dir = (
            Path(self.plugin_dir) if self.plugin_dir else Path(__file__).parent
        )
        self._tab = None

        # Shared engine/binder — owned at Plugin level so all widgets
        # (tab + injected command bars) use the same loaded model.
        self.engine = None
        self.binder = None

        # Load saved model preference (written by ModelSelectDialog)
        self._saved_model_id       = self._load_saved_model_id()
        self._saved_model_filename = self._load_saved_model_filename()

        # _settings_existed: True only if settings have a GGUF filename AND
        # the model was fully downloaded (model_downloaded: true).
        # Old transformers-format settings (no model_filename) are treated as
        # unconfigured so the first-run dialog appears again.
        settings_data = self._load_settings()
        self._settings_existed = (
            (self.data_dir / _SETTINGS_FILE).exists()
            and bool(settings_data.get("model_downloaded", False))
            and bool(settings_data.get("model_filename"))
        )
        self._download_dialog = None  # holds reference to prevent GC

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _settings_path(self) -> Path:
        return self.data_dir / _SETTINGS_FILE

    def _load_settings(self) -> dict:
        try:
            p = self.data_dir / _SETTINGS_FILE
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _load_saved_model_id(self) -> str | None:
        data = self._load_settings()
        mid  = data.get("model_id") or None
        # Only valid if it has a GGUF filename (post-migration format)
        if mid and not data.get("model_filename"):
            return None
        return mid

    def _load_saved_model_filename(self) -> str | None:
        return self._load_settings().get("model_filename") or None

    def _write_settings(self, updates: dict):
        try:
            p    = self._settings_path()
            data = self._load_settings()
            data.update(updates)
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            self.log.warning("Could not write settings: %s", e)

    def _save_model_choice(self, model_id: str, model_filename: str):
        self._write_settings({"model_id": model_id, "model_filename": model_filename})
        self._saved_model_id       = model_id
        self._saved_model_filename = model_filename
        self.log.info("Saved model preference: %s / %s", model_id, model_filename)

    def _mark_model_downloaded(self):
        self._write_settings({"model_downloaded": True})
        self.log.info("Model marked as downloaded")

    # ------------------------------------------------------------------
    # GUI setup
    # ------------------------------------------------------------------

    def on_ui_setup(self, main_window):
        try:
            from PyQt6.QtCore import QTimer
            from PyQt6.QtWidgets import QFrame
            from .gui import (
                AssistantCommandBar,
                DepsInstallDialog,
                LLMAssistantTab,
                ModelDownloadDialog,
                ModelSelectDialog,
                _check_missing_deps,
            )
            from ofscraper.gui.widgets.styled_button import NavButton

            # ── Full chat tab ────────────────────────────────────────────
            self._tab = LLMAssistantTab(self, main_window, self.data_dir)
            main_window._add_page("llm_assistant", self._tab)

            btn = NavButton("🤖 AI Assistant")
            main_window._nav_group.addButton(btn)
            main_window._nav_buttons["llm_assistant"] = btn

            nav_layout = main_window._nav_frame.layout()
            theme_idx  = nav_layout.indexOf(main_window._theme_btn)
            if theme_idx >= 0:
                nav_layout.insertWidget(theme_idx, btn)
            else:
                nav_layout.addWidget(btn)

            btn.clicked.connect(
                lambda checked: main_window._navigate("llm_assistant")
            )
            self.log.info("LLM Assistant tab attached to sidebar")

            # ── Inject compact command bars ──────────────────────────────
            def _inject_bar(page, attr_name: str):
                layout = page.layout() if page else None
                if layout is None:
                    self.log.warning(
                        "LLM Assistant: could not inject bar into %s (no layout)",
                        attr_name,
                    )
                    return
                bar = AssistantCommandBar(self, parent=page)
                sep = QFrame(parent=page)
                sep.setFrameShape(QFrame.Shape.HLine)
                layout.insertWidget(0, sep)
                layout.insertWidget(0, bar)
                self.log.info("LLM Assistant bar injected into %s", attr_name)

            action_page = getattr(main_window, "action_page", None)
            area_page   = getattr(main_window, "area_page",   None)

            if action_page:
                _inject_bar(action_page, "action_page")
            else:
                self.log.warning("LLM Assistant: action_page not found, bar not injected")

            if area_page:
                _inject_bar(area_page, "area_page")
            else:
                self.log.warning("LLM Assistant: area_page not found, bar not injected")

            # ── Auto-load model if previously downloaded ─────────────────
            if self._settings_existed and self._saved_model_id:
                def _auto_load():
                    try:
                        if self._tab and not getattr(
                            getattr(self, "engine", None), "is_loaded", False
                        ):
                            self.log.info(
                                "Auto-loading cached model: %s", self._saved_model_id
                            )
                            self._tab._on_load_model()
                    except Exception as exc:
                        self.log.error("Auto-load failed: %s", exc)

                QTimer.singleShot(1500, _auto_load)

            # ── First-run model selection dialog ─────────────────────────
            if not self._settings_existed:
                def _show_model_dialog():
                    try:
                        dlg = ModelSelectDialog(
                            current_model_id=self._saved_model_id or "",
                            parent=main_window,
                        )
                        if not dlg.exec():
                            return   # user clicked Skip for Now

                        chosen_id       = dlg.selected_model_id
                        chosen_filename = dlg.selected_model_filename
                        self._save_model_choice(chosen_id, chosen_filename)

                        # Sync the combo in the main tab
                        if self._tab and hasattr(self._tab, "_model_combo"):
                            combo = self._tab._model_combo
                            for i in range(combo.count()):
                                data = combo.itemData(i)
                                if isinstance(data, dict) and data.get("id") == chosen_id:
                                    combo.setCurrentIndex(i)
                                    break

                        self.log.info(
                            "Model preference saved from first-run dialog: %s / %s",
                            chosen_id, chosen_filename,
                        )

                        # ── Step 2: check / install Python deps ──────────
                        missing = _check_missing_deps()
                        if missing:
                            self.log.info("Missing deps: %s — showing install dialog", missing)
                            deps_dlg = DepsInstallDialog(
                                missing_packages=missing,
                                parent=main_window,
                            )
                            accepted = deps_dlg.exec()
                            self.log.info("Deps dialog closed: accepted=%s success=%s",
                                     accepted, deps_dlg.was_successful())
                            if not accepted:
                                # User cancelled — settings already saved so
                                # the first-run dialog won't re-appear, but
                                # model_downloaded stays False so on next launch
                                # it will proceed straight to deps+download.
                                self.log.info(
                                    "Deps install skipped; will retry on next launch"
                                )
                                return

                        # ── Step 3: download / load the model ────────────
                        self.log.info(
                            "Launching model download dialog: %s / %s",
                            chosen_id, chosen_filename,
                        )

                        def _on_dl_done():
                            self._mark_model_downloaded()
                            if self._tab:
                                try:
                                    self._tab._on_load_done()
                                except Exception:
                                    pass

                        try:
                            # Store on self to prevent GC (show() is non-blocking)
                            self._download_dialog = ModelDownloadDialog(
                                self, chosen_id, chosen_filename, main_window,
                                on_done=_on_dl_done,
                                parent=main_window,
                            )
                            self._download_dialog.show()
                            self._download_dialog.start()
                        except Exception as dl_exc:
                            self.log.error("Could not launch model download dialog: %s", dl_exc)

                    except Exception as exc:
                        self.log.error("First-run dialog error: %s", exc, exc_info=True)

                QTimer.singleShot(800, _show_model_dialog)

        except Exception as e:
            self.log.error("Failed to attach LLM Assistant GUI: %s", e)

    def on_unload(self):
        if self._tab:
            try:
                self._tab.cleanup()
            except Exception:
                pass
