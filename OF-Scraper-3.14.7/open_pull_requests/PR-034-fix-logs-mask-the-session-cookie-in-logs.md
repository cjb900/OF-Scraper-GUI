# PR #34: fix(logs): mask the session cookie in logs

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/34
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/log-privacy` → `main`
- **Created:** 2026-11-06T22:20:55Z  ·  **Updated:** 2026-11-07T00:03:20Z
- **Draft:** False
- **Changes:** 14 files, +787 / -28

## Description

**What was broken:**
- The `sess` cookie was written to the debug log in full.
- The GUI's own log handlers (console and Verbose Log) didn't mask anything.
- A log line with a stray markup tag was dropped.

**What was fixed:**
- The session value is masked as `{sess}` everywhere, including the GUI console and the Verbose Log.
- The home-folder rule runs last.
- The PSSH, username and display name are escaped.
- Broken-markup lines are kept as plain text.

With Privacy mode off, the GUI console now also hides the home folder, username and user id.

Tested: 52 new tests; full suite 904 passed, 11 skipped. Patched installs get this once #32 is merged and the patch rebuilt.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/classes/of/media.py`
- `OF-Scraper-3.14.7/ofscraper/data/api/me.py`
- `OF-Scraper-3.14.7/ofscraper/gui/app.py`
- `OF-Scraper-3.14.7/ofscraper/gui/main_window.py`
- `OF-Scraper-3.14.7/ofscraper/gui/utils/privacy_mode.py`
- `OF-Scraper-3.14.7/ofscraper/gui/utils/workflow.py`
- `OF-Scraper-3.14.7/ofscraper/utils/auth/file.py`
- `OF-Scraper-3.14.7/ofscraper/utils/logs/classes/classes.py`
- `OF-Scraper-3.14.7/ofscraper/utils/logs/stdout.py`
- `OF-Scraper-3.14.7/ofscraper/utils/logs/utils/sensitive.py`
- `OF-Scraper-3.14.7/test/unit/test_gui_log_handlers_mask_sess.py`
- `OF-Scraper-3.14.7/test/unit/test_gui_log_stray_markup.py`
- `OF-Scraper-3.14.7/test/unit/test_log_stray_markup.py`
- `OF-Scraper-3.14.7/test/unit/test_sess_cookie_masked.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/classes/of/media.py b/OF-Scraper-3.14.7/ofscraper/classes/of/media.py
index f287cb3..7a0fd24 100644
--- a/OF-Scraper-3.14.7/ofscraper/classes/of/media.py
+++ b/OF-Scraper-3.14.7/ofscraper/classes/of/media.py
@@ -683,7 +683,11 @@ async def mpd_audio_helper(self, mpd_obj=None):
         for prot in adapt_set.content_protections:
             if prot.value is None:
                 kId = prot.pssh[0].pssh
-                sensitive.add_sensitive_pattern(kId, "pssh_code")
+                # escaped: a base64 PSSH can hold "+" and "/", which as a raw
+                # regex would stop matching itself or break every log line
+                sensitive.add_sensitive_pattern(
+                    re.compile(re.escape(str(kId))), "pssh_code"
+                )
                 break
 
         origname = f"{selected_repr.base_urls[0].base_url_value}"
diff --git a/OF-Scraper-3.14.7/ofscraper/data/api/me.py b/OF-Scraper-3.14.7/ofscraper/data/api/me.py
index cc882dc..71f9bd0 100644
--- a/OF-Scraper-3.14.7/ofscraper/data/api/me.py
+++ b/OF-Scraper-3.14.7/ofscraper/data/api/me.py
@@ -12,6 +12,7 @@
 """
 
 import logging
+import re
 import traceback
 
 import ofscraper.managers.manager as manager
@@ -21,6 +22,18 @@
 log = logging.getLogger("shared")
 
 
+def _name_pattern(value):
+    """Mask pattern for a username or display name.
+
+    The display name is free text, so it's escaped: "Jane (VIP)" or "A+B" as a
+    raw regex wouldn't match itself, and an unbalanced "(" broke every log
+    line. The lookarounds work like the old \\b, also for names that start or
+    end with a symbol.
+    """
+    e = re.escape(str(value))
+    return f"{e} | {e}|(?<!\\w){e}(?!\\w)"
+
+
 def scrape_user():
     with manager.Manager.session.get_ofsession() as c:
         return _scraper_user_helper(c)
@@ -39,14 +52,15 @@ def _scraper_user_helper(c):
                 )
             if data.get("isAuth"):
                 sensitive.add_sensitive_pattern(data["id"], "userid")
-                sensitive.add_sensitive_pattern(
-                    f"{data['username']} | {data['username']}|\\b{data['username']}\\b",
-                    "username",
-                )
-                sensitive.add_sensitive_pattern(
-                    f"{data['name']} | {data['name']}|\\b{data['name']}\\b",
-                    "name",
-                )
+                # an empty value would match every space or word edge
+                if data.get("username"):
+                    sensitive.add_sensitive_pattern(
+                        _name_pattern(data["username"]), "username"
+                    )
+                if data.get("name"):
+                    sensitive.add_sensitive_pattern(
+                        _name_pattern(data["name"]), "name"
+                    )
 
     except Exception as E:
         log.traceback_(E)
diff --git a/OF-Scraper-3.14.7/ofscraper/gui/app.py b/OF-Scraper-3.14.7/ofscraper/gui/app.py
index cf96abf..888cd85 100644
--- a/OF-Scraper-3.14.7/ofscraper/gui/app.py
+++ b/OF-Scraper-3.14.7/ofscraper/gui/app.py
@@ -320,6 +320,22 @@ def enable_rhi_widgets(platform: str = sys.platform, docker: bool = False) -> No
         os.environ.setdefault("QT_WIDGETS_RHI", "1")
 
 
+def _make_gui_log_handler() -> GUILogHandler:
+    """Handler that forwards log lines to the GUI console.
+
+    Uses the same masking as the log file, so the session cookie and other
+    secrets are hidden in the console with Privacy mode on or off. The
+    handler strips Rich tags itself.
+    """
+    from ofscraper.utils.logs.classes.classes import SensitiveFormatter
+
+    handler = GUILogHandler()
+    handler.setFormatter(
+        SensitiveFormatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
+    )
+    return handler
+
+
 def launch_gui(manager=None):
     """Launch the PyQt6 GUI application."""
     # Tell Windows to use our own AppUserModelID so the taskbar shows our
@@ -446,10 +462,7 @@ def launch_gui(manager=None):
         log.warning(f"Could not install GUI interaction event filter: {e}")
 
     # Attach GUI log handler to forward logs to the console widget
-    gui_handler = GUILogHandler()
-    gui_handler.setFormatter(
-        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
-    )
+    gui_handler = _make_gui_log_handler()
     # Hook both loggers used by the scraper
     for logger_name in ["shared", "shared_other"]:
         target_logger = logging.getLogger(logger_name)
diff --git a/OF-Scraper-3.14.7/ofscraper/gui/main_window.py b/OF-Scraper-3.14.7/ofscraper/gui/main_window.py
index d38fe1b..4e38725 100644
--- a/OF-Scraper-3.14.7/ofscraper/gui/main_window.py
+++ b/OF-Scraper-3.14.7/ofscraper/gui/main_window.py
@@ -868,11 +868,15 @@ def _apply_verbose_log(self, enable: bool):
                     log_dir.mkdir(parents=True, exist_ok=True)
                     log_path = log_dir / f"ofscraper_gui_verbose_{profile}_{timestamp}.log"
 
-                    fmt = r" %(asctime)s:[%(module)s.%(funcName)s:%(lineno)d]  %(message)s"
+                    # "\[" as in utils/logs/other.py: LogFileFormatter removes
+                    # Rich markup, and an unescaped "[" would drop the location
+                    fmt = r" %(asctime)s:\[%(module)s.%(funcName)s:%(lineno)d]  %(message)s"
                     stream = open(log_path, "a", encoding="utf-8")
                     fh = _logging.StreamHandler(stream)
                     fh.setLevel(_logging.DEBUG)
-                    fh.setFormatter(_logging.Formatter(fmt, "%Y-%m-%d %H:%M:%S"))
+                    # same formatter as the normal log file: masks the
+                    # session cookie and other secrets, strips Rich markup
+                    fh.setFormatter(_log_class.LogFileFormatter(fmt, "%Y-%m-%d %H:%M:%S"))
                     setattr(fh, _GUI_VERBOSE_TAG, True)
                     fh._gui_verbose_stream = stream
                     logger.addHandler(fh)
diff --git a/OF-Scraper-3.14.7/ofscraper/gui/utils/privacy_mode.py b/OF-Scraper-3.14.7/ofscraper/gui/utils/privacy_mode.py
index 65c0cd3..6c7fc54 100644
--- a/OF-Scraper-3.14.7/ofscraper/gui/utils/privacy_mode.py
+++ b/OF-Scraper-3.14.7/ofscraper/gui/utils/privacy_mode.py
@@ -266,7 +266,9 @@ def _known_model_patterns():
         name_re = re.compile(rf"(?i)(?<![{_NAME_EDGE}])(?:{alt})(?![{_NAME_EDGE}])")
     if ids:
         alt = "|".join(sorted(ids, key=len, reverse=True))
-        id_re = re.compile(rf"(?<!\d)(?:{alt})(?!\d)")
+        # not next to a letter or digit, so an id inside a longer token
+        # (such as the session cookie value) isn't cut out of it
+        id_re = re.compile(rf"(?<![0-9A-Za-z])(?:{alt})(?![0-9A-Za-z])")
     _KNOWN_CACHE.update(key=key, names=name_re, ids=id_re)
     return name_re, id_re
 
@@ -288,6 +290,9 @@ def redact_log_message(message: str) -> str:
     """Extra redaction applied to GUI console lines when privacy mode is on."""
     if not is_privacy_mode() or not message:
         return message
+    # Model names and ids first: the mask table's broad rules (home folder
+    # name anywhere, the user's own id) would otherwise rewrite part of a
+    # creator name so the name rule no longer matches it.
     out = redact_known_models(str(message))
     out = redact_status_message(out)
     try:
diff --git a/OF-Scraper-3.14.7/ofscraper/gui/utils/workflow.py b/OF-Scraper-3.14.7/ofscraper/gui/utils/workflow.py
index b53459b..51c4206 100644
--- a/OF-Scraper-3.14.7/ofscraper/gui/utils/workflow.py
+++ b/OF-Scraper-3.14.7/ofscraper/gui/utils/workflow.py
@@ -476,13 +476,22 @@ def _strip_rich_stdout_handlers():
     Rich console I/O from download worker threads has caused Windows access
     violations mid-scrape (faulthandler cut off inside ``logging.flush``).
     GUI mode uses the Qt console bridge instead.
+
+    Subclasses count too: the terminal handlers are ``SafeRichHandler``,
+    which lives in ofscraper, not in the rich package.
     """
+    from rich.logging import RichHandler
+
     for name in ("shared", "shared_other"):
         lg = logging.getLogger(name)
         for h in list(lg.handlers):
             cls_name = type(h).__name__
             mod = getattr(type(h), "__module__", "") or ""
-            if cls_name == "RichHandler" or mod.startswith("rich"):
+            if (
+                isinstance(h, RichHandler)
+                or cls_name == "RichHandler"
+                or mod.startswith("rich")
+            ):
                 try:
                     lg.removeHandler(h)
                     h.close()
@@ -585,8 +594,11 @@ def _install_gui_log_handler():
     # Level 11 = TRACEBACK_ (DEBUG+1) — catches exceptions logged via
     # log.traceback_() which the scraper uses for all error reporting.
     _gui_log_handler.setLevel(logging.DEBUG + 1)
+    from ofscraper.utils.logs.classes.classes import SensitiveFormatter
+
+    # masks the session cookie and other secrets, with Privacy mode on or off
     _gui_log_handler.setFormatter(
-        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
+        SensitiveFormatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
     )
     logger = logging.getLogger("shared_other")
     logger.addHandler(_gui_log_handler)
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/auth/file.py b/OF-Scraper-3.14.7/ofscraper/utils/auth/file.py
index 3db9de9..2adfc15 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/auth/file.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/auth/file.py
@@ -13,6 +13,7 @@
 
 import json
 import logging
+import re
 
 from rich.console import Console
 
@@ -21,6 +22,7 @@
 import ofscraper.utils.auth.utils.error as auth_error
 import ofscraper.utils.auth.utils.dict as auth_dict
 import ofscraper.utils.paths.common as common_paths
+import ofscraper.utils.logs.utils.sensitive as sensitive
 console = Console()
 
 
@@ -52,9 +54,27 @@ def read_auth():
             if result =="quit":
                 logging.getLogger("shared").info("unable to read auth file")
                 quit()
+    hide_secrets(auth)
     return auth
 
 
+MIN_SECRET_LENGTH = 8
+
+
+def hide_secrets(auth):
+    """Mask the session cookie wherever it appears in a log line.
+
+    Request headers are logged when a request fails, and the cookie header
+    holds ``sess=<value>``. Registering the value itself covers every form it
+    is logged in (cookie header, dict repr, JSON).
+    """
+    sess = auth.get("sess") if isinstance(auth, dict) else None
+    # a real session value is long; a stray short one (e.g. a placeholder)
+    # would mask ordinary words in every log line
+    if sess and len(str(sess)) >= MIN_SECRET_LENGTH:
+        sensitive.add_sensitive_pattern(re.compile(re.escape(str(sess))), "{sess}")
+
+
 def edit_auth():
     """
     Opens the auth editing menu, handling errors interactively.
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/logs/classes/classes.py b/OF-Scraper-3.14.7/ofscraper/utils/logs/classes/classes.py
index 78abe39..f79bd7d 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/logs/classes/classes.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/logs/classes/classes.py
@@ -1,11 +1,39 @@
 import logging
 import re
+from rich.errors import MarkupError
+from rich.logging import RichHandler
 from rich.text import Text
 
 # Assumes you have this module for getting sensitive patterns
 import ofscraper.utils.logs.utils.sensitive as sensitive
 
 
+def _unescape(t: str) -> str:
+    # What Rich would have done with "\[" escapes
+    return re.sub(r"\\(\[)", r"\1", t)
+
+
+def strip_markup(t: str) -> str:
+    """Plain text of a Rich-markup string; the text as is (escapes removed) if
+    the markup is broken (e.g. a stray closing tag), so the line is still
+    logged."""
+    try:
+        return Text.from_markup(t).plain
+    except MarkupError:
+        return _unescape(t)
+
+
+class SafeRichHandler(RichHandler):
+    """RichHandler that prints a line with broken markup as plain text instead
+    of dropping it."""
+
+    def render_message(self, record, message):
+        try:
+            return super().render_message(record, message)
+        except MarkupError:
+            return Text(_unescape(message))
+
+
 class TraceBackOnly(logging.Filter):
     """A filter to only allow log records with a specific traceback level."""
 
@@ -81,7 +109,7 @@ def _filter(self, s: str) -> str:  # Added 'self'
         t = re.sub(r"\[code[^\]]*](.*?)\[/code[^\]]*]", r"`\1`", t, flags=re.IGNORECASE)
 
         # --- Cleanup and Final Touches ---
-        t = Text.from_markup(t).plain  # Handle any lingering markup entities
+        t = strip_markup(t)  # Handle any lingering markup entities
         t = re.sub(r" +", " ", t)  # Consolidate multiple spaces
         t = re.sub(r"\*\*+", "**", t)  # Fix cases like "****"
         t = re.sub(r"__+", "__", t)
@@ -101,4 +129,4 @@ def _filter(self, s: str) -> str:  # Added 'self'
         # First, apply the parent's sensitive data filtering
         t = super()._filter(s)
         # Then, strip all rich markup for a plain text representation
-        return Text.from_markup(t).plain
+        return strip_markup(t)
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/logs/stdout.py b/OF-Scraper-3.14.7/ofscraper/utils/logs/stdout.py
index d2f0787..2d7fd72 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/logs/stdout.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/logs/stdout.py
@@ -1,7 +1,5 @@
 # logs stdout logs via a shared queue
 
-from rich.logging import RichHandler
-
 import ofscraper.utils.console as console
 import ofscraper.utils.logs.classes.classes as log_class
 from ofscraper.utils.logs.classes.handlers.text import TextHandler
@@ -19,7 +17,7 @@ def add_stdout_handler(log, clear=True, rich_array=None):
     log.setLevel(1)
     log_helpers.addtraceback()
     log_helpers.addtrace()
-    sh = RichHandler(
+    sh = log_class.SafeRichHandler(
         markup=True,
         tracebacks_show_locals=True,
         show_time=False,
@@ -36,7 +34,7 @@ def add_stdout_handler(log, clear=True, rich_array=None):
     log.addHandler(tx)
 
     if settings.get_settings().output_level in {"DEBUG"}:
-        sh2 = RichHandler(
+        sh2 = log_class.SafeRichHandler(
             rich_tracebacks=True,
             console=console.get_shared_console(),
             markup=True,
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/logs/utils/sensitive.py b/OF-Scraper-3.14.7/ofscraper/utils/logs/utils/sensitive.py
index e769190..40e1acf 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/logs/utils/sensitive.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/logs/utils/sensitive.py
@@ -38,7 +38,13 @@ def getSenstiveDict() -> dict:
     """
     Returns a combined dictionary of default, user-added, and dynamic patterns.
     """
+    # Dicts keep insertion order, which is the order they're applied in:
+    # built-in rules, then patterns added during the session (exact values
+    # such as the session cookie or user id), then the home folder name last.
+    # The home folder name is short and could otherwise rewrite part of a
+    # secret so it no longer matches.
     combined_patterns = _DEFAULT_PATTERNS.copy()
+    combined_patterns.update(_USER_ADDED_PATTERNS)
 
     # --- Add Dynamic Patterns ---
     # These are generated based on the current user's specific info.
@@ -47,9 +53,6 @@ def getSenstiveDict() -> dict:
     profile_dir = paths.get_username()
     if profile_dir:
         # Escape the path for regex and replace it
-        combined_patterns[re.escape(str(profile_dir))] = "{home_directory}"
-
-    # Add any patterns the user added manually during the session
-    combined_patterns.update(_USER_ADDED_PATTERNS)
+        combined_patterns.setdefault(re.escape(str(profile_dir)), "{home_directory}")
 
     return combined_patterns
diff --git a/OF-Scraper-3.14.7/test/unit/test_gui_log_handlers_mask_sess.py b/OF-Scraper-3.14.7/test/unit/test_gui_log_handlers_mask_sess.py
new file mode 100644
index 0000000..a573f62
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_gui_log_handlers_mask_sess.py
@@ -0,0 +1,262 @@
+"""The GUI's own log handlers must mask the session cookie too.
+
+The GUI console handlers and the Verbose Log file used a plain
+logging.Formatter, so the session value showed in full there even after
+read_auth() registered it.
+"""
+
+import logging
+from types import SimpleNamespace
+
+import pytest
+
+pytest.importorskip("PyQt6.QtWidgets")
+
+import ofscraper.gui.app as gui_app  # noqa: E402
+import ofscraper.gui.utils.workflow as workflow_mod  # noqa: E402
+import ofscraper.managers.manager as manager_mod  # noqa: E402
+import ofscraper.utils.auth.file as auth_file  # noqa: E402
+import ofscraper.utils.config.data as config_data  # noqa: E402
+import ofscraper.utils.logs.utils.sensitive as sensitive  # noqa: E402
+import ofscraper.utils.paths.common as common_paths  # noqa: E402
+from ofscraper.gui.main_window import MainWindow  # noqa: E402
+from ofscraper.gui.signals import app_signals  # noqa: E402
+from ofscraper.gui.utils import privacy_mode as pm  # noqa: E402
+from ofscraper.utils.logs.classes.classes import LogFileFormatter  # noqa: E402
+
+pytestmark = pytest.mark.unit
+
+# fake value; holds a 9-digit run that matches a loaded model id below
+SESS = "fakesess168143417abc+def/XYZ"
+MODEL_ID = 168143417
+
+# the forms the value is logged in: the failed-request header dump (a dict
+# repr holding the cookie header) and a cookie dict
+COOKIE_LINE = "requests headers " + str(
+    {"cookie": f"auth_id=1;sess={SESS};auth_uid_=1;", "user-agent": "ua"}
+)
+DICT_LINE = "cookies " + str({"sess": SESS, "auth_id": "1"})
+
+
+@pytest.fixture(autouse=True)
+def registered_sess(monkeypatch):
+    monkeypatch.setattr(sensitive, "_USER_ADDED_PATTERNS", {})
+    monkeypatch.setattr(sensitive.paths, "get_username", lambda: None)
+    auth_file.hide_secrets({"sess": SESS})
+
+
+@pytest.fixture
+def privacy():
+    def set_to(value):
+        pm.set_privacy_mode(value, persist=False, emit=False)
+
+    before = pm.is_privacy_mode()
+    yield set_to
+    set_to(before)
+
+
+@pytest.fixture
+def console_lines():
+    got = []
+
+    def slot(level, msg):
+        got.append(msg)
+
+    app_signals.log_message.connect(slot)
+    yield got
+    app_signals.log_message.disconnect(slot)
+
+
+def record(msg, level=logging.INFO, name="shared"):
+    return logging.LogRecord(name, level, __file__, 1, msg, None, None)
+
+
+def shown_in_console(lines):
+    # what ConsoleLogWidget._append_log puts on screen
+    return [pm.redact_log_message(line) for line in lines]
+
+
+# -- GUI console: app.py handler (on "shared" and "shared_other") -----------
+
+
+@pytest.mark.parametrize("line", [COOKIE_LINE, DICT_LINE])
+def test_app_console_handler_masks_sess_with_privacy_off(console_lines, privacy, line):
+    privacy(False)
+    gui_app._make_gui_log_handler().handle(record(line))
+    (out,) = shown_in_console(console_lines)
+    assert SESS not in out
+    assert "{sess}" in out
+
+
+def test_app_console_handler_still_hides_cookie_with_privacy_on(console_lines, privacy):
+    privacy(True)
+    gui_app._make_gui_log_handler().handle(record(COOKIE_LINE))
+    (out,) = shown_in_console(console_lines)
+    assert SESS not in out
+    assert "sess={hidden}" in out
+
+
+# -- GUI console: workflow.py handler (on "shared_other") --------------------
+
+
+@pytest.fixture
+def workflow_handler():
+    workflow_mod._install_gui_log_handler()
+    try:
+        yield workflow_mod._gui_log_handler
+    finally:
+        workflow_mod._uninstall_gui_log_handler()
+
+
+@pytest.mark.parametrize("line", [COOKIE_LINE, DICT_LINE])
+def test_workflow_console_handler_masks_sess_with_privacy_off(
+    workflow_handler, console_lines, privacy, line
+):
+    privacy(False)
+    workflow_handler.handle(record(line, name="shared_other"))
+    (out,) = shown_in_console(console_lines)
+    assert SESS not in out
+    assert "{sess}" in out
+
+
+def test_workflow_console_handler_still_hides_cookie_with_privacy_on(
+    workflow_handler, console_lines, privacy
+):
+    privacy(True)
+    workflow_handler.handle(record(COOKIE_LINE, name="shared_other"))
+    (out,) = shown_in_console(console_lines)
+    assert SESS not in out
+    assert "sess={hidden}" in out
+
+
+# -- Verbose Log file (main_window._apply_verbose_log) -----------------------
+
+
+@pytest.fixture
+def verbose_log(monkeypatch, tmp_path):
+    monkeypatch.setattr(common_paths, "get_log_folder", lambda: tmp_path)
+    monkeypatch.setattr(config_data, "get_main_profile", lambda: "main")
+    logger = logging.getLogger("shared")
+    level_before = logger.level
+    levels_before = {h: h.level for h in logger.handlers}
+    win = SimpleNamespace()
+    MainWindow._apply_verbose_log(win, True)
+    try:
+        (handler,) = [h for h in logger.handlers if getattr(h, "_gui_verbose_handler", False)]
+        yield handler, tmp_path
+    finally:
+        MainWindow._apply_verbose_log(win, False)
+        logger.setLevel(level_before)
+        for h, lvl in levels_before.items():
+            h.setLevel(lvl)
+
+
+@pytest.mark.parametrize("line", [COOKIE_LINE, DICT_LINE])
+def test_verbose_log_file_masks_sess(verbose_log, line):
+    handler, folder = verbose_log
+    handler.handle(record(f"[bold]{line}[/bold]", level=logging.DEBUG))
+    handler.flush()
+    (path,) = folder.rglob("ofscraper_gui_verbose_*.log")
+    text = path.read_text(encoding="utf-8")
+    assert SESS not in text
+    assert "{sess}" in text
+    assert "[bold]" not in text  # Rich markup stripped like the normal log file
+
+
+# the normal log file's format, from utils/logs/other.py
+NORMAL_LOG_FMT = r" %(asctime)s:\[%(module)s.%(funcName)s:%(lineno)d]  %(message)s"
+
+
+def test_verbose_log_keeps_the_location_like_the_normal_log(verbose_log):
+    handler, folder = verbose_log
+    rec = logging.LogRecord(
+        "shared", logging.DEBUG, "sessionmanager.py", 584, "a plain line", None, None,
+        func="requests",
+    )
+    handler.handle(rec)
+    handler.flush()
+    (path,) = folder.rglob("ofscraper_gui_verbose_*.log")
+    written = path.read_text(encoding="utf-8").splitlines()[-1]
+    assert "[sessionmanager.requests:584]" in written
+    normal = LogFileFormatter(NORMAL_LOG_FMT, "%Y-%m-%d %H:%M:%S").format(rec)
+    assert written == normal
+
+
+# -- Privacy mode: model names and ids ---------------------------------------
+
+
+def load_models(monkeypatch, subs):
+    monkeypatch.setattr(pm, "_KNOWN_CACHE", {"key": None, "names": None, "ids": None})
+    monkeypatch.setattr(
+        manager_mod,
+        "Manager",
+        SimpleNamespace(
+            _model_manager=SimpleNamespace(_all_subs_dict=subs),
+            _profile_manager=SimpleNamespace(model_managers={}),
+        ),
+    )
+
+
+@pytest.fixture
+def loaded_model(monkeypatch):
+    load_models(monkeypatch, {"realname": SimpleNamespace(id=MODEL_ID)})
+
+
+def test_model_id_inside_sess_does_not_split_it(loaded_model, privacy):
+    # the id rule doesn't match next to a letter or digit, so the whole
+    # value is still there for the mask table
+    privacy(True)
+    out = pm.redact_log_message(DICT_LINE)
+    assert "{sess}" in out
+    assert "{model_id}" not in out
+    for part in SESS.split(str(MODEL_ID)):
+        assert part not in out
+    # model ids elsewhere in the line are still hidden
+    assert pm.redact_log_message(f"user {MODEL_ID}") == "user {model_id}"
+    assert pm.redact_log_message(f"/.data/{MODEL_ID}/user_data.db") == "/.data/{model_id}/user_data.db"
+
+
+CREATOR_LINES = [
+    "Downloading from {name}",
+    "saved to /data/{name}/Posts/Videos/clip.mp4",
+    "GET https://onlyfans.com/{name}/media",
+]
+
+
+@pytest.mark.parametrize("name", ["happiness_jo", "pippa.rose"])
+@pytest.mark.parametrize("line", CREATOR_LINES)
+def test_home_folder_name_inside_a_creator_name_doesnt_expose_it(
+    monkeypatch, privacy, name, line
+):
+    # home folder "pi": its mask matches anywhere, and used to cut into the
+    # creator name before the name rule could hide it
+    load_models(monkeypatch, {name: SimpleNamespace(id=55512345)})
+    monkeypatch.setattr(sensitive.paths, "get_username", lambda: "pi")
+    privacy(True)
+    out = pm.redact_log_message(line.format(name=name))
+    assert "{model}" in out
+    assert "{home_directory}" not in out
+    for piece in name.split("pi"):
+        if len(piece) >= 3:
+            assert piece not in out
+
+
+@pytest.mark.parametrize("line", CREATOR_LINES)
+def test_creator_name_holding_the_users_id_doesnt_expose_it(monkeypatch, privacy, line):
+    # me.py registers the user's own id as a plain pattern that matches anywhere
+    name = "creator123456789x"
+    load_models(monkeypatch, {name: SimpleNamespace(id=55512345)})
+    sensitive.add_sensitive_pattern(123456789, "userid")
+    privacy(True)
+    out = pm.redact_log_message(line.format(name=name))
+    assert "{model}" in out
+    assert "creator" not in out
+    assert "userid" not in out
+
+
+def test_handle_made_of_a_letter_and_the_model_id_is_still_hidden(monkeypatch, privacy):
+    # the id rule no longer matches next to a letter; the name rule covers it
+    load_models(monkeypatch, {"u1234567": SimpleNamespace(id=1234567)})
+    privacy(True)
+    assert pm.redact_log_message("Downloading from u1234567") == "Downloading from {model}"
+    assert pm.redact_log_message("model id 1234567 done") == "model id {model_id} done"
diff --git a/OF-Scraper-3.14.7/test/unit/test_gui_log_stray_markup.py b/OF-Scraper-3.14.7/test/unit/test_gui_log_stray_markup.py
new file mode 100644
index 0000000..30d9ba2
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_gui_log_stray_markup.py
@@ -0,0 +1,130 @@
+"""GUI log paths with a line holding broken Rich markup ("[/bold]").
+
+The Verbose Log file uses LogFileFormatter, so it needs the same fallback
+as the normal log file. The GUI console never parses markup with Rich, and
+GUI mode must still remove the terminal handlers now that they are a
+RichHandler subclass.
+"""
+
+import logging
+from types import SimpleNamespace
+
+import pytest
+from rich.logging import RichHandler
+
+pytest.importorskip("PyQt6.QtWidgets")
+
+import ofscraper.gui.app as gui_app  # noqa: E402
+import ofscraper.gui.utils.workflow as workflow_mod  # noqa: E402
+import ofscraper.utils.config.data as config_data  # noqa: E402
+import ofscraper.utils.logs.stdout as stdout_mod  # noqa: E402
+import ofscraper.utils.logs.utils.sensitive as sensitive  # noqa: E402
+import ofscraper.utils.paths.common as common_paths  # noqa: E402
+from ofscraper.gui.main_window import MainWindow  # noqa: E402
+from ofscraper.gui.signals import app_signals  # noqa: E402
+from ofscraper.gui.utils import privacy_mode as pm  # noqa: E402
+
+pytestmark = pytest.mark.unit
+
+STRAY = "done [/bold] here"
+
+
+@pytest.fixture(autouse=True)
+def no_run_masks(monkeypatch):
+    monkeypatch.setattr(sensitive, "_USER_ADDED_PATTERNS", {})
+    monkeypatch.setattr(sensitive.paths, "get_username", lambda: None)
+
+
+def record(msg, level=logging.INFO, name="shared"):
+    return logging.LogRecord(
+        name, level, "sessionmanager.py", 584, msg, None, None, func="requests"
+    )
+
+
+# -- Verbose Log file ---------------------------------------------------------
+
+
+@pytest.fixture
+def verbose_log(monkeypatch, tmp_path):
+    monkeypatch.setattr(common_paths, "get_log_folder", lambda: tmp_path)
+    monkeypatch.setattr(config_data, "get_main_profile", lambda: "main")
+    logger = logging.getLogger("shared")
+    level_before = logger.level
+    levels_before = {h: h.level for h in logger.handlers}
+    win = SimpleNamespace()
+    MainWindow._apply_verbose_log(win, True)
+    try:
+        (handler,) = [
+            h for h in logger.handlers if getattr(h, "_gui_verbose_handler", False)
+        ]
+        yield handler, tmp_path
+    finally:
+        MainWindow._apply_verbose_log(win, False)
+        logger.setLevel(level_before)
+        for h, lvl in levels_before.items():
+            h.setLevel(lvl)
+
+
+def test_verbose_log_keeps_a_line_with_a_stray_closing_tag(verbose_log):
+    handler, folder = verbose_log
+    raised = []
+    handler.handleError = lambda rec: raised.append(rec)
+    handler.handle(record(STRAY, level=logging.DEBUG))
+    handler.flush()
+    (path,) = folder.rglob("ofscraper_gui_verbose_*.log")
+    lines = path.read_text(encoding="utf-8").splitlines()
+    assert not raised
+    assert lines and lines[-1].endswith(":[sessionmanager.requests:584]  " + STRAY)
+    assert "\\[" not in lines[-1]
+
+
+# -- GUI console --------------------------------------------------------------
+
+
+@pytest.fixture
+def console_lines():
+    got = []
+
+    def slot(level, msg):
+        got.append(msg)
+
+    app_signals.log_message.connect(slot)
+    yield got
+    app_signals.log_message.disconnect(slot)
+
+
+def test_app_console_handler_shows_a_line_with_a_stray_closing_tag(console_lines):
+    gui_app._make_gui_log_handler().handle(record(STRAY))
+    (out,) = [pm.redact_log_message(line) for line in console_lines]
+    assert out.endswith(STRAY)
+
+
+def test_workflow_console_handler_shows_a_line_with_a_stray_closing_tag(
+    console_lines,
+):
+    workflow_mod._install_gui_log_handler()
+    try:
+        workflow_mod._gui_log_handler.handle(record(STRAY, name="shared_other"))
+    finally:
+        workflow_mod._uninstall_gui_log_handler()
+    (out,) = [pm.redact_log_message(line) for line in console_lines]
+    # its own regex drops the known tag, the rest of the line stays
+    assert out.endswith("done  here")
+
+
+# -- GUI mode removes the terminal handlers -----------------------------------
+
+
+def test_gui_mode_removes_the_terminal_handlers():
+    logger = logging.getLogger("shared")
+    handlers_before = list(logger.handlers)
+    level_before = logger.level
+    try:
+        stdout_mod.add_stdout_handler(logger, clear=False)
+        added = [h for h in logger.handlers if h not in handlers_before]
+        assert any(isinstance(h, RichHandler) for h in added)
+        workflow_mod._strip_rich_stdout_handlers()
+        assert not any(isinstance(h, RichHandler) for h in logger.handlers)
+    finally:
+        logger.handlers[:] = handlers_before
+        logger.setLevel(level_before)
diff --git a/OF-Scraper-3.14.7/test/unit/test_log_stray_markup.py b/OF-Scraper-3.14.7/test/unit/test_log_stray_markup.py
new file mode 100644
index 0000000..f8a60f4
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_log_stray_markup.py
@@ -0,0 +1,103 @@
+"""A log line with broken Rich markup is still logged, not dropped.
+
+Rich raises MarkupError on a stray closing tag such as "[/bold]"; the log
+file and Discord formatters and the terminal handler used to lose the line.
+"""
+
+import io
+import logging
+
+import pytest
+from rich.console import Console
+
+import ofscraper.utils.console as console_mod
+import ofscraper.utils.logs.classes.classes as log_class
+import ofscraper.utils.logs.stdout as stdout_mod
+import ofscraper.utils.logs.utils.sensitive as sensitive
+
+pytestmark = pytest.mark.unit
+
+STRAY = "done [/bold] here"
+# the terminal and log file line format, from utils/logs/stdout.py
+LINE_FMT = r" \[%(module)s.%(funcName)s:%(lineno)d]  %(message)s"
+
+
+@pytest.fixture(autouse=True)
+def no_run_masks(monkeypatch):
+    monkeypatch.setattr(sensitive, "_USER_ADDED_PATTERNS", {})
+    monkeypatch.setattr(sensitive.paths, "get_username", lambda: None)
+
+
+def _record(msg):
+    return logging.LogRecord(
+        "t", logging.INFO, "mod.py", 7, msg, None, None, func="fn"
+    )
+
+
+# -- log file and Discord formatters -----------------------------------------
+
+
+@pytest.mark.parametrize(
+    "formatter", [log_class.LogFileFormatter, log_class.DiscordFormatter]
+)
+def test_formatters_keep_line_with_stray_closing_tag(formatter):
+    out = formatter("%(message)s").format(_record(STRAY))
+    assert out == STRAY
+
+
+def test_log_file_fallback_removes_escapes_like_rich_does():
+    out = log_class.LogFileFormatter(LINE_FMT).format(_record(STRAY))
+    assert "\\[" not in out
+    assert out == " [mod.fn:7]  " + STRAY
+
+
+def test_strip_markup_removes_only_bracket_escapes_on_fallback():
+    assert log_class.strip_markup(r"\[a] b [/bold] c\d") == r"[a] b [/bold] c\d"
+
+
+def test_formatters_still_strip_valid_markup():
+    out = log_class.LogFileFormatter("%(message)s").format(
+        _record("[bold]ok[/bold] fine")
+    )
+    assert out == "ok fine"
+
+
+# -- terminal handlers, as utils/logs/stdout.py builds them -------------------
+
+
+def _terminal_output(monkeypatch, msg):
+    buf = io.StringIO()
+    test_console = Console(file=buf, width=200, color_system=None)
+    monkeypatch.setattr(console_mod, "get_console", lambda: test_console)
+    logger = logging.getLogger(f"stray-markup-test-{id(buf)}")
+    logger.propagate = False
+    stdout_mod.add_stdout_handler(logger)
+    raised = []
+    try:
+        for h in logger.handlers:
+            h.handleError = lambda record: raised.append(record)
+        logger.info(msg)
+    finally:
+        for h in list(logger.handlers):
+            logger.removeHandler(h)
+    return buf.getvalue(), raised
+
+
+def test_terminal_handler_keeps_line_with_stray_closing_tag(monkeypatch):
+    out, raised = _terminal_output(monkeypatch, STRAY)
+    assert not raised
+    assert STRAY in out
+
+
+def test_terminal_fallback_removes_escapes(monkeypatch):
+    out, raised = _terminal_output(monkeypatch, STRAY)
+    assert not raised
+    assert "\\[" not in out
+    assert "[test_log_stray_markup._terminal_output:" in out
+
+
+def test_terminal_handler_still_renders_valid_markup(monkeypatch):
+    out, raised = _terminal_output(monkeypatch, "[bold]ok[/bold] fine")
+    assert not raised
+    assert "ok fine" in out
+    assert "[bold]" not in out
diff --git a/OF-Scraper-3.14.7/test/unit/test_sess_cookie_masked.py b/OF-Scraper-3.14.7/test/unit/test_sess_cookie_masked.py
new file mode 100644
index 0000000..33b5486
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_sess_cookie_masked.py
@@ -0,0 +1,163 @@
+"""The OnlyFans session cookie and other secrets must not reach a log unmasked."""
+
+import asyncio
+import contextlib
+import logging
+from types import SimpleNamespace
+
+import pytest
+
+import ofscraper.classes.of.media as media
+import ofscraper.data.api.me as me
+import ofscraper.utils.auth.file as auth_file
+import ofscraper.utils.logs.utils.sensitive as sensitive
+from ofscraper.utils.logs.classes.classes import DiscordFormatter, LogFileFormatter
+
+pytestmark = pytest.mark.unit
+
+# fake value with regex metacharacters, so an unescaped pattern would misbehave
+SESS = "fake.sess+value/with?regex*chars"
+
+
+@pytest.fixture(autouse=True)
+def clean_patterns(monkeypatch):
+    monkeypatch.setattr(sensitive, "_USER_ADDED_PATTERNS", {})
+    monkeypatch.setattr(sensitive.paths, "get_username", lambda: None)
+
+
+@pytest.fixture
+def fake_auth(monkeypatch):
+    auth = {"sess": SESS, "auth_id": "1", "auth_uid": "", "user_agent": "ua", "x-bc": "bc"}
+    monkeypatch.setattr(auth_file.auth_dict, "get_auth_dict", lambda *a, **k: dict(auth))
+    monkeypatch.setattr(auth_file.auth_schema, "auth_schema", lambda a: dict(a))
+    monkeypatch.setattr(auth_file.auth_schema, "auth_key_missing", lambda a: False)
+    monkeypatch.setattr(auth_file.auth_schema, "auth_key_null", lambda a: False)
+    return auth
+
+
+def formatted(formatter, msg):
+    record = logging.LogRecord("shared", logging.DEBUG, __file__, 1, msg, None, None)
+    return formatter.format(record)
+
+
+# the forms the value is logged in: the failed-request header dump in
+# sessionmanager (a dict repr holding the cookie header), a cookie dict, JSON
+LINES = [
+    "requests headers " + str({"cookie": f"auth_id=1;sess={SESS};auth_uid_=1;", "user-agent": "ua"}),
+    "cookies " + str({"sess": SESS, "auth_id": "1"}),
+    '{"sess": "' + SESS + '"}',
+]
+
+
+@pytest.mark.parametrize("formatter", [LogFileFormatter, DiscordFormatter])
+@pytest.mark.parametrize("line", LINES)
+def test_sess_is_masked_once_auth_is_read(fake_auth, formatter, line):
+    auth_file.read_auth()
+    out = formatted(formatter(), line)
+    assert SESS not in out
+    assert "{sess}" in out
+    assert "LOGGING ERROR" not in out
+
+
+def test_reading_auth_again_does_not_add_patterns(fake_auth):
+    # add_cookies() and get_cookies_str() read auth on every request
+    for _ in range(5):
+        auth_file.read_auth()
+    assert len(sensitive._USER_ADDED_PATTERNS) == 1
+
+
+@pytest.mark.parametrize("home", ["pi", "root"])
+def test_home_folder_name_inside_the_value_doesnt_expose_it(fake_auth, monkeypatch, home):
+    # the home-folder rule used to run before the session value and break it apart
+    value = f"k3{home}9xq2m7abcdz0r5t8w1y4ue"
+    fake_auth["sess"] = value
+    monkeypatch.setattr(sensitive.paths, "get_username", lambda: home)
+    auth_file.read_auth()
+    out = formatted(LogFileFormatter(), f"requests headers {{'cookie': 'auth_id=1;sess={value};'}}")
+    assert "sess={sess}" in out
+    assert value[len(home) + 2:] not in out
+
+
+def test_a_short_value_masks_nothing(fake_auth):
+    # a stray short value would otherwise mask ordinary words everywhere
+    fake_auth["sess"] = "a"
+    auth_file.read_auth()
+    assert sensitive._USER_ADDED_PATTERNS == {}
+    out = formatted(LogFileFormatter(), "failed: https://onlyfans.com/x")
+    assert out.endswith("failed: https://onlyfans.com/x")
+
+
+def test_empty_sess_registers_nothing(fake_auth):
+    fake_auth["sess"] = ""
+    auth_file.read_auth()
+    assert sensitive._USER_ADDED_PATTERNS == {}
+
+
+def test_a_short_user_id_doesnt_split_an_ip_address():
+    # run-time patterns come after the built-in rules, so the IP rule still
+    # sees the whole address
+    sensitive.add_sensitive_pattern("15", "userid")
+    out = formatted(LogFileFormatter(), "ip 10.15.2.3")
+    assert out.endswith("ip {ip_address}")
+
+
+def test_audio_pssh_with_regex_characters_is_masked():
+    # base64 with "+": as a raw regex "A+" means "one or more A", so the
+    # value didn't match itself and was logged in full
+    pssh = "AAAAW3Bzc2gAAA+/AAAA=="
+
+    async def run():
+        loop = asyncio.get_running_loop()
+
+        def done(value):
+            fut = loop.create_future()
+            fut.set_result(value)
+            return fut
+
+        prot = SimpleNamespace(value=None, pssh=[SimpleNamespace(pssh=pssh)])
+        repr_ = SimpleNamespace(base_urls=[SimpleNamespace(base_url_value="a.mp4")])
+        fake = SimpleNamespace(
+            _audio_adaptation_set=done(SimpleNamespace(content_protections=[prot])),
+            selected_audio_representation=done(repr_),
+            id=1,
+            post_id=2,
+        )
+        return await media.Media.mpd_audio_helper(fake)
+
+    assert asyncio.run(run())["pssh"] == pssh
+    out = formatted(LogFileFormatter(), f"license request for {pssh}")
+    assert pssh not in out and "pssh_code" in out
+    assert "LOGGING ERROR" not in out
+
+
+def me_session(username, name):
+    data = {"isAuth": True, "id": 123456789, "username": username, "name": name}
+
+    class FakeSession:
+        @contextlib.contextmanager
+        def requests(self, url):
+            yield SimpleNamespace(json_=lambda: data)
+
+    return FakeSession()
+
+
+@pytest.mark.parametrize("name", ["Jane (VIP)", "A+B", "Jane (VIP", "*Star*", "Plain Name"])
+def test_display_name_with_symbols_is_masked(name):
+    me._scraper_user_helper(me_session("plainuser1", name))
+    out = formatted(LogFileFormatter(), f"hello {name} and plainuser1 here")
+    assert name not in out
+    assert "plainuser1" not in out
+    assert "LOGGING ERROR" not in out
+
+
+def test_username_still_masked_only_as_a_whole_word():
+    me._scraper_user_helper(me_session("ann", "Ann Example"))
+    out = formatted(LogFileFormatter(), "ann is here; channel stays")
+    assert "channel stays" in out  # "ann" inside a longer word is left alone
+    assert not out.endswith("ann is here; channel stays")
+
+
+def test_an_empty_display_name_masks_nothing():
+    me._scraper_user_helper(me_session("plainuser1", ""))
+    out = formatted(LogFileFormatter(), "a line with spaces")
+    assert out.endswith("a line with spaces")
```
