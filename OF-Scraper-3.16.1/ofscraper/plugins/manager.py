import os
import json
import logging
import importlib.util
import re
from pathlib import Path
import traceback
import shutil
import sys
import platform
import subprocess
import threading
import time

from ofscraper.utils.paths.common import get_config_path
import ofscraper.utils.dates as dates_manager
import ofscraper.utils.config.data as config_data


def _sanitize_plugin_log_name(name: str) -> str:
    import re
    name = (name or "unknown").strip().lower()
    name = re.sub(r"[^a-z0-9._-]+", "_", name)
    return name.strip("._-") or "unknown"


def _plugin_log_path(config_path: Path | None, plugin_name: str) -> Path | None:
    if not config_path:
        return None
    base_log_dir = config_path.parent / "logging"
    profile = config_data.get_main_profile()
    log_date = dates_manager.getLogDate() or {}
    day = log_date.get("day", "unknown-day")
    now = log_date.get("now", "unknown-run")
    safe_name = _sanitize_plugin_log_name(plugin_name)
    if config_data.get_rotate_logs():
        log_dir = base_log_dir / f"{profile}_{day}" / "plugins"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / f"plugin-{safe_name}_{now}.log"
    log_dir = base_log_dir / "plugins"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"plugin-{safe_name}_{day}.log"

class PluginManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PluginManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.plugins = []
        self._loaded_plugin_ids: set[str] = set()
        self._plugin_loggers_configured: set[str] = set()
        self.log = logging.getLogger("ofscraper_plugins")

        config_path = get_config_path()
        if config_path:
            self.plugins_dir = config_path.parent / "plugins"
        else:
            self.plugins_dir = None

        # Threading event for daemon-mode post-scrape plugin coordination.
        # Set = no async work pending; cleared = a plugin is doing async work.
        self._scrape_complete_event = threading.Event()
        self._scrape_complete_event.set()
        self._has_pending_post_scrape = False

        self._initialized = True

    def _configure_plugin_logger(self, plugin_instance, metadata: dict):
        """Attach a dedicated file handler for an individual plugin."""
        plugin_name = metadata.get("name") or metadata.get("id") or "unknown"
        logger_name = f"ofscraper_plugin.{plugin_name}"
        if logger_name in self._plugin_loggers_configured:
            return

        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        try:
            log_path = _plugin_log_path(get_config_path(), plugin_name)
            if not log_path:
                return
            for handler in logger.handlers[:]:
                if isinstance(handler, logging.FileHandler):
                    try:
                        existing = Path(handler.baseFilename)
                    except Exception:
                        existing = None
                    if existing == log_path:
                        self._plugin_loggers_configured.add(logger_name)
                        plugin_instance.log = logger
                        return

            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            plugin_instance.log = logger
            self._plugin_loggers_configured.add(logger_name)
            self.log.info(f"Plugin log file ready: {log_path}")
        except Exception as e:
            self.log.warning(f"Failed to configure plugin logger for {plugin_name}: {e}")

    # ------------------------------------------------------------------ post-scrape coordination

    def pre_scrape_complete(self):
        """Call from the scraper thread BEFORE emitting scraping_finished.
        Clears the completion event so _daemon_wait() will pause until
        post_scrape_complete_dispatch() or signal_post_scrape_done() sets it."""
        self._has_pending_post_scrape = False
        self._scrape_complete_event.clear()

    def signal_post_scrape_working(self):
        """Call from on_scrape_complete when a plugin starts async work."""
        self._has_pending_post_scrape = True

    def signal_post_scrape_done(self):
        """Call when async post-scrape work finishes (sets the event)."""
        self._has_pending_post_scrape = False
        self._scrape_complete_event.set()

    def post_scrape_complete_dispatch(self):
        """Call from the GUI thread AFTER dispatch_event('on_scrape_complete').
        If no plugin registered async work, immediately sets the event so the
        daemon countdown is not blocked."""
        if not self._has_pending_post_scrape:
            self._scrape_complete_event.set()

    def wait_post_scrape_done(self, timeout: float = 300.0) -> bool:
        """Block until post-scrape async work completes or timeout expires.
        Returns True if the event was set within the timeout."""
        return self._scrape_complete_event.wait(timeout=timeout)

    # ------------------------------------------------------------------ discovery

    def discover_and_load(self):
        """Finds all valid plugins in the plugins directory and loads them."""
        if not self.plugins_dir or not self.plugins_dir.parent.exists():
            self.log.debug("Config directory not found, skipping plugin load.")
            return

        if not self.plugins_dir.exists():
            try:
                self.plugins_dir.mkdir(parents=True, exist_ok=True)
                self.log.info(f"Created plugins directory at {self.plugins_dir}")
            except Exception as e:
                self.log.warning(f"Failed to create plugins directory: {e}")
                return

        for entry in self.plugins_dir.iterdir():
            if entry.is_dir():
                self._load_plugin(entry)

    def _load_plugin(self, plugin_dir: Path):
        """Attempt to load a single plugin directory."""
        main_file = plugin_dir / "main.py"
        meta_file = plugin_dir / "metadata.json"

        if not main_file.exists():
            return

        # Guard against double-loading when discover_and_load() is called more
        # than once (e.g. once from main/open/load.py and once from main_window.py).
        if plugin_dir.name in self._loaded_plugin_ids:
            self.log.debug(f"Plugin {plugin_dir.name} already loaded, skipping.")
            return

        # Check for plugin_enabled flag in main.py
        try:
            with open(main_file, 'r', encoding='utf-8') as f:
                content = f.read()
                import re
                match = re.search(r'^plugin_enabled\s*=\s*([01])', content, re.MULTILINE)
                if match and match.group(1) == '0':
                    self.log.info(f"Skipping disabled plugin: {plugin_dir.name}")
                    return
        except Exception as e:
            self.log.warning(f"Could not read {main_file} to check enabled status: {e}")

        metadata = {}
        if meta_file.exists():
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
            except Exception as e:
                self.log.error(f"Failed to parse metadata.json in {plugin_dir.name}: {e}")

        metadata['id'] = plugin_dir.name

        try:
            import sys
            # Inject plugin-local deps/ into sys.path so packages installed via
            # --target (e.g. in Docker where the venv is not a persistent volume)
            # are found on every container start.
            _deps_dir = plugin_dir / "deps"
            if _deps_dir.is_dir():
                _deps_str = str(_deps_dir)
                if _deps_str not in sys.path:
                    sys.path.insert(0, _deps_str)
                # On Windows, PyTorch DLLs inside deps/ must also be registered
                # with os.add_dll_directory() — Python 3.8+ "safe DLL search"
                # does not automatically search subdirectories, causing
                # [WinError 1114] when torch/lib/c10.dll loads its dependencies.
                # IMPORTANT: os.add_dll_directory() returns a context manager; the
                # directory is removed from the search path when that object is GC'd,
                # so we must keep a reference alive on self for the process lifetime.
                if platform.system() == "Windows":
                    _torch_lib = _deps_dir / "torch" / "lib"
                    if _torch_lib.is_dir():
                        _torch_lib_str = str(_torch_lib)
                        # 1. Add to PATH so c10.dll's own internal LoadLibrary
                        #    calls (old-style search) can find sibling DLLs.
                        if _torch_lib_str.lower() not in os.environ.get("PATH", "").lower():
                            os.environ["PATH"] = _torch_lib_str + os.pathsep + os.environ.get("PATH", "")
                        # 2. Register with os.add_dll_directory for Python's
                        #    safe DLL search (Python 3.8+). Keep the context
                        #    object alive for the process lifetime.
                        if hasattr(os, "add_dll_directory"):
                            try:
                                _dll_ctx = os.add_dll_directory(_torch_lib_str)
                                if not hasattr(self, "_dll_directories"):
                                    self._dll_directories = []
                                self._dll_directories.append(_dll_ctx)
                            except Exception:
                                pass
                        # 3. ctypes-preload every DLL in torch/lib so Windows
                        #    returns the existing handle (no DllMain re-run)
                        #    when Python's extension importer later loads them.
                        #    This mirrors preload_for_windows_gui() and is the
                        #    step that actually prevents [WinError 1114].
                        import ctypes as _ctypes
                        import glob as _glob
                        for _dll in sorted(_glob.glob(os.path.join(_torch_lib_str, "*.dll"))):
                            try:
                                _ctypes.CDLL(_dll)
                            except OSError:
                                pass

            # Dynamically load the plugin directory as a package to support relative imports
            package_name = f"ofscraper_plugin_{plugin_dir.name}"

            init_file = plugin_dir / "__init__.py"
            if not init_file.exists():
                init_file.touch()

            spec = importlib.util.spec_from_file_location(package_name, str(init_file), submodule_search_locations=[str(plugin_dir)])
            if spec and spec.loader:
                package_module = importlib.util.module_from_spec(spec)
                sys.modules[package_name] = package_module
                spec.loader.exec_module(package_module)

                # Now dynamically load the main module inside the package
                main_name = f"{package_name}.main"
                main_spec = importlib.util.spec_from_file_location(main_name, str(main_file))
                if main_spec and main_spec.loader:
                    module = importlib.util.module_from_spec(main_spec)
                    sys.modules[main_name] = module
                    main_spec.loader.exec_module(module)

                    # Look for the 'Plugin' class
                    if hasattr(module, 'Plugin'):
                        plugin_instance = module.Plugin(metadata=metadata, plugin_dir=str(plugin_dir))
                        self._configure_plugin_logger(plugin_instance, metadata)
                        self.plugins.append(plugin_instance)
                        self._loaded_plugin_ids.add(plugin_dir.name)
                        self.log.info(f"Loaded plugin: {metadata.get('name', plugin_dir.name)}")

                        # Fire on_load
                        self._safe_call(plugin_instance, "on_load")
                    else:
                        self.log.error(f"Plugin {plugin_dir.name} is missing the 'Plugin' class in main.py")
        except ModuleNotFoundError as e:
            self.log.error(f"Failed to load plugin {plugin_dir.name}: Missing package '{e.name}'")
            req_file = plugin_dir / "requirements.txt"
            if req_file.exists():
                hint = self._dependency_install_hint(str(req_file), plugin_dir=plugin_dir)
                self.log.warning(
                    "This plugin requires extra dependencies (%s). %s", e.name, hint
                )
                try:
                    from PyQt6.QtWidgets import QMessageBox, QApplication
                    if QApplication.instance():
                        plugin_name = metadata.get("name", plugin_dir.name)
                        plugin_logger = logging.getLogger(f"ofscraper_plugin.{plugin_name}")
                        try:
                            self._configure_plugin_logger(type("_TempPlugin", (), {"log": plugin_logger})(), metadata)
                        except Exception:
                            pass
                        try:
                            plugin_logger.warning("Missing dependency detected during plugin load: %s", e.name)
                        except Exception:
                            pass
                        dlg = QMessageBox()
                        dlg.setIcon(QMessageBox.Icon.Warning)
                        dlg.setWindowTitle("Plugin Missing Dependencies")
                        dlg.setText(
                            f"The plugin '{plugin_name}' could not be loaded because it is missing "
                            f"the '{e.name}' package."
                        )
                        dlg.setInformativeText("Install the plugin dependencies now?")
                        dlg.setDetailedText(
                            "Please install its dependencies by running:\n\n"
                            f"{hint}"
                        )
                        install_btn = dlg.addButton(
                            "Install Dependencies",
                            QMessageBox.ButtonRole.YesRole,
                        )
                        cancel_btn = dlg.addButton(QMessageBox.StandardButton.Cancel)
                        dlg.setDefaultButton(cancel_btn)

                        dlg.exec()
                        if dlg.clickedButton() == install_btn:
                            from PyQt6.QtCore import Qt
                            from PyQt6.QtWidgets import (
                                QDialog, QVBoxLayout, QLabel,
                                QPlainTextEdit, QProgressBar,
                            )
                            import threading
                            import queue as _queue

                            self.log.warning(
                                "Installing plugin dependencies for '%s' using: %s",
                                plugin_name,
                                hint,
                            )
                            try:
                                plugin_logger.info("Installing plugin dependencies using command: %s", hint)
                            except Exception:
                                pass

                            # Build a live-output install dialog.
                            install_dlg = QDialog()
                            install_dlg.setWindowTitle("Installing Plugin Dependencies")
                            install_dlg.setMinimumWidth(620)
                            install_dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
                            _layout = QVBoxLayout(install_dlg)
                            _layout.addWidget(QLabel(f"Installing dependencies for <b>{plugin_name}</b>…"))
                            _cmd_lbl = QLabel(hint)
                            _cmd_lbl.setWordWrap(True)
                            _layout.addWidget(_cmd_lbl)
                            _out_box = QPlainTextEdit()
                            _out_box.setReadOnly(True)
                            _out_box.setFixedHeight(220)
                            _out_box.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
                            _layout.addWidget(_out_box)
                            _pbar = QProgressBar()
                            _pbar.setRange(0, 0)  # indeterminate / busy
                            _layout.addWidget(_pbar)
                            install_dlg.show()
                            QApplication.processEvents()

                            t0 = time.time()
                            _out_queue: _queue.Queue = _queue.Queue()
                            _result: dict = {}

                            def _do_install():
                                code, out = self._run_dependency_install_command_live(
                                    hint, _out_queue
                                )
                                _result["code"] = code
                                _result["output"] = out

                            _t = threading.Thread(target=_do_install, daemon=True)
                            _t.start()
                            while _t.is_alive():
                                # Drain live output lines into the text box.
                                _lines = []
                                try:
                                    while True:
                                        _lines.append(_out_queue.get_nowait())
                                except _queue.Empty:
                                    pass
                                if _lines:
                                    _out_box.appendPlainText("".join(_lines).rstrip("\n"))
                                    sb = _out_box.verticalScrollBar()
                                    sb.setValue(sb.maximum())
                                QApplication.processEvents()
                                time.sleep(0.05)
                            _t.join()
                            # Drain any remaining output.
                            _lines = []
                            try:
                                while True:
                                    _lines.append(_out_queue.get_nowait())
                            except _queue.Empty:
                                pass
                            if _lines:
                                _out_box.appendPlainText("".join(_lines).rstrip("\n"))

                            code = _result.get("code", 1)
                            output = _result.get("output", "")
                            install_dlg.close()
                            elapsed = time.time() - t0

                            if code == 0:
                                self.log.warning(
                                    "Plugin dependency install completed in %.1fs for '%s'",
                                    elapsed,
                                    plugin_name,
                                )
                                try:
                                    plugin_logger.info("Plugin dependency install completed in %.1fs", elapsed)
                                    if output:
                                        plugin_logger.info("Dependency installer full output\n%s", output.rstrip())
                                except Exception:
                                    pass
                                # On Windows, torch/c10.dll must be loaded into
                                # the process BEFORE PyQt6/SIP initializes (see
                                # preload_for_windows_gui).  Since deps were just
                                # installed *after* the GUI launched, it is too
                                # late to preload them safely in this process.
                                # Attempting _load_plugin() here would let the
                                # module load (no top-level torch import) but the
                                # first real inference call would raise WinError
                                # 1114.  The safe fix is to ask for a restart so
                                # preload_for_windows_gui() can run first next
                                # time.
                                _needs_restart = platform.system() == "Windows" and (
                                    plugin_dir / "deps" / "torch" / "lib"
                                ).is_dir()
                                if _needs_restart:
                                    QMessageBox.information(
                                        None,
                                        "Restart Required",
                                        f"Dependencies installed successfully for '{plugin_name}'.\n\n"
                                        "Please restart OF-Scraper for the plugin to become active.\n\n"
                                        "(On Windows, PyTorch DLLs must be pre-loaded before the GUI "
                                        "starts. The plugin will work correctly after restarting.)",
                                    )
                                else:
                                    QMessageBox.information(
                                        None,
                                        "Plugin Dependencies Installed",
                                        f"Dependencies installed successfully for '{plugin_name}'.\n\nThe plugin will now be loaded.",
                                    )
                                    # Non-Windows or no torch: safe to reload in place.
                                    self._load_plugin(plugin_dir)
                            else:
                                out = (output or "").strip()
                                out = out[-8000:] if len(out) > 8000 else out
                                self.log.error(
                                    "Plugin dependency install FAILED (code=%s) for '%s' after %.1fs\n%s",
                                    code,
                                    plugin_name,
                                    elapsed,
                                    out,
                                )
                                QMessageBox.warning(
                                    None,
                                    "Dependency Install Failed",
                                    f"Install command failed with exit code {code}.\n\n{hint}\n\n{out}",
                                )
                except Exception:
                    pass
        except Exception as e:
            self.log.error(f"Failed to load plugin {plugin_dir.name}: {e}")
            self.log.debug(traceback.format_exc())

    def _dependency_install_hint(self, req_file: str, plugin_dir: Path | None = None) -> str:
        """
        Return a shell command hint that matches the user's environment.

        Packages are installed into <plugin_dir>/deps/ via --target so they
        persist across Docker container restarts (the plugin folder lives in a
        mounted volume, while /opt/venv does not).
        """
        req_file = str(req_file)

        # Build the --target flag pointing at the plugin-local deps directory.
        # This makes deps persist in the config volume across container restarts.
        if plugin_dir is not None:
            deps_dir = str(plugin_dir / "deps")
            target_flag = f" --target \"{deps_dir}\""
        else:
            target_flag = ""

        # IMPORTANT: keep this aligned with `patch_ofscraper_3.14.3_gui.py`'s
        # install-method detection (pip vs pipx vs uv). The patch checks whether
        # the *ofscraper package* is located inside a pipx/uv environment, not
        # just whether `uv` is on PATH.
        install_method = self._detect_install_method_for_ofscraper()

        if install_method == "uv":
            return f"uv pip install -r \"{req_file}\"{target_flag}"
        if install_method == "pipx":
            # Use a plugin-local virtualenv first so plugin dependencies are
            # isolated from the main pipx ofscraper environment.
            if plugin_dir is not None:
                plugin_python = self._ensure_plugin_venv(plugin_dir)
                if plugin_python:
                    return f'"{plugin_python}" -m pip install -r "{req_file}"{target_flag}'

            # If a host python with pip is available, prefer that next.
            import shutil
            import subprocess
            host_python = shutil.which("python3")
            if host_python:
                try:
                    probe = subprocess.run(
                        [host_python, "-m", "pip", "--version"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    if probe.returncode == 0:
                        return f'"{host_python}" -m pip install -r "{req_file}"{target_flag}'
                except Exception:
                    pass

            pip_path = self._pipx_venv_pip()
            if pip_path:
                return f'"{pip_path}" install -r "{req_file}"{target_flag}'

            return f'pipx runpip ofscraper install -r "{req_file}"{target_flag}'
        if install_method == "venv":
            # Plain virtualenv / Docker: use the venv's own pip executable.
            pip_path = self._venv_pip()
            if pip_path:
                return f"\"{pip_path}\" install -r \"{req_file}\"{target_flag}"
            import sys
            return f"\"{sys.executable}\" -m pip install -r \"{req_file}\"{target_flag}"
        if install_method == "pip":
            return f"pip install -r \"{req_file}\"{target_flag}"

        # Unknown: safest fallback.
        return f"python -m pip install -r \"{req_file}\"{target_flag}"

    def _run_dependency_install_command(self, command: str) -> tuple[int, str]:
        """
        Run the dependency install command and return (exit_code, combined output).
        """
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            return proc.returncode, out
        except Exception as e:
            return 1, str(e)

    def _run_dependency_install_command_live(self, command: str, out_queue, plugin_logger=None) -> tuple[int, str]:
        """
        Run the install command and stream each output line into out_queue so
        the UI can display live progress. Returns (exit_code, full_output).
        """
        try:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            all_lines = []
            for line in proc.stdout:
                out_queue.put(line)
                all_lines.append(line)
                if plugin_logger is not None:
                    try:
                        plugin_logger.info(line.rstrip())
                    except Exception:
                        pass
            proc.wait()
            return proc.returncode, "".join(all_lines)
        except Exception as e:
            msg = str(e)
            out_queue.put(msg + "\n")
            return 1, msg

    def _get_pipx_home(self) -> Path | None:
        env = os.environ.get("PIPX_HOME")
        if env:
            p = Path(env)
            if p.is_dir():
                return p
        home = Path.home()
        is_win = platform.system() == "Windows"
        if is_win:
            candidates = [
                home / "pipx",
                home / "AppData" / "Local" / "pipx",
                home / ".local" / "pipx",
            ]
        else:
            candidates = [
                home / ".local" / "share" / "pipx",
                home / ".local" / "pipx",
            ]
        for c in candidates:
            if c.is_dir():
                return c
        return None

    def _find_pipx_ofscraper_pkg(self) -> Path | None:
        pipx_home = self._get_pipx_home()
        if not pipx_home:
            return None
        venv_dir = pipx_home / "venvs" / "ofscraper"
        if not venv_dir.is_dir():
            return None
        matches = list(venv_dir.glob("**/site-packages/ofscraper/__main__.py"))
        if matches:
            return matches[0].parent
        return None

    def _get_uv_tool_dir(self) -> Path | None:
        env = os.environ.get("UV_TOOL_DIR")
        if env:
            p = Path(env)
            if p.is_dir():
                return p
        home = Path.home()
        is_win = platform.system() == "Windows"
        if is_win:
            appdata = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
            candidates = [
                Path(appdata) / "uv" / "data" / "tools",
                Path(appdata) / "uv" / "tools",
            ]
        else:
            xdg = os.environ.get("XDG_DATA_HOME", str(home / ".local" / "share"))
            candidates = [Path(xdg) / "uv" / "tools"]
        for c in candidates:
            if c.is_dir():
                return c
        return None

    def _find_uv_ofscraper_pkg(self) -> Path | None:
        uv_dir = self._get_uv_tool_dir()
        if not uv_dir:
            return None
        venv_dir = uv_dir / "ofscraper"
        if not venv_dir.is_dir():
            return None
        matches = list(venv_dir.glob("**/site-packages/ofscraper/__main__.py"))
        if matches:
            return matches[0].parent
        return None

    def _plugin_venv_dir(self, plugin_dir: Path) -> Path:
        return plugin_dir / ".deps_venv"

    def _plugin_venv_python(self, plugin_dir: Path) -> str | None:
        venv_dir = self._plugin_venv_dir(plugin_dir)
        candidates = [venv_dir / "bin" / "python", venv_dir / "Scripts" / "python.exe"]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    def _ensure_plugin_venv(self, plugin_dir: Path) -> str | None:
        python_path = self._plugin_venv_python(plugin_dir)
        if python_path:
            return python_path

        import shutil
        import subprocess
        import sys

        venv_dir = self._plugin_venv_dir(plugin_dir)
        host_python = shutil.which("python3") or sys.executable
        try:
            subprocess.run([host_python, "-m", "venv", str(venv_dir)], check=True, capture_output=True, text=True)
        except Exception:
            return None
        return self._plugin_venv_python(plugin_dir)

    def _detect_install_method_for_ofscraper(self) -> str:
        # Prefer pipx over uv because some systems have stale `ofscraper`
        # directories under uv tools, which would otherwise mislead the hint.
        if self._find_pipx_ofscraper_pkg():
            return "pipx"
        if self._find_uv_ofscraper_pkg():
            return "uv"
        # Detect plain virtualenv / Docker venv (sys.prefix != sys.base_prefix)
        import sys
        if sys.prefix != sys.base_prefix:
            return "venv"
        exe = shutil.which("ofscraper")
        if exe:
            exe_lower = str(exe).lower()
            if "uv" in exe_lower and "tools" in exe_lower:
                return "uv"
            if "pipx" in exe_lower:
                return "pipx"
        try:
            import ofscraper  # type: ignore

            if getattr(ofscraper, "__path__", None):
                return "pip"
        except ImportError:
            pass
        return "unknown"

    def _venv_pip(self) -> str | None:
        """Return the pip executable inside the active virtualenv, or None."""
        import sys
        prefix = sys.prefix
        is_win = platform.system() == "Windows"
        candidates = (
            [os.path.join(prefix, "Scripts", "pip.exe"),
             os.path.join(prefix, "Scripts", "pip")]
            if is_win
            else [os.path.join(prefix, "bin", "pip"),
                  os.path.join(prefix, "bin", "pip3")]
        )
        for p in candidates:
            if os.path.isfile(p):
                return p
        return None

    def _pipx_venv_pip(self) -> str | None:
        pipx_home = self._get_pipx_home()
        if not pipx_home:
            return None
        venv_dir = pipx_home / "venvs" / "ofscraper"
        pip_path = venv_dir / "bin" / "pip"
        if pip_path.exists():
            return str(pip_path)
        pip_path3 = venv_dir / "bin" / "pip3"
        if pip_path3.exists():
            return str(pip_path3)
        pip_path_win = venv_dir / "Scripts" / "pip.exe"
        if pip_path_win.exists():
            return str(pip_path_win)
        return None

    def preload_for_windows_gui(self) -> None:
        """Pre-load plugin DLLs on Windows before PyQt6 is imported.

        PyQt6.QtCore's Python extension module (SIP initialization) modifies
        process-level state in a way that causes torch/c10.dll's DllMain to
        fail with WinError 1114.  Pre-loading the torch DLLs *before* PyQt6
        is imported avoids the conflict because the DLLs are already resident
        in the process when DllMain would otherwise be called later.

        This must be called from ofscraper's startup (managers/manager.py)
        BEFORE 'from ofscraper.gui.app import launch_gui' which triggers the
        first PyQt6 import.
        """
        if platform.system() != "Windows":
            return
        if not self.plugins_dir or not self.plugins_dir.is_dir():
            return
        import ctypes
        import glob as _glob
        for plugin_dir in self.plugins_dir.iterdir():
            if not plugin_dir.is_dir():
                continue
            torch_lib = plugin_dir / "deps" / "torch" / "lib"
            if not torch_lib.is_dir():
                continue
            torch_lib_str = str(torch_lib)
            # Add to PATH so DLL's own internal LoadLibraryW calls find siblings
            if torch_lib_str.lower() not in os.environ.get("PATH", "").lower():
                os.environ["PATH"] = torch_lib_str + os.pathsep + os.environ.get("PATH", "")
            # Also register with os.add_dll_directory for Python's restricted DLL search
            try:
                _ctx = os.add_dll_directory(torch_lib_str)
                if not hasattr(self, "_dll_directories"):
                    self._dll_directories = []
                self._dll_directories.append(_ctx)
            except Exception:
                pass
            # Pre-load all DLLs in dependency order (alphabetical puts c10 before torch_cpu)
            for dll_path in sorted(_glob.glob(os.path.join(torch_lib_str, "*.dll"))):
                try:
                    ctypes.CDLL(dll_path)
                except OSError:
                    pass

    def dispatch_event(self, event_name: str, *args, **kwargs):
        """Dispatch an event to all loaded plugins."""
        results = []
        for plugin in self.plugins:
            res = self._safe_call(plugin, event_name, *args, **kwargs)
            if res is not None:
                results.append(res)
        return results

    def _safe_call(self, plugin, method_name, *args, **kwargs):
        """Safely execute a plugin method without crashing the main application."""
        if hasattr(plugin, method_name):
            try:
                method = getattr(plugin, method_name)
                return method(*args, **kwargs)
            except Exception as e:
                name = plugin.metadata.get('name', plugin.plugin_dir)
                self.log.error(f"Plugin '{name}' crashed in {method_name}: {e}")
                self.log.debug(traceback.format_exc())
        return None

    # ------------------------------------------------------------------ GUI plugin inventory

    @staticmethod
    def read_enabled_flag(main_file: Path) -> bool:
        """Return True unless main.py has ``plugin_enabled = 0`` at line start."""
        try:
            content = main_file.read_text(encoding="utf-8")
            match = re.search(r"^plugin_enabled\s*=\s*([01])", content, re.MULTILINE)
            if match and match.group(1) == "0":
                return False
        except Exception:
            pass
        return True

    def set_enabled_flag(self, plugin_id: str, enabled: bool) -> bool:
        """Write ``plugin_enabled = 0|1`` into the plugin's main.py. Restart required."""
        if not self.plugins_dir:
            return False
        plugin_dir = self.plugins_dir / str(plugin_id)
        main_file = plugin_dir / "main.py"
        if not main_file.is_file():
            return False
        try:
            content = main_file.read_text(encoding="utf-8")
            new_val = "1" if enabled else "0"
            if re.search(r"^plugin_enabled\s*=\s*[01]", content, re.MULTILINE):
                content = re.sub(
                    r"^plugin_enabled\s*=\s*[01]",
                    f"plugin_enabled = {new_val}",
                    content,
                    count=1,
                    flags=re.MULTILINE,
                )
            else:
                content = f"plugin_enabled = {new_val}\n" + content
            main_file.write_text(content, encoding="utf-8")
            self.log.info(
                f"Plugin '{plugin_id}' marked "
                f"{'enabled' if enabled else 'disabled'} on disk"
            )
            return True
        except Exception as e:
            self.log.error(f"Failed to update plugin_enabled for {plugin_id}: {e}")
            return False

    def get_loaded_plugin(self, plugin_id: str):
        """Return the loaded plugin instance for *plugin_id*, or None."""
        for plugin in self.plugins:
            meta_id = (plugin.metadata or {}).get("id")
            dir_id = Path(str(plugin.plugin_dir)).name
            if meta_id == plugin_id or dir_id == plugin_id:
                return plugin
        return None

    def load_plugin_now(self, plugin_id: str, main_window=None) -> tuple[bool, str]:
        """Import and activate one enabled plugin without restarting the app.

        Runs ``on_load`` (via ``_load_plugin``) and ``on_ui_setup`` when
        *main_window* is provided. Does not unload plugins.
        """
        plugin_id = str(plugin_id or "").strip()
        if not plugin_id:
            return False, "No plugin selected."
        if not self.plugins_dir:
            return False, "Plugins folder is unavailable."

        plugin_dir = self.plugins_dir / plugin_id
        main_file = plugin_dir / "main.py"
        if not main_file.is_file():
            return False, f"Plugin folder missing main.py: {plugin_id}"

        if plugin_id in self._loaded_plugin_ids:
            return False, f"Plugin '{plugin_id}' is already loaded."

        if not self.read_enabled_flag(main_file):
            return (
                False,
                f"Plugin '{plugin_id}' is disabled. Enable it first, then Load now.",
            )

        before = set(self._loaded_plugin_ids)
        try:
            self._load_plugin(plugin_dir)
        except Exception as e:
            self.log.error(f"load_plugin_now failed for {plugin_id}: {e}")
            self.log.debug(traceback.format_exc())
            return False, f"Load failed: {e}"

        if plugin_id not in self._loaded_plugin_ids:
            return (
                False,
                f"Plugin '{plugin_id}' did not load "
                "(check logs — often missing dependencies or no Plugin class).",
            )

        plugin = self.get_loaded_plugin(plugin_id)
        if plugin is None:
            return False, f"Plugin '{plugin_id}' loaded but instance not found."

        # Only call UI setup for this newly loaded plugin (avoid re-running others).
        if main_window is not None and plugin_id not in before:
            try:
                self._safe_call(plugin, "on_ui_setup", main_window)
            except Exception as e:
                return (
                    True,
                    f"Loaded '{plugin_id}', but on_ui_setup failed: {e}",
                )

        name = (plugin.metadata or {}).get("name") or plugin_id
        return True, f"Loaded plugin: {name}"

    def _purge_plugin_modules(self, plugin_id: str) -> None:
        """Drop dynamically imported plugin modules so Load now can re-import."""
        package_name = f"ofscraper_plugin_{plugin_id}"
        doomed = [
            key
            for key in list(sys.modules)
            if key == package_name or key.startswith(package_name + ".")
        ]
        for key in doomed:
            try:
                del sys.modules[key]
            except Exception:
                pass

    def _teardown_plugin_ui(self, plugin, plugin_id: str, main_window) -> None:
        """Best-effort removal of GUI pieces added by on_ui_setup."""
        if main_window is None:
            return
        # Preferred hook for plugins that know their page ids.
        if hasattr(plugin, "on_ui_teardown"):
            self._safe_call(plugin, "on_ui_teardown", main_window)

        remove = getattr(main_window, "_remove_page", None)
        if not callable(remove):
            return

        page_ids = set()
        meta = plugin.metadata or {}
        for candidate in (
            plugin_id,
            meta.get("id"),
            meta.get("page_id"),
            getattr(plugin, "_page_id", None),
            getattr(plugin, "page_id", None),
        ):
            if candidate:
                page_ids.add(str(candidate))
        # Common attrs used by bundled / example plugins.
        for attr in ("btn", "gui", "_page"):
            obj = getattr(plugin, attr, None)
            if obj is None:
                continue
            # If the widget is still in the stack map, find its id.
            pages = getattr(main_window, "_pages", None) or {}
            for pid, widget in list(pages.items()):
                if widget is obj:
                    page_ids.add(str(pid))

        for pid in page_ids:
            try:
                remove(pid)
            except Exception as e:
                self.log.debug(f"UI teardown remove_page({pid}) failed: {e}")

        # Drop dangling refs plugins often keep.
        for attr in ("btn", "gui", "_page"):
            if hasattr(plugin, attr):
                try:
                    setattr(plugin, attr, None)
                except Exception:
                    pass

    def unload_plugin_now(self, plugin_id: str, main_window=None) -> tuple[bool, str]:
        """Deactivate one loaded plugin without restarting the app.

        Calls ``on_ui_teardown`` / best-effort UI removal, then ``on_unload``,
        removes the instance from the manager, and purges import cache so
        ``load_plugin_now`` can load a fresh copy later.
        """
        plugin_id = str(plugin_id or "").strip()
        if not plugin_id:
            return False, "No plugin selected."

        plugin = self.get_loaded_plugin(plugin_id)
        if plugin is None:
            return False, f"Plugin '{plugin_id}' is not loaded."

        name = (plugin.metadata or {}).get("name") or plugin_id
        try:
            self._teardown_plugin_ui(plugin, plugin_id, main_window)
        except Exception as e:
            self.log.warning(f"UI teardown for '{plugin_id}' raised: {e}")
            self.log.debug(traceback.format_exc())

        try:
            self._safe_call(plugin, "on_unload")
        except Exception as e:
            self.log.warning(f"on_unload for '{plugin_id}' raised: {e}")
            self.log.debug(traceback.format_exc())

        self.plugins = [
            p
            for p in self.plugins
            if not (
                ((p.metadata or {}).get("id") == plugin_id)
                or Path(str(p.plugin_dir)).name == plugin_id
            )
        ]
        self._loaded_plugin_ids.discard(plugin_id)
        self._purge_plugin_modules(plugin_id)

        self.log.info(f"Unloaded plugin: {name}")
        return True, f"Unloaded plugin: {name}"

    def list_installed_plugins(self) -> list[dict]:
        """Scan plugins_dir for installable plugins (GUI inventory)."""
        results: list[dict] = []
        if not self.plugins_dir:
            return results
        try:
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        if not self.plugins_dir.is_dir():
            return results

        loaded_ids = set(self._loaded_plugin_ids)
        loaded_meta = {
            (p.metadata.get("id") or Path(str(p.plugin_dir)).name): p.metadata
            for p in self.plugins
        }

        for entry in sorted(self.plugins_dir.iterdir(), key=lambda p: p.name.lower()):
            if not entry.is_dir():
                continue
            main_file = entry / "main.py"
            if not main_file.is_file():
                continue
            plugin_id = entry.name
            enabled = self.read_enabled_flag(main_file)
            metadata: dict = {}
            meta_file = entry / "metadata.json"
            if meta_file.is_file():
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        metadata = json.load(f) or {}
                except Exception:
                    metadata = {}
            # Prefer live metadata when loaded.
            if plugin_id in loaded_meta:
                metadata = {**metadata, **(loaded_meta[plugin_id] or {})}
            metadata["id"] = plugin_id
            results.append(
                {
                    "id": plugin_id,
                    "name": metadata.get("name") or plugin_id,
                    "version": str(metadata.get("version") or ""),
                    "author": str(metadata.get("author") or ""),
                    "description": str(metadata.get("description") or ""),
                    "enabled": enabled,
                    "loaded": plugin_id in loaded_ids,
                    "path": str(entry),
                    "has_requirements": (entry / "requirements.txt").is_file(),
                }
            )
        return results


plugin_manager = PluginManager()
