# PR #33: fix(session, auth): session timeouts and retries, download limit and auth-check errors

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/33
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/session-network` → `main`
- **Created:** 2026-11-06T22:20:52Z  ·  **Updated:** 2026-11-07T00:03:18Z
- **Draft:** False
- **Changes:** 30 files, +2521 / -92

## Description

One commit per fix.

**What was broken:**
- Failed downloads leaked connections.
- Stalled TLS handshakes and silent servers hung requests.
- Requests ignored the retries and waits passed in.
- Cancels were retried.
- The download speed limit did nothing, and the Config page saved it in the wrong unit.
- A 0 passed to the download session was ignored.
- Network, server and dynamic-rule failures were reported as bad auth.
- A logged-out session passed the auth check.
- "Quit" in the CLI auth prompt didn't quit.

**What was fixed:** Each of the above, adapted to this code. In the GUI, Test Credentials and the model list now say "network or server problem" instead of blaming the auth. The Config page saves the speed limit in bytes per second (1 KB = 1000 bytes).

Tested: 93 new tests; full suite 945 passed, 11 skipped. Not tested live. Patched installs get these fixes once #32 is merged and the patch rebuilt.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/utils/leaky.py`
- `OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/utils/retries.py`
- `OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py`
- `OF-Scraper-3.14.7/ofscraper/data/api/init.py`
- `OF-Scraper-3.14.7/ofscraper/gui/dialogs/auth_dialog.py`
- `OF-Scraper-3.14.7/ofscraper/gui/dialogs/config_dialog.py`
- `OF-Scraper-3.14.7/ofscraper/gui/help/GUI_HELP.md`
- `OF-Scraper-3.14.7/ofscraper/gui/utils/auth_errors.py`
- `OF-Scraper-3.14.7/ofscraper/gui/utils/model_fetch.py`
- `OF-Scraper-3.14.7/ofscraper/managers/sessionmanager/ofsession.py`
- `OF-Scraper-3.14.7/ofscraper/managers/sessionmanager/sessionmanager.py`
- `OF-Scraper-3.14.7/ofscraper/prompts/prompt_groups/config.py`
- `OF-Scraper-3.14.7/ofscraper/utils/auth/request.py`
- `OF-Scraper-3.14.7/ofscraper/utils/checkers.py`
- `OF-Scraper-3.14.7/ofscraper/utils/of_env/values/req/req.py`
- `OF-Scraper-3.14.7/test/unit/test_auth_check_logged_out.py`
- `OF-Scraper-3.14.7/test/unit/test_auth_check_network.py`
- `OF-Scraper-3.14.7/test/unit/test_auth_prompt_choice.py`
- `OF-Scraper-3.14.7/test/unit/test_download_limit.py`
- `OF-Scraper-3.14.7/test/unit/test_download_limit_help.py`
- `OF-Scraper-3.14.7/test/unit/test_download_retry_cancel.py`
- `OF-Scraper-3.14.7/test/unit/test_download_session_zero_args.py`
- `OF-Scraper-3.14.7/test/unit/test_gui_download_limit_units.py`
- `OF-Scraper-3.14.7/test/unit/test_gui_pick_and_account_privacy.py`
- `OF-Scraper-3.14.7/test/unit/test_profile_info_after_clear.py`
- `OF-Scraper-3.14.7/test/unit/test_session_cancel.py`
- `OF-Scraper-3.14.7/test/unit/test_session_read_timeout.py`
- `OF-Scraper-3.14.7/test/unit/test_session_request_retry_args.py`
- `OF-Scraper-3.14.7/test/unit/test_session_stream_cleanup.py`
- `OF-Scraper-3.14.7/test/unit/test_session_sync_connect_timeout.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/utils/leaky.py b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/utils/leaky.py
index a45b907..bbd9aa7 100644
--- a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/utils/leaky.py
+++ b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/utils/leaky.py
@@ -11,4 +11,10 @@ def __init__(self, *args, **kwargs):
     async def acquire(self, amount: float = 1):
         if settings.get_settings().download_limit <= 0:
             return
-        await super().acquire(amount or CHUNK_SIZE)
+        amount = amount or CHUNK_SIZE
+        # AsyncLimiter refuses more than one period's worth at once, and a
+        # chunk can be bigger than the limit (metadata reads 30 MB chunks)
+        while amount > self.max_rate:
+            await super().acquire(self.max_rate)
+            amount -= self.max_rate
+        await super().acquire(amount)
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/utils/retries.py b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/utils/retries.py
index 71ee120..fcbc3c8 100644
--- a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/utils/retries.py
+++ b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/utils/retries.py
@@ -1,3 +1,4 @@
+import asyncio
 import logging
 from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_random
 
@@ -12,9 +13,11 @@ def __init__(self, stop=None, wait=None, retry=None) -> None:
             min=of_env.getattr("OF_MIN_WAIT_API"),
             max=of_env.getattr("OF_MAX_WAIT_API"),
         )
+        # a cancel (Ctrl+C, a cancelled task) stops the download: tenacity's
+        # attempt swallows it, so it must not count as a failure
         retry = retry or retry_if_exception(
             lambda e: str(e) != of_env.getattr("SPACE_DOWNLOAD_MESSAGE")
-            and not isinstance(e, KeyboardInterrupt)
+            and not isinstance(e, (KeyboardInterrupt, asyncio.CancelledError))
             and not getattr(e, "no_retry", False)
         )
         
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py b/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py
index 88417e0..b2ad65e 100644
--- a/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py
+++ b/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py
@@ -54,7 +54,8 @@ def runner(self, menu=False):
                 logger_mod.resetLogger()
             except Exception:
                 pass
-        check_auth()
+        # "Go to Main Menu" is only offered when the run came from the menu
+        check_auth(include_main_menu=menu)
         with scrape_context_manager():
             with progress_utils.stop_live_screen(clear="all"):
                 with progress_utils.setup_live("main_activity"):
diff --git a/OF-Scraper-3.14.7/ofscraper/data/api/init.py b/OF-Scraper-3.14.7/ofscraper/data/api/init.py
index 3718345..d26620e 100644
--- a/OF-Scraper-3.14.7/ofscraper/data/api/init.py
+++ b/OF-Scraper-3.14.7/ofscraper/data/api/init.py
@@ -11,9 +11,14 @@
 
 """
 
+import json
 import logging
 import traceback
 
+import aiohttp
+import httpx
+
+import ofscraper.utils.auth.request as auth_requests
 import ofscraper.utils.console as console
 import ofscraper.utils.settings as settings
 from . import me
@@ -29,13 +34,82 @@ def print_sign_status():
         console.get_shared_console().print("Status - [bold red]🔴 DOWN[/bold red]")
 
 
-def getstatus():
+def _host(e) -> str:
+    try:
+        if isinstance(e, aiohttp.ClientResponseError):
+            return e.request_info.url.host
+        if isinstance(e, aiohttp.ClientConnectorError):
+            return e.host
+        return e.request.url.host
+    except (AttributeError, RuntimeError):
+        return "the server"
+
+
+def unavailable_message(e: Exception) -> str | None:
+    """
+    Returns a message for a failure that says nothing about the auth
+    (network errors, server errors, a reply that isn't JSON, no usable
+    dynamic rule), else None.
+    """
+    if isinstance(e, auth_requests.DynamicRuleUnavailable):
+        return str(e)
+    if isinstance(e, (httpx.TransportError, aiohttp.ClientConnectionError)):
+        timed_out = isinstance(
+            e, (httpx.TimeoutException, aiohttp.ServerTimeoutError)
+        )
+        reason = "timed out" if timed_out else "connection failed"
+        return f"Couldn't reach {_host(e)} ({reason}). Check your connection or VPN."
+    if isinstance(e, httpx.HTTPStatusError):
+        status = e.response.status_code
+    elif isinstance(e, aiohttp.ClientResponseError):
+        status = e.status
+    else:
+        status = None
+    if status == 429:
+        return f"{_host(e)} is rate limiting requests. Try again later."
+    if status is not None and status >= 500:
+        return (
+            f"{_host(e)} returned {status}: the server had an error. "
+            "Try again later."
+        )
+    if isinstance(e, json.JSONDecodeError):
+        # the parse error doesn't say which request it came from
+        return (
+            "Got a reply that isn't JSON from OnlyFans. It may be a captive "
+            "portal or a VPN block page, or the server may be having problems. "
+            "Check your connection or VPN."
+        )
+    return None
+
+
+def auth_status():
+    """
+    Returns (status, message). status is UP, DOWN (the auth was rejected) or
+    UNAVAILABLE (the auth couldn't be checked; message says why).
+    """
     if settings.get_settings().anon:
-        return "UP"
+        return "UP", None
     try:
-        me.scrape_user()
-        return "UP"
+        # fetch the dynamic rule once, with its own retries. Otherwise each
+        # retry of /me fetches it again from every rule host
+        auth_requests.read_request_auth()
+        data = me.scrape_user()
     except Exception as e:
         log.traceback_(e)
         log.traceback_(traceback.format_exc())
-        return "DOWN"
+        message = unavailable_message(e)
+        if message:
+            log.error(message)
+            return "UNAVAILABLE", message
+        return "DOWN", None
+    # /me answers isAuth false when no one is logged in. That's a normal
+    # answer for anonymous runs (get_id() falls back to 'id_unknown'), so
+    # only the auth check treats it as bad auth
+    if not data.get("isAuth"):
+        log.info("OnlyFans says this session isn't logged in")
+        return "DOWN", None
+    return "UP", None
+
+
+def getstatus():
+    return auth_status()[0]
diff --git a/OF-Scraper-3.14.7/ofscraper/gui/dialogs/auth_dialog.py b/OF-Scraper-3.14.7/ofscraper/gui/dialogs/auth_dialog.py
index 17f6c40..1063c91 100644
--- a/OF-Scraper-3.14.7/ofscraper/gui/dialogs/auth_dialog.py
+++ b/OF-Scraper-3.14.7/ofscraper/gui/dialogs/auth_dialog.py
@@ -2857,7 +2857,7 @@ def _validate_of_credentials(creds: dict) -> "tuple[bool | None, str]":
     import asyncio as _aio
 
     from ofscraper.gui.utils.auth_errors import (
-        format_cred_test_failure,
+        cred_test_failure,
         wrong_user_help_message,
     )
 
@@ -2910,9 +2910,12 @@ def _validate_of_credentials(creds: dict) -> "tuple[bool | None, str]":
         import ofscraper.data.api.me as _me
         user_info = None
         try:
+            # fetch the dynamic rule once, with its own retries. Otherwise
+            # each retry of /me fetches it again from every rule host
+            _auth_req.read_request_auth()
             user_info = _me.scrape_user()
         except Exception as e:
-            return False, format_cred_test_failure(e)
+            return cred_test_failure(e)
 
         if not user_info or not isinstance(user_info, dict):
             return False, wrong_user_help_message(
@@ -2969,7 +2972,7 @@ def _validate_of_credentials(creds: dict) -> "tuple[bool | None, str]":
             "Check your internet connection or try again."
         )
     except Exception as e:
-        return False, format_cred_test_failure(e)
+        return cred_test_failure(e)
 
     finally:
         # Always restore original auth.json ONLY IF test failed
@@ -2981,7 +2984,8 @@ def _validate_of_credentials(creds: dict) -> "tuple[bool | None, str]":
 
 
 class _CredTestWorker(QThread):
-    # success: True=valid, False=invalid, None=inconclusive
+    # success: True=valid, False=invalid, None=inconclusive,
+    # CRED_TEST_UNAVAILABLE=couldn't be checked (network or server problem)
     result_ready = pyqtSignal(object, str)
 
     def __init__(self, creds: dict, parent=None):
@@ -5138,6 +5142,8 @@ def _test_credentials(self):
         self._test_progress_dlg.exec()
 
     def _on_test_done(self, success, message: str):
+        from ofscraper.gui.utils.auth_errors import CRED_TEST_UNAVAILABLE
+
         # Close the progress dialog before showing the result.
         try:
             if hasattr(self, "_test_progress_dlg") and self._test_progress_dlg is not None:
@@ -5155,6 +5161,12 @@ def _on_test_done(self, success, message: str):
             # Inconclusive — credentials likely valid but session state mismatch
             app_signals.status_message.emit("Credentials test inconclusive — likely valid")
             QMessageBox.information(self, "Credentials Appear Valid", message)
+        elif success == CRED_TEST_UNAVAILABLE:
+            # a network or server problem: says nothing about the credentials
+            app_signals.status_message.emit(
+                "Couldn't check credentials — network or server problem"
+            )
+            QMessageBox.warning(self, "Couldn't Check Credentials", message)
         else:
             app_signals.status_message.emit(f"Credentials failed — {message}")
             QMessageBox.warning(self, "Credentials Invalid", message)
diff --git a/OF-Scraper-3.14.7/ofscraper/gui/dialogs/config_dialog.py b/OF-Scraper-3.14.7/ofscraper/gui/dialogs/config_dialog.py
index c3225d8..264295c 100644
--- a/OF-Scraper-3.14.7/ofscraper/gui/dialogs/config_dialog.py
+++ b/OF-Scraper-3.14.7/ofscraper/gui/dialogs/config_dialog.py
@@ -67,6 +67,31 @@ def _sanitize_ext_text(val: str, default: str) -> str:
     return s or default
 
 
+# download_limit is stored in bytes per second (a bare number, or a size such
+# as "500K"), but the page shows it in KB/s. 1 KB = 1000 bytes, as in
+# --download-limit 500K.
+_KB = 1000
+# the page's spin box range; Qt can't hold much more than 2.1e9 anyway
+_DOWNLOAD_LIMIT_MAX_KB = 999999
+
+
+def _download_limit_to_kb(stored) -> int:
+    try:
+        from humanfriendly import parse_size
+
+        limit = parse_size(str(stored).strip()) if stored not in (None, "") else 0
+    except Exception:
+        return 0
+    if limit <= 0:
+        return 0
+    # Never round a set limit down to 0, which would mean "unlimited"
+    return min(_DOWNLOAD_LIMIT_MAX_KB, max(1, round(limit / _KB)))
+
+
+def _download_limit_from_kb(kb: int) -> int:
+    return int(kb) * _KB
+
+
 def _display_fs_path(value: str) -> str:
     """Normalize Windows filesystem paths for GUI display; Linux unchanged."""
     try:
@@ -782,8 +807,9 @@ def _create_performance_tab(self):
         scroll, form = self._create_scrollable_form()
         self._add_spin(form, "download_sems", "Download Semaphores", 1, 15, 6,
                        tooltip="Number of concurrent downloads per thread (1-15).\nHigher = more parallel downloads but may hit rate limits.")
-        self._add_spin(form, "download_limit", "Download Speed Limit (KB/s)", 0, 999999, 0,
-                       "0 = unlimited")
+        self._add_spin(form, "download_limit", "Download Speed Limit (KB/s)", 0, _DOWNLOAD_LIMIT_MAX_KB, 0,
+                       "0 = unlimited. 1 KB = 1000 bytes, as in --download-limit 500K.\n"
+                       "One limit shared by all downloads, not set per thread.")
         return scroll
 
     def _create_content_tab(self):
@@ -1173,6 +1199,8 @@ def _load_config(self):
                         widget.setPlainText(json.dumps(val, indent=2) if val else "")
                     else:
                         widget.setPlainText(str(val).strip() if val else "")
+                elif isinstance(widget, QSpinBox) and key == "download_limit":
+                    widget.setValue(_download_limit_to_kb(val))
                 elif isinstance(widget, QSpinBox):
                     try:
                         widget.setValue(int(val) if val else 0)
@@ -1455,10 +1483,18 @@ def set_nested(d, section, key, val):
                     pass
 
             # Performance
-            for k in ["download_sems", "download_limit"]:
-                w = self._widgets.get(k)
-                if w:
-                    set_nested(config, "performance_options", k, w.value())
+            w = self._widgets.get("download_sems")
+            if w:
+                set_nested(config, "performance_options", "download_sems", w.value())
+            w = self._widgets.get("download_limit")
+            if w:
+                # shown in KB/s, stored in bytes per second
+                set_nested(
+                    config,
+                    "performance_options",
+                    "download_limit",
+                    _download_limit_from_kb(w.value()),
+                )
 
             # Content
             w = self._widgets.get("block_ads")
diff --git a/OF-Scraper-3.14.7/ofscraper/gui/help/GUI_HELP.md b/OF-Scraper-3.14.7/ofscraper/gui/help/GUI_HELP.md
index 6ae1309..0fef69d 100644
--- a/OF-Scraper-3.14.7/ofscraper/gui/help/GUI_HELP.md
+++ b/OF-Scraper-3.14.7/ofscraper/gui/help/GUI_HELP.md
@@ -814,7 +814,7 @@ Note: older GUI builds incorrectly wrote `scripts_options` (typo). Saving from t
 
 - **Thread Count (`performance_options.thread_count`)**: Download threads.
 - **Download Semaphores (`performance_options.download_sems`)**: Limits concurrency inside the downloader.
-- **Download Speed Limit (KB/s) (`performance_options.download_limit`)**: 0 = unlimited.
+- **Download Speed Limit (KB/s) (`performance_options.download_limit`)**: 0 = unlimited. 1 KB = 1000 bytes. `config.json` stores the limit in bytes per second, so 500 here is saved as `500000`. The limit is shared by all downloads, not set per thread.
 
 <a id="config-content"></a>
 ### Content
diff --git a/OF-Scraper-3.14.7/ofscraper/gui/utils/auth_errors.py b/OF-Scraper-3.14.7/ofscraper/gui/utils/auth_errors.py
index fe585eb..3ddd287 100644
--- a/OF-Scraper-3.14.7/ofscraper/gui/utils/auth_errors.py
+++ b/OF-Scraper-3.14.7/ofscraper/gui/utils/auth_errors.py
@@ -70,6 +70,9 @@ def is_wrong_user_failure(exc=None, of_code=None, of_message=None, text: str | N
 
 def format_cred_test_failure(exc) -> str:
     """Turn credential-test exceptions into actionable GUI text."""
+    problem = network_problem_message(exc)
+    if problem:
+        return network_problem_help_message(problem)
     of_code, of_message, detail = extract_of_error(exc)
     if is_wrong_user_failure(exc, of_code, of_message):
         return wrong_user_help_message(detail=detail)
@@ -93,6 +96,15 @@ def format_cred_test_failure(exc) -> str:
 def model_load_failure_dialog_text(detail=None) -> tuple[str, str | None]:
     """Main + optional detailed text for Unable to Load Models dialogs."""
     detail_s = str(detail).strip() if detail else ""
+    if NETWORK_PROBLEM_PREFIX in detail_s:
+        problem = detail_s.split(NETWORK_PROBLEM_PREFIX, 1)[1]
+        return (
+            "Unable to get list of models: this is a network or server "
+            "problem, not a problem with your auth.\n\n"
+            f"{problem}\n\n"
+            "Check your connection or VPN, then click Retry.",
+            detail_s,
+        )
     if detail_s and is_wrong_user_failure(text=detail_s):
         return (
             "Unable to get list of models — OnlyFans rejected the session "
@@ -115,3 +127,38 @@ def model_load_failure_dialog_text(detail=None) -> tuple[str, str | None]:
         "For “Wrong user” / sess and auth_id mismatch, see Help → Auth Issues."
     )
     return main, (detail_s or None)
+
+
+# Marks a model-list failure that is a network or server problem: the model
+# list worker hands its error to the page as text.
+NETWORK_PROBLEM_PREFIX = "Network or server problem: "
+# Test Credentials result when the credentials couldn't be checked at all
+CRED_TEST_UNAVAILABLE = "unavailable"
+
+
+def network_problem_message(exc) -> str | None:
+    """The reason, if exc is a network, server or dynamic-rule problem
+    rather than rejected auth; else None."""
+    try:
+        from ofscraper.data.api.init import unavailable_message
+
+        return unavailable_message(exc)
+    except Exception:
+        return None
+
+
+def network_problem_help_message(problem: str) -> str:
+    return (
+        "Couldn't check the credentials: this is a network or server problem, "
+        "not a problem with your auth.\n\n"
+        f"{problem}\n\n"
+        "Check your connection or VPN, then Test Credentials again. If it "
+        "keeps failing, try another Dynamic Mode under Configuration → Advanced."
+    )
+
+
+def cred_test_failure(exc) -> tuple:
+    """(result, text) for a Test Credentials failure. result is
+    CRED_TEST_UNAVAILABLE when the credentials couldn't be checked, else False."""
+    result = CRED_TEST_UNAVAILABLE if network_problem_message(exc) else False
+    return result, format_cred_test_failure(exc)
diff --git a/OF-Scraper-3.14.7/ofscraper/gui/utils/model_fetch.py b/OF-Scraper-3.14.7/ofscraper/gui/utils/model_fetch.py
index a5a7f78..21c11d1 100644
--- a/OF-Scraper-3.14.7/ofscraper/gui/utils/model_fetch.py
+++ b/OF-Scraper-3.14.7/ofscraper/gui/utils/model_fetch.py
@@ -18,6 +18,11 @@
 import threading
 from typing import Any, Iterable, Optional
 
+from ofscraper.gui.utils.auth_errors import (
+    NETWORK_PROBLEM_PREFIX,
+    network_problem_message,
+)
+
 log = logging.getLogger("shared")
 
 _FETCH_LOCK = threading.RLock()
@@ -405,12 +410,17 @@ async def _do_fetch_all():
     except asyncio.TimeoutError as e:
         breadcrumb("api_timeout", f"after={int(timeout)}s")
         raise Exception(
-            f"Model list fetch timed out after {int(timeout)}s. "
+            f"{NETWORK_PROBLEM_PREFIX}Model list fetch timed out after {int(timeout)}s. "
             "Check your network / Dynamic Mode and retry."
         ) from e
     except Exception as e:
         msg = str(e).strip() or e.__class__.__name__
         breadcrumb("api_error", f"{type(e).__name__}: {msg}")
+        # the page gets this as text, so mark a network or server problem
+        # for the dialog: it isn't a sign of bad auth
+        problem = network_problem_message(e)
+        if problem:
+            raise Exception(f"{NETWORK_PROBLEM_PREFIX}{problem}") from e
         raise Exception(f"Model list fetch failed: {msg}") from e
 
     breadcrumb("to_dicts_start")
diff --git a/OF-Scraper-3.14.7/ofscraper/managers/sessionmanager/ofsession.py b/OF-Scraper-3.14.7/ofscraper/managers/sessionmanager/ofsession.py
index c5fefc8..e9f4409 100644
--- a/OF-Scraper-3.14.7/ofscraper/managers/sessionmanager/ofsession.py
+++ b/OF-Scraper-3.14.7/ofscraper/managers/sessionmanager/ofsession.py
@@ -145,10 +145,20 @@ def __init__(
         **kwargs: Any,
     ) -> None:
         # --- Apply specialized defaults for download sessions ---
-        retries = kwargs.pop("retries", None) or get_download_req_retries()
-        wait_min = kwargs.pop("wait_min", None) or of_env.getattr("OF_MIN_WAIT_API")
-        wait_max = kwargs.pop("wait_max", None) or of_env.getattr("OF_MAX_WAIT_API")
-        read_timeout = kwargs.pop("read_timeout", None) or get_chunk_timeout()
+        # only None means "use the default": 0 tries, a 0 s wait or a read
+        # timeout of 0 (no limit, mapped to None by sessionManager) is a value
+        retries = kwargs.pop("retries", None)
+        if retries is None:
+            retries = get_download_req_retries()
+        wait_min = kwargs.pop("wait_min", None)
+        if wait_min is None:
+            wait_min = of_env.getattr("OF_MIN_WAIT_API")
+        wait_max = kwargs.pop("wait_max", None)
+        if wait_max is None:
+            wait_max = of_env.getattr("OF_MAX_WAIT_API")
+        read_timeout = kwargs.pop("read_timeout", None)
+        if read_timeout is None:
+            read_timeout = get_chunk_timeout()
         log = kwargs.pop("log", None) or common_globals.log
         self.leaky_bucket = LeakyBucket(settings.get_settings().download_limit, 1)
 
@@ -179,13 +189,13 @@ async def requests_async(
         async with super().requests_async(*args, **kwargs) as r:
             yield r
 
-    async def _httpx_funct_async(self, *args, **kwargs):
+    async def _aio_funct(self, *args, **kwargs):
         """Wraps the parent method to add download speed limiting to chunk iteration."""
-        t = await super()._httpx_funct_async(*args, **kwargs)
+        t = await super()._aio_funct(*args, **kwargs)
 
-        # Override chunk iterators to use the leaky bucket
+        # Override the chunk iterator to use the leaky bucket. iter_chunks is
+        # left alone: it yields (data, end_of_chunk) tuples and nothing uses it.
         t.iter_chunked = self.chunk_with_limit(t.iter_chunked)
-        t.iter_chunks = self.chunk_with_limit(t.iter_chunks)
         return t
 
     def chunk_with_limit(self, funct):
@@ -238,28 +248,7 @@ async def requests_async(
         async with super().requests_async(*args, **kwargs) as r:
             yield r
 
-    async def _httpx_funct_async(self, *args, **kwargs):
-        """Wraps the parent method to add download speed limiting to chunk iteration."""
-        t = await super()._httpx_funct_async(*args, **kwargs)
-
-        # Override chunk iterators to use the leaky bucket
-        t.iter_chunked = self.chunk_with_limit(t.iter_chunked)
-        t.iter_chunks = self.chunk_with_limit(t.iter_chunks)
-        return t
-
-    def chunk_with_limit(self, funct):
-        """Decorator to apply the leaky bucket to an async chunk generator."""
-
-        async def wrapper(*args, **kwargs):
-            async for chunk in funct(*args, **kwargs):
-                await self.get_token(len(chunk))
-                yield chunk
-
-        return wrapper
-
-    async def get_token(self, size: int):
-        """Acquires tokens from the leaky bucket corresponding to the chunk size."""
-        await self.leaky_bucket.acquire(size)
+    # the speed limit is inherited from download_session
 
 
 class cdm_session(sessionManager):
diff --git a/OF-Scraper-3.14.7/ofscraper/managers/sessionmanager/sessionmanager.py b/OF-Scraper-3.14.7/ofscraper/managers/sessionmanager/sessionmanager.py
index 051fb8e..ceb360d 100644
--- a/OF-Scraper-3.14.7/ofscraper/managers/sessionmanager/sessionmanager.py
+++ b/OF-Scraper-3.14.7/ofscraper/managers/sessionmanager/sessionmanager.py
@@ -285,11 +285,13 @@ def __init__(
             if total_timeout is not None
             else of_env.getattr("TOTAL_TIMEOUT")
         )
+        # 0 means no limit (None), wherever it comes from: aiohttp reads 0
+        # that way, but httpx reads 0 as "fail at once"
         self._read_timeout = (
             read_timeout
             if read_timeout is not None
             else of_env.getattr("OF_READ_TIMEOUT")
-        )
+        ) or None
         self._pool_connect_timeout = (
             pool_timeout
             if pool_timeout is not None
@@ -523,10 +525,10 @@ def requests(
     ) -> Generator[httpx.Response, None, None]:
         actions = actions or []
         exceptions = exceptions or []
-        log = kwargs.get("log") or self._log
-        retries = kwargs.get("retries") or self._retries
-        wait_min = kwargs.get("wait_min") or self._wait_min
-        wait_max = kwargs.get("wait_max") or self._wait_max
+        log = log or self._log
+        retries = retries if retries is not None else self._retries
+        wait_min = wait_min if wait_min is not None else self._wait_min
+        wait_max = wait_max if wait_max is not None else self._wait_max
 
         for _ in Retrying(
             retry=retry_if_not_exception_type((KeyboardInterrupt, SystemExit)),
@@ -570,7 +572,9 @@ def requests(
                             data=data,
                             timeout=httpx.Timeout(
                                 total_timeout or self._total_timeout,
-                                connect=connect_timeout,
+                                # the TLS handshake counts as connect time:
+                                # None here let a stalled handshake hang forever
+                                connect=connect_timeout or self._connect_timeout,
                                 pool=pool_connect_timeout or self._pool_connect_timeout,
                                 read=read_timeout or self._read_timeout,
                             ),
@@ -625,14 +629,24 @@ async def requests_async(
     ) -> AsyncGenerator[httpx.Response, None]:
         actions = actions or []
         exceptions = exceptions or []
-        retries = kwargs.get("retries") or self._retries
-        wait_min = kwargs.get("wait_min") or self._wait_min
-        wait_max = kwargs.get("wait_max") or self._wait_max
-
+        retries = retries if retries is not None else self._retries
+        wait_min = wait_min if wait_min is not None else self._wait_min
+        wait_max = wait_max if wait_max is not None else self._wait_max
+
+        # The retry loop only gets the response. The caller's code runs after
+        # it, at the yield below: an error there (e.g. a read timeout while
+        # streaming) must not land inside tenacity's attempt, which swallows
+        # every exception and would start a new request and yield again,
+        # leaving both responses' connections open.
+        r = None
         async for _ in AsyncRetrying(
             stop=tenacity.stop.stop_after_attempt(retries),
             wait=tenacity.wait_random(min=wait_min, max=wait_max),
-            retry=retry_if_not_exception_type((KeyboardInterrupt, SystemExit)),
+            # a cancel (Ctrl+C, a timeout around the call) stops the request:
+            # tenacity's attempt swallows it, so it must not count as a failure
+            retry=retry_if_not_exception_type(
+                (KeyboardInterrupt, SystemExit, asyncio.CancelledError)
+            ),
             reraise=True,
             before_sleep=lambda retry_state: (
                 self._log.debug(
@@ -686,13 +700,23 @@ async def requests_async(
                             )
                             raise SystemExit("OnlyFans Maintenance detected.")
                         r.raise_for_status()
-                    self._sem.release()
-                    yield r
-                    return
                 except Exception as E:
+                    if r is not None:
+                        r.close()
+                        r = None
                     await self._async_handle_error(E, exceptions)
-                    self._sem.release()
                     raise E
+                finally:
+                    self._sem.release()
+
+        try:
+            yield r
+        except BaseException:
+            # unread data stays in the socket buffer until the connection closes
+            r.close()
+            raise
+        else:
+            r.release()
 
     @property
     def sleep(self):
diff --git a/OF-Scraper-3.14.7/ofscraper/prompts/prompt_groups/config.py b/OF-Scraper-3.14.7/ofscraper/prompts/prompt_groups/config.py
index 666f15d..0c5f563 100644
--- a/OF-Scraper-3.14.7/ofscraper/prompts/prompt_groups/config.py
+++ b/OF-Scraper-3.14.7/ofscraper/prompts/prompt_groups/config.py
@@ -87,7 +87,7 @@ def funct(prompt_):
     [Performance Options]
     download_sems: number of downloads per processor/worker
     thread_count: number of processors/workers
-    download_limit: max download speed per second for each thread
+    download_limit: max download speed per second, shared by all downloads
     -----------------------------------
     [Content Filter Options]
     block_ads: use common key words to block ads
@@ -418,7 +418,7 @@ def performance_config():
             {
                 "type": "input",
                 "name": "download_limit",
-                "message": "Maximum download speed per second for  each thread: ",
+                "message": "Maximum download speed per second, shared by all downloads: ",
                 "validate": EmptyInputValidator(),
                 "option_instruction": """
                 Input can be int representing bytes
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/auth/request.py b/OF-Scraper-3.14.7/ofscraper/utils/auth/request.py
index 0c0d5d3..493ee7a 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/auth/request.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/auth/request.py
@@ -31,6 +31,74 @@
 last_check = None
 
 
+class UnusableDynamicRule(Exception):
+    """A dynamic rule's content can't be used to sign requests."""
+
+
+class DynamicRuleUnavailable(Exception):
+    """No dynamic rule source gave a rule that can sign requests.
+
+    This says nothing about the auth: the rule hosts couldn't be reached,
+    had an error, or sent a rule that can't be used.
+    """
+
+    def __init__(self, failures):
+        self.failures = list(failures)
+        reasons = "; ".join(
+            f"{source}: {_failure_reason(e)}" for source, e in self.failures
+        )
+        super().__init__(
+            "Couldn't get a usable dynamic rule to sign requests"
+            + (f" ({reasons})" if reasons else "")
+            + ". This isn't a problem with your auth. Check your connection or "
+            "VPN, try another dynamic rule source (Dynamic Mode), or try again "
+            "later."
+        )
+
+
+def _failure_reason(e):
+    import httpx
+
+    if isinstance(e, UnusableDynamicRule):
+        return str(e)
+    host = "the rule host"
+    if isinstance(e, httpx.HTTPError):
+        try:
+            host = e.request.url.host
+        except RuntimeError:
+            pass
+    if isinstance(e, httpx.TimeoutException):
+        return f"couldn't reach {host} (timed out)"
+    if isinstance(e, httpx.TransportError):
+        return f"couldn't reach {host} (connection failed)"
+    if isinstance(e, httpx.HTTPStatusError):
+        return f"{host} returned {e.response.status_code}"
+    if isinstance(e, json.JSONDecodeError):
+        return "the reply isn't JSON"
+    return str(e) or type(e).__name__
+
+
+RULE_KEYS = ["static_param", "format", "checksum_indexes", "checksum_constant"]
+SUFFIX_RULE_KEYS = [
+    "static_param",
+    "prefix",
+    "suffix",
+    "checksum_indexes",
+    "checksum_constant",
+]
+
+
+def check_rule(content):
+    """Raise UnusableDynamicRule unless content has the keys signing reads."""
+    if not isinstance(content, dict):
+        found = "null" if content is None else type(content).__name__
+        raise UnusableDynamicRule(f"unusable rule: expected a JSON object, got {found}")
+    keys = SUFFIX_RULE_KEYS if content.get("suffix") else RULE_KEYS
+    missing = [key for key in keys if key not in content]
+    if missing:
+        raise UnusableDynamicRule(f"unusable rule: missing {', '.join(missing)}")
+
+
 def invalidate_auth_cache():
     """Clear in-memory + disk signing-rule cache so the next request re-fetches rules."""
     global curr_auth, last_check
@@ -50,11 +118,8 @@ def read_request_auth():
         "checksum_constant": "0",
     }
 
-    # *values, = get_request_auth()
-    result = get_request_auth()
-    if not result:
-        raise json.JSONDecodeError("No content")
-    (*values,) = result
+    # get_request_auth returns a checked rule or raises DynamicRuleUnavailable
+    (*values,) = get_request_auth()
 
     request_auth.update(zip(request_auth.keys(), values))
     return request_auth
@@ -78,52 +143,63 @@ def get_request_auth():
 
     dynamic = settings.get_settings().dynamic_rules
     auth = None
+    # (source, error) for each source that gave no rule, for the message
+    failures = []
     if dynamic in {"manual"}:
         try:
             auth = get_request_auth_dynamic_rule_manual()
-        except Exception:
-            pass
+        except Exception as e:
+            failures.append((dynamic, e))
     elif dynamic in {"generic"}:
         try:
             auth = get_request_auth_generic()
-        except Exception:
-            pass
+        except Exception as e:
+            failures.append((dynamic, e))
     elif (dynamic) in {"dc", "digital", "digitalcriminal", "digitalcriminals"}:
         try:
             auth = get_request_auth_digitalcriminals()
-        except Exception:
-            pass
+        except Exception as e:
+            failures.append((dynamic, e))
     elif (dynamic) in {"riley"}:
         try:
             auth = get_request_auth_riley()
-        except Exception:
-            pass
+        except Exception as e:
+            failures.append((dynamic, e))
     elif (dynamic) in {"datawhores"}:
         try:
             auth = get_request_auth_datawhores()
-        except Exception:
-            pass
+        except Exception as e:
+            failures.append((dynamic, e))
     elif (dynamic) in {"xagler"}:
         try:
             auth = get_request_auth_xagler()
-        except Exception:
-            pass
+        except Exception as e:
+            failures.append((dynamic, e))
     elif (dynamic) in {"rafa"}:
         try:
             auth = get_request_auth_rafa()
-        except Exception:
-            pass
+        except Exception as e:
+            failures.append((dynamic, e))
 
     # Fallbacks in case selected provider failed, returned 404, or returned invalid/obsolete rules
     if auth is None or (isinstance(auth, (tuple, list)) and len(auth) > 1 and "26974" in str(auth[1])):
-        for fallback_fn in [get_request_auth_digitalcriminals, get_request_auth_riley]:
+        for name, fallback_fn in [
+            ("digitalcriminals", get_request_auth_digitalcriminals),
+            ("riley", get_request_auth_riley),
+        ]:
             try:
                 cand = fallback_fn()
                 if cand and isinstance(cand, (tuple, list)) and len(cand) > 1 and "26974" not in str(cand[1]):
                     auth = cand
                     break
-            except Exception:
-                pass
+                failures.append((name, UnusableDynamicRule("sent an obsolete rule")))
+            except Exception as e:
+                failures.append((name, e))
+
+    if auth is None:
+        # Not cached, so the next request tries again. Callers that make
+        # several attempts (the auth check) fetch the rule once first.
+        raise DynamicRuleUnavailable(failures)
 
     cache.set("api_onlyfans_sign", auth, of_env.getattr("THIRTY_EXPIRY"))
     curr_auth = auth
@@ -272,6 +348,7 @@ def get_request_auth_digitalcriminals():
 
 
 def request_auth_helper_picker(content):
+    check_rule(content)
     token = content.get("app_token") or content.get("app-token")
     if token:
         import os
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/checkers.py b/OF-Scraper-3.14.7/ofscraper/utils/checkers.py
index d2f2eed..73db8be 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/checkers.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/checkers.py
@@ -8,17 +8,38 @@
 log = logging.getLogger("shared")
 
 
-def check_auth():
+class AuthCheckUnavailable(Exception):
+    """The auth couldn't be checked (network, server or dynamic rule problem)."""
+
+
+class AuthCheckLeft(Exception):
+    """The user chose "Go to Main Menu" in the auth prompt."""
+
+
+def check_auth(include_main_menu=False):
     status = None
     log.info("checking auth status")
     while status != "UP":
-        status = init.getstatus()
+        status, message = init.auth_status()
+        if status == "UNAVAILABLE":
+            # The auth may be fine, so don't report it as failed or ask for it
+            # again, in the GUI or the CLI. An ordinary exception ends a one-off
+            # run or a GUI scrape with this message, and lets the daemon try
+            # its next pass.
+            raise AuthCheckUnavailable(f"Couldn't check the auth: {message}")
         if status != "UP":
             log.info("Auth Failed")
             # In GUI mode skip interactive prompts; the GUI auth dialog handles re-auth
             if getattr(settings.get_args(), "gui", False):
                 log.debug("GUI mode: skipping interactive auth prompt on auth failure")
                 return
-            make.make_auth(auth=auth_file.read_auth())
+            _, choice = make.make_auth(
+                auth=auth_file.read_auth(), include_main_menu=include_main_menu
+            )
+            if choice == "quit":
+                raise SystemExit(0)
+            if choice == "main":
+                # the main menu catches this and shows itself again
+                raise AuthCheckLeft("back to the main menu")
         else:
             break
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/of_env/values/req/req.py b/OF-Scraper-3.14.7/ofscraper/utils/of_env/values/req/req.py
index 20ec23a..69694d2 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/of_env/values/req/req.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/of_env/values/req/req.py
@@ -20,6 +20,13 @@ def load_network_config():
     # Default: 15
     config["POOL_CONNECT_TIMEOUT"] = int(os.getenv("OFSC_POOL_CONNECT_TIMEOUT", "15"))
 
+    # OF_READ_TIMEOUT: Longest wait for the next piece of a response (seconds),
+    # for requests that don't pass their own read timeout. It isn't a limit
+    # on the whole response: a slow response that keeps sending is fine.
+    # 0 means no limit (the session manager turns it into None).
+    # Default: 60
+    config["OF_READ_TIMEOUT"] = int(os.getenv("OFSC_READ_TIMEOUT", "60"))
+
     # MAX_CONNECTIONS: Maximum number of simultaneous network connections.
     # Default: 200
     config["MAX_CONNECTIONS"] = int(os.getenv("OFSC_MAX_CONNECTIONS", "200"))
diff --git a/OF-Scraper-3.14.7/test/unit/test_auth_check_logged_out.py b/OF-Scraper-3.14.7/test/unit/test_auth_check_logged_out.py
new file mode 100644
index 0000000..d962952
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_auth_check_logged_out.py
@@ -0,0 +1,127 @@
+"""The auth check must report a logged-out session as bad auth.
+
+If /me answered {"isAuth": false}, getstatus() said UP: scrape_user() only
+reads isAuth to decide whether to record the user's details. The check is
+in getstatus() only. Anonymous runs ask /me for the user id too (the
+self-media filter), get isAuth false, and get_id() falls back to
+'id_unknown' for that reply, so scrape_user() must keep accepting it.
+"""
+
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import pytest
+
+pytestmark = pytest.mark.unit
+import logging
+from contextlib import contextmanager
+from types import SimpleNamespace
+
+import ofscraper.data.api.init as init
+import ofscraper.data.api.me as me
+import ofscraper.utils.auth.file as auth_file
+import ofscraper.utils.auth.request as auth_requests
+import ofscraper.utils.checkers as checkers
+import ofscraper.utils.me as me_util
+import ofscraper.utils.profiles.data as profile_data
+import ofscraper.utils.settings as settings
+
+
+class AuthPrompted(Exception):
+    pass
+
+
+@pytest.fixture
+def me_replies(monkeypatch):
+    """/me answers with the given JSON through the real me.scrape_user."""
+    run_settings = SimpleNamespace(anon=False, auth_fail=False)
+    run_args = SimpleNamespace(gui=False)
+    monkeypatch.setattr(settings, "get_settings", lambda: run_settings)
+    monkeypatch.setattr(settings, "get_args", lambda: run_args)
+    monkeypatch.setattr(
+        logging.getLogger("shared"), "traceback_", lambda *a, **k: None, raising=False
+    )
+    monkeypatch.setattr(auth_file, "read_auth", lambda: {})
+    # signing isn't part of this test
+    monkeypatch.setattr(auth_requests, "read_request_auth", lambda: {})
+    # scrape_user registers the user's id and names for log redaction, for
+    # the rest of the process; keep the test user out of other tests
+    monkeypatch.setattr(me.sensitive, "add_sensitive_pattern", lambda *a, **k: None)
+    prompts = []
+
+    def make_auth(*args, **kwargs):
+        prompts.append(1)
+        raise AuthPrompted
+
+    monkeypatch.setattr(checkers.make, "make_auth", make_auth)
+
+    def set_reply(data):
+        @contextmanager
+        def requests(url, *args, **kwargs):
+            yield SimpleNamespace(json_=lambda: data)
+
+        @contextmanager
+        def get_ofsession(*args, **kwargs):
+            yield SimpleNamespace(requests=requests)
+
+        monkeypatch.setattr(
+            me.manager,
+            "Manager",
+            SimpleNamespace(session=SimpleNamespace(get_ofsession=get_ofsession)),
+        )
+
+    set_reply.settings = run_settings
+    set_reply.args = run_args
+    set_reply.prompts = prompts
+    return set_reply
+
+
+def test_logged_out_session_is_reported_as_bad_auth(me_replies):
+    me_replies({"isAuth": False})
+    assert init.getstatus() == "DOWN"
+
+
+def test_logged_out_session_asks_for_auth_in_the_cli(me_replies, caplog):
+    me_replies({"isAuth": False})
+    with caplog.at_level(logging.INFO, logger="shared"):
+        with pytest.raises(AuthPrompted):
+            checkers.check_auth()
+    assert "isn't logged in" in caplog.text
+    assert "Auth Failed" in caplog.text
+
+
+def test_logged_out_session_is_auth_failed_in_the_gui(me_replies, caplog):
+    # GUI scrapes log "Auth Failed" and carry on, as for a 401
+    me_replies.args.gui = True
+    me_replies({"isAuth": False})
+    with caplog.at_level(logging.INFO, logger="shared"):
+        assert checkers.check_auth() is None
+    assert "Auth Failed" in caplog.text
+    assert me_replies.prompts == []
+
+
+def test_logged_in_session_passes(me_replies):
+    me_replies({"isAuth": True, "id": 1, "username": "u1", "name": "n1"})
+    assert init.getstatus() == "UP"
+
+
+def test_anon_run_still_gets_unknown_id(me_replies, monkeypatch):
+    # --anon metadata runs ask /me for the user id (self-media filter), and
+    # /me answers isAuth false because no one is logged in
+    me_replies.settings.anon = True
+    monkeypatch.setattr(profile_data, "get_active_profile", lambda: "a_profile")
+    monkeypatch.setattr(profile_data, "currentProfile", None)
+    monkeypatch.setattr(profile_data, "currentData", None)
+    me_replies({"isAuth": False})
+
+    assert me_util.get_id() == "id_unknown"
+    assert me_util.get_id() == "id_unknown"
+
+    # the same reply still fails the auth check of a logged-in run
+    me_replies.settings.anon = False
+    assert init.getstatus() == "DOWN"
diff --git a/OF-Scraper-3.14.7/test/unit/test_auth_check_network.py b/OF-Scraper-3.14.7/test/unit/test_auth_check_network.py
new file mode 100644
index 0000000..b1d4b5e
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_auth_check_network.py
@@ -0,0 +1,454 @@
+"""A network, server or dynamic-rule problem must not be reported as bad auth.
+
+The auth check (check_auth -> getstatus), Test Credentials and the model
+list all reported a timeout, a 5xx, a 429, a reply that isn't JSON, or rule
+hosts that couldn't give a usable rule as "Auth Failed", "Could not verify
+credentials" or "Please check your auth information".
+
+When no rule host gave a rule, get_request_auth returned None and
+read_request_auth raised a TypeError (json.JSONDecodeError needs three
+arguments). None was never cached, so every /me retry fetched the rule again
+from all three rule hosts, each with its own retries.
+
+These tests go through the real check, the real rule fetch (with its
+fallback chain) and the real session manager. Only httpx.Client.send is
+replaced, so nothing leaves the machine, and time.sleep, so the retry waits
+don't slow the tests down.
+"""
+
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import pytest
+
+pytestmark = pytest.mark.unit
+import json
+import logging
+import socket
+import time
+from types import SimpleNamespace
+
+import aiohttp
+import httpx
+import yarl
+
+import ofscraper.data.api.init as init
+import ofscraper.data.api.me as me
+import ofscraper.managers.manager as manager
+import ofscraper.utils.auth.file as auth_file
+import ofscraper.utils.auth.request as auth_requests
+import ofscraper.utils.checkers as checkers
+import ofscraper.utils.of_env.of_env as of_env
+import ofscraper.utils.settings as settings
+from ofscraper.managers.sessionHandler import SessionHandler
+
+RULE = {
+    "static_param": "a",
+    "format": "1:{}:{:x}:2",
+    "checksum_indexes": [1, 2],
+    "checksum_constant": 3,
+}
+AUTH = {
+    "sess": "s",
+    "auth_id": "1",
+    "auth_uid": "",
+    "user_agent": "Mozilla/5.0 Chrome/120.0",
+    "x-bc": "x",
+}
+USER = {"isAuth": True, "id": 1, "username": "u1", "name": "n1"}
+
+
+class AuthPrompted(Exception):
+    pass
+
+
+class Settings(SimpleNamespace):
+    # any other setting is unset, as with no args and no config
+    def __getattr__(self, name):
+        return None
+
+
+class _Manager:
+    # like the app's Manager: `session` is a read-only property, so the
+    # GUI's `Manager.session = None` fails and is ignored
+    @property
+    def session(self):
+        return SessionHandler()
+
+
+class Offline:
+    """Answers every request in place of the network, and counts them."""
+
+    def __init__(self):
+        self.rule_urls = {
+            of_env.getattr(key): name
+            for key, name in [
+                ("DATAWHORES_URL", "datawhores"),
+                ("DIGITALCRIMINALS", "digitalcriminals"),
+                ("RILEY_URL", "riley"),
+            ]
+        }
+        self.rule_requests = []
+        self.me_requests = 0
+        self.other_requests = []
+        # what each rule host and /me answer: a dict/list/None for JSON, an
+        # int for a status code, an exception, or a str for a text body
+        self.rules = {name: RULE for name in self.rule_urls.values()}
+        self.me = USER
+
+    def send(self, client, request, **kwargs):
+        url = str(request.url)
+        if url in self.rule_urls:
+            name = self.rule_urls[url]
+            self.rule_requests.append(name)
+            return self._answer(request, self.rules[name])
+        if url.split("?")[0] == of_env.getattr("meEP"):
+            self.me_requests += 1
+            return self._answer(request, self.me)
+        self.other_requests.append(url)
+        return httpx.Response(404, request=request)
+
+    @staticmethod
+    def _answer(request, what):
+        if isinstance(what, Exception):
+            raise type(what)(str(what), request=request)
+        if isinstance(what, int):
+            return httpx.Response(what, request=request, text="error")
+        if isinstance(what, str):
+            return httpx.Response(200, request=request, text=what)
+        return httpx.Response(
+            200,
+            request=request,
+            content=json.dumps(what).encode(),
+            headers={"content-type": "application/json"},
+        )
+
+
+@pytest.fixture
+def offline(monkeypatch):
+    net = Offline()
+    monkeypatch.setattr(
+        httpx.Client, "send", lambda self, request, **kw: net.send(self, request, **kw)
+    )
+
+    def no_lookups(*args, **kwargs):
+        raise AssertionError("a test tried to resolve a host name")
+
+    monkeypatch.setattr(socket, "getaddrinfo", no_lookups)
+    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)
+    run_settings = Settings(
+        anon=False,
+        dynamic_rules="datawhores",
+        ssl_verify="false",
+        cached_disabled=True,
+        auth_fail=False,
+    )
+    run_args = SimpleNamespace(gui=False)
+    monkeypatch.setattr(settings, "get_settings", lambda: run_settings)
+    monkeypatch.setattr(settings, "get_args", lambda: run_args)
+    monkeypatch.setattr(auth_file, "read_auth", lambda: dict(AUTH))
+    monkeypatch.setattr(manager, "Manager", _Manager())
+    # no rule cached from an earlier check, and nothing written to the cache
+    monkeypatch.setattr(auth_requests, "curr_auth", None)
+    monkeypatch.setattr(auth_requests, "last_check", None)
+    monkeypatch.setattr(auth_requests.cache, "set", lambda *a, **k: None)
+    # scrape_user registers the user's id and names for log redaction, for
+    # the rest of the process; keep the test user out of other tests
+    monkeypatch.setattr(me.sensitive, "add_sensitive_pattern", lambda *a, **k: None)
+    # traceback_ is added to loggers by the app's log setup
+    monkeypatch.setattr(
+        logging.getLogger("shared"), "traceback_", lambda *a, **k: None, raising=False
+    )
+    prompts = []
+
+    def make_auth(*args, **kwargs):
+        prompts.append(1)
+        raise AuthPrompted
+
+    monkeypatch.setattr(checkers.make, "make_auth", make_auth)
+    net.prompts = prompts
+    net.settings = run_settings
+    net.args = run_args
+    return net
+
+
+def timeout():
+    return httpx.ConnectTimeout("timed out")
+
+
+def run_check(caplog):
+    """Run the auth check; it must end with AuthCheckUnavailable."""
+    error = None
+    with caplog.at_level(logging.INFO, logger="shared"):
+        try:
+            checkers.check_auth()
+        except Exception as e:
+            error = e
+    assert "Auth Failed" not in caplog.text
+    assert type(error).__name__ == "AuthCheckUnavailable", repr(error)
+    return str(error)
+
+
+# --- the auth check (scrapes) ---------------------------------------------
+
+
+@pytest.mark.parametrize("gui", [False, True], ids=["cli", "gui"])
+def test_rule_hosts_down_is_not_bad_auth(offline, caplog, gui):
+    offline.args.gui = gui
+    offline.rules = {name: timeout() for name in offline.rules}
+
+    message = run_check(caplog)
+
+    assert "Couldn't get a usable dynamic rule" in message
+    assert (
+        "datawhores: couldn't reach raw.githubusercontent.com (timed out)" in message
+    )
+    assert "digitalcriminals:" in message and "riley:" in message
+    assert offline.prompts == []
+
+
+def test_failed_rule_fetch_is_not_repeated_by_me_retries(offline, caplog):
+    offline.rules = {name: timeout() for name in offline.rules}
+
+    run_check(caplog)
+
+    # the selected rule host and the two fallbacks, 3 tries each (GIT_NUM_TRIES),
+    # once for the whole check rather than once per /me try
+    assert sorted(set(offline.rule_requests)) == [
+        "datawhores",
+        "digitalcriminals",
+        "riley",
+    ]
+    assert len(offline.rule_requests) == 9
+    assert offline.me_requests == 0
+
+
+@pytest.mark.parametrize(
+    "rule,detail",
+    [
+        ({}, "unusable rule: missing static_param, format, checksum_indexes, checksum_constant"),
+        (None, "unusable rule: expected a JSON object, got null"),
+        ([], "unusable rule: expected a JSON object, got list"),
+        (
+            {"static_param": "a", "suffix": "s", "checksum_indexes": [1]},
+            "unusable rule: missing prefix, checksum_constant",
+        ),
+        (500, "raw.githubusercontent.com returned 500"),
+        ("<html>blocked</html>", "the reply isn't JSON"),
+    ],
+    ids=["empty-object", "null", "list", "missing-keys", "server-error", "not-json"],
+)
+def test_unusable_rule_is_reported_as_unusable(offline, caplog, rule, detail):
+    offline.rules = {name: rule for name in offline.rules}
+
+    message = run_check(caplog)
+
+    assert f"datawhores: {detail}" in message
+    assert offline.prompts == []
+
+
+def test_a_broken_selected_rule_still_falls_back(offline, caplog):
+    # cjb's fallback chain: the selected source fails, digitalcriminals works
+    offline.rules["datawhores"] = {}
+    checkers.check_auth()
+    assert offline.rule_requests == ["datawhores", "digitalcriminals"]
+    assert offline.me_requests == 1
+
+
+@pytest.mark.parametrize(
+    "reply,message",
+    [
+        (httpx.ConnectTimeout("timed out"), "Couldn't reach onlyfans.com (timed out)"),
+        (httpx.ConnectError("refused"), "Couldn't reach onlyfans.com (connection failed)"),
+        (httpx.ReadTimeout("timed out"), "Couldn't reach onlyfans.com (timed out)"),
+        (429, "onlyfans.com is rate limiting requests"),
+        (500, "onlyfans.com returned 500: the server had an error"),
+        (502, "onlyfans.com returned 502: the server had an error"),
+        ("<html>Sign in to the wifi</html>", "Got a reply that isn't JSON from OnlyFans"),
+    ],
+    ids=["connect-timeout", "connect-error", "read-timeout", "429", "500", "502", "not-json"],
+)
+@pytest.mark.parametrize("gui", [False, True], ids=["cli", "gui"])
+def test_me_network_and_server_errors_are_not_bad_auth(
+    offline, caplog, reply, message, gui
+):
+    offline.args.gui = gui
+    offline.me = reply
+
+    assert message in run_check(caplog)
+    assert offline.prompts == []
+
+
+@pytest.mark.parametrize("status", [400, 401, 403])
+def test_rejected_auth_still_asks_for_auth(offline, caplog, status):
+    offline.me = status
+    with caplog.at_level(logging.INFO, logger="shared"):
+        with pytest.raises(AuthPrompted):
+            checkers.check_auth()
+    assert "Auth Failed" in caplog.text
+
+
+@pytest.mark.parametrize("status", [400, 401, 403])
+def test_rejected_auth_in_the_gui_is_still_auth_failed(offline, caplog, status):
+    offline.args.gui = True
+    offline.me = status
+    with caplog.at_level(logging.INFO, logger="shared"):
+        assert checkers.check_auth() is None
+    assert "Auth Failed" in caplog.text
+    assert offline.prompts == []
+
+
+def test_good_auth_passes(offline):
+    checkers.check_auth()
+    assert offline.me_requests == 1
+
+
+@pytest.mark.parametrize(
+    "error,message",
+    [
+        (
+            aiohttp.ClientConnectorError(
+                SimpleNamespace(host="onlyfans.com", port=443, ssl=True),
+                OSError("refused"),
+            ),
+            "Couldn't reach onlyfans.com (connection failed)",
+        ),
+        (
+            aiohttp.ClientResponseError(
+                aiohttp.RequestInfo(
+                    yarl.URL("https://onlyfans.com/api2/v2/subscriptions"),
+                    "GET",
+                    {},
+                    yarl.URL("https://onlyfans.com/api2/v2/subscriptions"),
+                ),
+                (),
+                status=503,
+            ),
+            "onlyfans.com returned 503: the server had an error",
+        ),
+    ],
+    ids=["aiohttp-connect", "aiohttp-503"],
+)
+def test_async_errors_are_network_problems(error, message):
+    # the model list's async requests raise aiohttp errors
+    assert message in init.unavailable_message(error)
+
+
+# --- Test Credentials and the model list (GUI) ----------------------------
+
+
+@pytest.fixture
+def gui_auth(offline, tmp_path, monkeypatch):
+    pytest.importorskip("PyQt6.QtWidgets")
+    from ofscraper.gui.dialogs import auth_dialog
+    from ofscraper.gui.utils import auth_errors
+    import ofscraper.utils.auth.utils.dict as auth_dict
+    import ofscraper.utils.paths.common as common_paths
+
+    # Test Credentials writes the auth it tests to auth.json, then restores it
+    monkeypatch.setattr(common_paths, "get_auth_file", lambda *a, **k: tmp_path / "auth.json")
+    monkeypatch.setattr(auth_dict, "get_auth_dict", lambda *a, **k: dict(AUTH))
+
+    offline.auth_dialog = auth_dialog
+    offline.auth_errors = auth_errors
+    offline.args.gui = True
+    return offline
+
+
+def test_credentials_with_rule_hosts_down_are_not_reported_invalid(gui_auth):
+    gui_auth.rules = {name: timeout() for name in gui_auth.rules}
+
+    result, text = gui_auth.auth_dialog._validate_of_credentials(dict(AUTH))
+
+    assert result == "unavailable", text  # CRED_TEST_UNAVAILABLE
+    assert "network or server problem, not a problem with your auth" in text
+    assert "Couldn't get a usable dynamic rule" in text
+    # the rule is fetched once for the test, not once per /me try
+    assert len(gui_auth.rule_requests) == 9
+    assert gui_auth.me_requests == 0
+
+
+@pytest.mark.parametrize(
+    "reply,message",
+    [
+        (httpx.ConnectTimeout("timed out"), "Couldn't reach onlyfans.com (timed out)"),
+        (502, "onlyfans.com returned 502"),
+        (429, "onlyfans.com is rate limiting requests"),
+        ("<html>blocked</html>", "Got a reply that isn't JSON"),
+    ],
+    ids=["timeout", "502", "429", "not-json"],
+)
+def test_credentials_with_onlyfans_unreachable_are_not_reported_invalid(
+    gui_auth, reply, message
+):
+    gui_auth.me = reply
+
+    result, text = gui_auth.auth_dialog._validate_of_credentials(dict(AUTH))
+
+    assert result == "unavailable", text  # CRED_TEST_UNAVAILABLE
+    assert message in text
+    assert "not a problem with your auth" in text
+
+
+def test_rejected_credentials_are_still_invalid(gui_auth):
+    gui_auth.me = 401
+
+    result, text = gui_auth.auth_dialog._validate_of_credentials(dict(AUTH))
+
+    assert result is False, text
+    assert "Auth error" in text
+
+
+def test_model_list_with_rule_hosts_down_is_not_an_auth_problem(gui_auth, tmp_path, monkeypatch):
+    from ofscraper.gui.utils import model_fetch
+
+    gui_auth.rules = {name: timeout() for name in gui_auth.rules}
+    import ofscraper.utils.auth.utils.dict as auth_dict
+
+    monkeypatch.setattr(auth_dict, "get_auth_dict", lambda *a, **k: dict(AUTH))
+
+    with pytest.raises(Exception) as e:
+        model_fetch.fetch_subscription_models(timeout_sec=30)
+    main, detail = gui_auth.auth_errors.model_load_failure_dialog_text(str(e.value))
+
+    assert "network or server problem, not a problem with your auth" in main
+    assert "Couldn't get a usable dynamic rule" in main
+    assert "check your auth information" not in main
+    assert detail == str(e.value)
+
+
+def test_model_list_with_onlyfans_down_is_not_an_auth_problem(gui_auth, monkeypatch):
+    from ofscraper.gui.utils import model_fetch
+    import ofscraper.utils.auth.utils.dict as auth_dict
+
+    monkeypatch.setattr(auth_dict, "get_auth_dict", lambda *a, **k: dict(AUTH))
+    monkeypatch.setattr(
+        httpx.Client,
+        "send",
+        lambda self, request, **kw: (
+            gui_auth.send(self, request, **kw)
+            if str(request.url) in gui_auth.rule_urls
+            else Offline._answer(request, 502)
+        ),
+    )
+
+    with pytest.raises(Exception) as e:
+        model_fetch.fetch_subscription_models(timeout_sec=30)
+    main, _ = gui_auth.auth_errors.model_load_failure_dialog_text(str(e.value))
+
+    assert "returned 502: the server had an error" in main
+    assert "check your auth information" not in main
+
+
+def test_model_list_auth_errors_are_unchanged():
+    from ofscraper.gui.utils import auth_errors
+
+    main, _ = auth_errors.model_load_failure_dialog_text(
+        "Model list fetch failed: Client error '401 Unauthorized'"
+    )
+    assert "Please check your auth information" in main
diff --git a/OF-Scraper-3.14.7/test/unit/test_auth_prompt_choice.py b/OF-Scraper-3.14.7/test/unit/test_auth_prompt_choice.py
new file mode 100644
index 0000000..120f9d8
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_auth_prompt_choice.py
@@ -0,0 +1,84 @@
+"""The CLI auth prompt must act on "Quit" and "Go to Main Menu".
+
+check_auth() ignored what make_auth() returned, so picking either one
+brought the auth prompt straight back. (GUI mode never shows this prompt.)
+"""
+
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import pytest
+
+pytestmark = pytest.mark.unit
+from types import SimpleNamespace
+
+import ofscraper.data.api.init as init
+import ofscraper.utils.checkers as checkers
+import ofscraper.utils.menu as menu
+import ofscraper.utils.settings as settings
+
+
+class PromptAgain(Exception):
+    """The auth prompt came back after the user left it."""
+
+
+@pytest.fixture
+def failed_auth(monkeypatch):
+    """The auth check fails as bad auth; the auth prompt answers with `choice`."""
+    monkeypatch.setattr(init, "auth_status", lambda: ("DOWN", None))
+    monkeypatch.setattr(checkers.auth_file, "read_auth", lambda: {})
+    monkeypatch.setattr(settings, "get_args", lambda: SimpleNamespace(gui=False))
+    monkeypatch.setattr(
+        settings, "get_settings", lambda: SimpleNamespace(daemon=False)
+    )
+    calls = []
+
+    def answer(choice):
+        def make_auth(auth=None, include_main_menu=False):
+            calls.append(include_main_menu)
+            if len(calls) > 1:
+                raise PromptAgain
+            return None, choice
+
+        monkeypatch.setattr(checkers.make, "make_auth", make_auth)
+        return calls
+
+    return answer
+
+
+def test_quit_in_the_auth_prompt_quits(failed_auth):
+    calls = failed_auth("quit")
+    with pytest.raises(SystemExit):
+        checkers.check_auth()
+    assert len(calls) == 1
+
+
+def test_main_in_the_auth_prompt_returns_to_the_main_menu(failed_auth, monkeypatch):
+    calls = failed_auth("main")
+    # main menu: pick an action and run it, then quit at the next main menu
+    main_answers = iter(["action", "quit"])
+    monkeypatch.setattr(menu.prompts, "main_prompt", lambda: next(main_answers))
+    monkeypatch.setattr(menu.prompts, "action_prompt", lambda: "download")
+    monkeypatch.setattr(
+        menu.console,
+        "get_shared_console",
+        lambda: SimpleNamespace(clear_live=lambda: None),
+    )
+
+    assert menu.main_menu_action() is True
+    # the auth prompt offered "Go to Main Menu" and wasn't shown again
+    assert calls == [True]
+    assert next(main_answers, None) is None
+
+
+def test_other_runs_are_not_offered_the_main_menu(failed_auth):
+    # one-off runs, the daemon and check/manual/metadata call check_auth()
+    calls = failed_auth("quit")
+    with pytest.raises(SystemExit):
+        checkers.check_auth()
+    assert calls == [False]
diff --git a/OF-Scraper-3.14.7/test/unit/test_download_limit.py b/OF-Scraper-3.14.7/test/unit/test_download_limit.py
new file mode 100644
index 0000000..93846ea
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_download_limit.py
@@ -0,0 +1,109 @@
+"""The download speed limit (download_limit) must slow downloads down.
+
+download_session and metadata_session applied the limit in an override of
+_httpx_funct_async, a method nothing calls: requests_async goes through
+_aio_funct. So the limit had no effect.
+"""
+
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import pytest
+
+pytestmark = pytest.mark.unit
+import asyncio
+import time
+from types import SimpleNamespace
+
+from aiohttp import web
+
+import ofscraper.utils.settings as settings
+from ofscraper.managers.sessionmanager.ofsession import (
+    download_session,
+    metadata_session,
+)
+
+LIMIT = 256 * 1024  # bytes per second
+BODY = b"x" * (3 * LIMIT)
+QUIET = SimpleNamespace(
+    traceback_=lambda *a, **k: None,
+    debug=lambda *a, **k: None,
+    warning=lambda *a, **k: None,
+)
+
+
+def use_limit(monkeypatch, limit):
+    monkeypatch.setattr(
+        settings,
+        "get_settings",
+        lambda: SimpleNamespace(
+            ssl_verify="false",
+            cached_disabled=True,
+            download_limit=limit,
+            command="download",
+        ),
+    )
+
+
+async def serve():
+    async def body(request):
+        return web.Response(body=BODY)
+
+    app = web.Application()
+    app.router.add_get("/f", body)
+    runner = web.AppRunner(app)
+    await runner.setup()
+    site = web.TCPSite(runner, "127.0.0.1", 0)
+    await site.start()
+    port = site._server.sockets[0].getsockname()[1]
+    return runner, f"http://127.0.0.1:{port}/f"
+
+
+def download(session_class, chunk_size):
+    async def run():
+        runner, url = await serve()
+        try:
+            async with session_class(log=QUIET, wait_min=0, wait_max=0) as c:
+                # no auth for a local server
+                c._create_headers = lambda headers, *a: headers or {}
+                c._create_cookies = lambda: None
+                start = time.monotonic()
+                received = 0
+                async with c.requests_async(url=url) as r:
+                    async for chunk in r.iter_chunked(chunk_size):
+                        received += len(chunk)
+                seconds = time.monotonic() - start
+        finally:
+            await runner.cleanup()
+        return received, seconds
+
+    return asyncio.run(run())
+
+
+def test_download_session_keeps_to_the_limit(monkeypatch):
+    use_limit(monkeypatch, LIMIT)
+    received, seconds = download(download_session, 64 * 1024)
+    assert received == len(BODY)
+    # 3 s of data; the first second's worth may arrive at once
+    assert 1.6 < seconds < 4, seconds
+
+
+def test_metadata_session_keeps_to_the_limit_once(monkeypatch):
+    # metadata reads in 30 MB chunks, more than the limit allows per second;
+    # it inherits download_session's limit and mustn't apply it twice
+    use_limit(monkeypatch, LIMIT)
+    received, seconds = download(metadata_session, 30 * 1024 * 1024)
+    assert received == len(BODY)
+    assert 1.6 < seconds < 4, seconds
+
+
+def test_no_limit_is_not_slowed(monkeypatch):
+    use_limit(monkeypatch, 0)
+    received, seconds = download(download_session, 64 * 1024)
+    assert received == len(BODY)
+    assert seconds < 1, seconds
diff --git a/OF-Scraper-3.14.7/test/unit/test_download_limit_help.py b/OF-Scraper-3.14.7/test/unit/test_download_limit_help.py
new file mode 100644
index 0000000..29f1937
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_download_limit_help.py
@@ -0,0 +1,67 @@
+"""The download-limit help must say the limit is shared by all downloads.
+
+The CLI config prompt said "for each thread", and the Config page and its
+help page didn't say either way. One limit is shared by every download in
+the download session.
+"""
+
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import pytest
+
+pytestmark = pytest.mark.unit
+import inspect
+import pathlib
+import re
+
+import ofscraper.prompts.prompt_groups.config as config_prompts
+
+HELP = (
+    pathlib.Path(__file__).resolve().parents[2]
+    / "ofscraper"
+    / "gui"
+    / "help"
+    / "GUI_HELP.md"
+)
+
+
+def test_cli_prompt_says_shared():
+    source = inspect.getsource(config_prompts)
+    lines = [line for line in source.splitlines() if "download speed" in line]
+    assert len(lines) == 2, lines  # the config overview and the prompt
+    for line in lines:
+        assert not re.search(r"each\s+thread", line), line
+        assert "shared by all downloads" in line, line
+
+
+def test_gui_help_says_shared():
+    lines = [
+        line
+        for line in HELP.read_text(encoding="utf-8").splitlines()
+        if "performance_options.download_limit" in line
+    ]
+    assert len(lines) == 1, lines
+    assert "shared by all downloads, not set per thread" in lines[0]
+
+
+def test_config_page_tooltip_says_shared():
+    QtWidgets = pytest.importorskip("PyQt6.QtWidgets")
+    from ofscraper.gui.dialogs import config_dialog
+
+    app = QtWidgets.QApplication.instance()
+    if app is None:
+        app = QtWidgets.QApplication([])
+    elif not isinstance(app, QtWidgets.QApplication):
+        pytest.skip("a QCoreApplication from another test is already running")
+    page = config_dialog.ConfigPage()
+    try:
+        tooltip = page._widgets["download_limit"].toolTip()
+    finally:
+        page.deleteLater()
+    assert "shared by all downloads, not set per thread" in tooltip
diff --git a/OF-Scraper-3.14.7/test/unit/test_download_retry_cancel.py b/OF-Scraper-3.14.7/test/unit/test_download_retry_cancel.py
new file mode 100644
index 0000000..3809e79
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_download_retry_cancel.py
@@ -0,0 +1,82 @@
+"""Cancelling a download must stop it, not start another attempt.
+
+download_retry, the downloaders' retry loop, retried every exception except
+KeyboardInterrupt, the out-of-space message and errors marked no_retry.
+tenacity's attempt swallows asyncio.CancelledError, so a Ctrl+C (or a
+cancelled task) during a transfer started the download again.
+"""
+
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import pytest
+
+pytestmark = pytest.mark.unit
+import asyncio
+
+from tenacity import stop_after_attempt, wait_none
+
+from ofscraper.commands.scraper.actions.download.utils.retries import download_retry
+
+
+def test_cancel_during_a_download_attempt_stops_it():
+    attempts = []
+
+    async def download():
+        # the default retry condition is what's under test
+        async for attempt in download_retry(stop=stop_after_attempt(3), wait=wait_none()):
+            with attempt:
+                attempts.append(1)
+                await asyncio.sleep(10)
+
+    async def run():
+        task = asyncio.create_task(download())
+        await asyncio.sleep(0.1)
+        task.cancel()
+        done, _ = await asyncio.wait({task}, timeout=3)
+        stopped = task in done and task.cancelled()
+        count = len(attempts)
+        while not task.done():
+            task.cancel()
+            await asyncio.wait({task}, timeout=1)
+        return stopped, count
+
+    stopped, count = asyncio.run(run())
+    assert stopped, f"the cancel was swallowed; {count} attempts were started"
+    assert count == 1
+
+
+def test_a_failed_download_attempt_is_still_retried():
+    attempts = []
+
+    async def download():
+        async for attempt in download_retry(stop=stop_after_attempt(3), wait=wait_none()):
+            with attempt:
+                attempts.append(1)
+                if len(attempts) < 3:
+                    raise OSError("connection reset")
+
+    asyncio.run(download())
+    assert len(attempts) == 3
+
+
+def test_a_no_retry_error_is_still_not_retried():
+    attempts = []
+
+    class Fatal(Exception):
+        no_retry = True
+
+    async def download():
+        async for attempt in download_retry(stop=stop_after_attempt(3), wait=wait_none()):
+            with attempt:
+                attempts.append(1)
+                raise Fatal("don't retry")
+
+    with pytest.raises(Fatal):
+        asyncio.run(download())
+    assert len(attempts) == 1
diff --git a/OF-Scraper-3.14.7/test/unit/test_download_session_zero_args.py b/OF-Scraper-3.14.7/test/unit/test_download_session_zero_args.py
new file mode 100644
index 0000000..40d8673
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_download_session_zero_args.py
@@ -0,0 +1,158 @@
+"""A 0 passed to the download session must be kept, not replaced.
+
+download_session set its defaults with `x or default`, so 0 tries, a 0 s
+wait or a read timeout of 0 passed to it became the default before
+sessionManager.__init__ could see it. Only None means "use the default".
+"""
+
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import pytest
+
+pytestmark = pytest.mark.unit
+import asyncio
+import socket
+import threading
+import time
+from types import SimpleNamespace
+
+from aiohttp import web
+
+import ofscraper.utils.settings as settings
+from ofscraper.managers.sessionmanager.ofsession import download_session
+
+QUIET = SimpleNamespace(
+    traceback_=lambda *a, **k: None,
+    debug=lambda *a, **k: None,
+    warning=lambda *a, **k: None,
+)
+
+
+@pytest.fixture(autouse=True)
+def plain_settings(monkeypatch):
+    monkeypatch.setattr(
+        settings,
+        "get_settings",
+        lambda: SimpleNamespace(
+            ssl_verify="false",
+            cached_disabled=True,
+            download_limit=0,
+            command="download",
+        ),
+    )
+
+
+def failing_requests(**session_args):
+    """Count requests to a server that always answers 500, and time them."""
+    calls = []
+
+    async def fail(request):
+        calls.append(1)
+        return web.Response(status=500, text="try again")
+
+    async def run():
+        app = web.Application()
+        app.router.add_get("/f", fail)
+        runner = web.AppRunner(app)
+        await runner.setup()
+        site = web.TCPSite(runner, "127.0.0.1", 0)
+        await site.start()
+        url = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/f"
+        try:
+            async with download_session(log=QUIET, **session_args) as c:
+                # no auth for a local server
+                c._create_headers = lambda headers, *a: headers or {}
+                c._create_cookies = lambda: None
+                start = time.monotonic()
+                with pytest.raises(Exception):
+                    async with c.requests_async(url=url):
+                        pass
+                return len(calls), time.monotonic() - start
+        finally:
+            await runner.cleanup()
+
+    return asyncio.run(run())
+
+
+def test_zero_waits_are_kept():
+    calls, seconds = failing_requests(retries=3, wait_min=0, wait_max=0)
+    assert calls == 3
+    # the default waits are 2 to 3 s between tries
+    assert seconds < 1, seconds
+
+
+def test_zero_retries_is_kept():
+    # stop_after_attempt(0) stops after the first try
+    calls, _ = failing_requests(retries=0, wait_min=0, wait_max=0)
+    assert calls == 1
+
+
+def slow_server():
+    """Answers each request after 1.5 s, on its own thread."""
+    sock = socket.socket()
+    sock.bind(("127.0.0.1", 0))
+    sock.listen(8)
+
+    def reply(conn):
+        with conn:
+            conn.recv(65536)
+            time.sleep(1.5)
+            conn.sendall(
+                b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"
+            )
+
+    def accept():
+        while True:
+            try:
+                conn, _ = sock.accept()
+            except OSError:
+                return
+            threading.Thread(target=reply, args=(conn,), daemon=True).start()
+
+    threading.Thread(target=accept, daemon=True).start()
+    return sock, f"http://127.0.0.1:{sock.getsockname()[1]}/f"
+
+
+def test_zero_read_timeout_means_no_limit():
+    # 0 means no limit, as for OFSC_READ_TIMEOUT: sessionManager turns it into
+    # None, but only if the 0 reaches it
+    assert download_session(log=QUIET, read_timeout=0)._read_timeout is None
+
+
+def test_zero_read_timeout_means_no_limit_on_the_sync_path():
+    sock, url = slow_server()
+    try:
+        with download_session(log=QUIET, read_timeout=0, retries=1) as c:
+            with c.requests(url) as r:
+                assert r.text_() == "ok"
+    finally:
+        sock.close()
+
+
+def test_zero_read_timeout_means_no_limit_on_the_async_path():
+    sock, url = slow_server()
+
+    async def go():
+        async with download_session(log=QUIET, read_timeout=0, retries=1) as c:
+            c._create_headers = lambda headers, *a: headers or {}
+            c._create_cookies = lambda: None
+            async with c.requests_async(url=url) as r:
+                return await r.text_()
+
+    try:
+        assert asyncio.run(go()) == "ok"
+    finally:
+        sock.close()
+
+
+def test_none_still_means_the_default():
+    c = download_session(log=QUIET)
+    assert c._retries > 0
+    assert c._wait_min > 0
+    assert c._read_timeout > 0
diff --git a/OF-Scraper-3.14.7/test/unit/test_gui_download_limit_units.py b/OF-Scraper-3.14.7/test/unit/test_gui_download_limit_units.py
new file mode 100644
index 0000000..2688d95
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_gui_download_limit_units.py
@@ -0,0 +1,113 @@
+"""The Config page's "Download Speed Limit (KB/s)" must mean KB/s.
+
+The page saved the number as typed, but OF-Scraper reads a bare number as
+bytes per second (and raises anything under 1024 to 1024). So typing 500,
+meaning 500 KB/s, set a limit of about 1 KB/s.
+"""
+
+import pytest
+
+pytestmark = pytest.mark.unit
+
+QtWidgets = pytest.importorskip("PyQt6.QtWidgets")
+
+import ofscraper.gui.utils.config_validation as config_validation  # noqa: E402
+import ofscraper.utils.config.data as config_data  # noqa: E402
+import ofscraper.utils.config.file as config_file  # noqa: E402
+from ofscraper.gui.dialogs import config_dialog  # noqa: E402
+
+
+@pytest.fixture
+def qapp():
+    app = QtWidgets.QApplication.instance()
+    if app is None:
+        app = QtWidgets.QApplication([])
+    elif not isinstance(app, QtWidgets.QApplication):
+        pytest.skip("a QCoreApplication from another test is already running")
+    return app
+
+
+@pytest.fixture
+def page(qapp, monkeypatch):
+    saved = []
+    monkeypatch.setattr(config_file, "write_config", lambda config: saved.append(config))
+    monkeypatch.setattr(
+        config_validation, "show_config_validation_dialog", lambda *a, **k: True
+    )
+    # the page reports with modal message boxes; record them instead
+    messages = []
+
+    class Boxes:
+        StandardButton = QtWidgets.QMessageBox.StandardButton
+
+        @staticmethod
+        def _record(kind):
+            def box(parent, title, text, *a, **k):
+                messages.append((kind, title, text))
+                return QtWidgets.QMessageBox.StandardButton.Ok
+
+            return box
+
+    for kind in ("information", "warning", "critical", "question"):
+        setattr(Boxes, kind, staticmethod(Boxes._record(kind)))
+    monkeypatch.setattr(config_dialog, "QMessageBox", Boxes)
+    p = config_dialog.ConfigPage()
+    p.saved = saved
+    p.messages = messages
+    yield p
+    p.deleteLater()
+
+
+def effective_limit(config):
+    """Bytes per second, the way OF-Scraper reads the saved config."""
+    limit = config_data.get_download_limit(config=config)
+    # settings.merged_settings raises a set limit to at least 1024
+    return max(limit, 1024) if limit else limit
+
+
+def show(page, stored):
+    page._config = {"performance_options": {"download_limit": stored}}
+    monkey_config = page._config
+
+    import ofscraper.utils.config.config as config_mod
+
+    real_read = config_mod.read_config
+    config_mod.read_config = lambda update=False: monkey_config
+    try:
+        page._load_config()
+    finally:
+        config_mod.read_config = real_read
+    return page._widgets["download_limit"].value()
+
+
+def test_typing_500_saves_about_500_kb_per_second(page):
+    page._widgets["download_limit"].setValue(500)
+    page._save_config()
+    assert page.saved, f"the page didn't save: {page.messages}"
+    limit = effective_limit(page.saved[-1])
+    assert 450_000 <= limit <= 550_000, limit
+
+
+def test_zero_still_means_unlimited(page):
+    page._widgets["download_limit"].setValue(0)
+    page._save_config()
+    assert effective_limit(page.saved[-1]) == 0
+
+
+def test_a_saved_limit_is_shown_back_in_kb_per_second(page):
+    # what the page saves for 500, and what OF-Scraper writes back for --download-limit 500K
+    assert show(page, 500_000) == 500
+    assert show(page, "500K") == 500
+    assert show(page, 0) == 0
+
+
+def test_a_huge_stored_limit_is_shown_at_the_page_maximum(page):
+    # 10 TB/s is past what the page's spin box (and Qt's int) can hold
+    assert show(page, "10TB") == page._widgets["download_limit"].maximum()
+
+
+def test_an_old_bare_number_is_shown_as_the_limit_it_really_sets(page):
+    # The old page saved 500 for "500 KB/s"; OF-Scraper reads that as
+    # 500 bytes/s and raises it to 1024, about 1 KB/s. Show that, not 0
+    # (unlimited), so saving the page again doesn't silently remove the limit.
+    assert show(page, 500) == 1
diff --git a/OF-Scraper-3.14.7/test/unit/test_gui_pick_and_account_privacy.py b/OF-Scraper-3.14.7/test/unit/test_gui_pick_and_account_privacy.py
index 7a9c2fd..8dda5ac 100644
--- a/OF-Scraper-3.14.7/test/unit/test_gui_pick_and_account_privacy.py
+++ b/OF-Scraper-3.14.7/test/unit/test_gui_pick_and_account_privacy.py
@@ -53,9 +53,12 @@ def test_pick_survives_no_manager(monkeypatch, no_saved_creators):
 def cred_env(tmp_path, monkeypatch):
     import ofscraper.data.api.me as me
     import ofscraper.data.models.utils.retriver as retriver
+    import ofscraper.utils.auth.request as auth_request
     import ofscraper.utils.paths.common as paths
 
     monkeypatch.setattr(paths, "get_auth_file", lambda *a, **k: tmp_path / "auth.json")
+    # Test Credentials fetches the dynamic rule before /me
+    monkeypatch.setattr(auth_request, "read_request_auth", lambda: {})
     monkeypatch.setattr(
         me, "scrape_user",
         lambda *a, **k: {"isAuth": True, "name": "Real Name", "username": "realhandle"},
diff --git a/OF-Scraper-3.14.7/test/unit/test_profile_info_after_clear.py b/OF-Scraper-3.14.7/test/unit/test_profile_info_after_clear.py
new file mode 100644
index 0000000..bd3f00e
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_profile_info_after_clear.py
@@ -0,0 +1,76 @@
+"""get_my_info() must read the profile again when its data isn't there.
+
+Stock 3.14.7 recorded the active profile before it called scrape_user(),
+and returned the cached data whenever the profile matched, even None:
+- after a failed scrape_user() (for example a network error), the next
+  call returned None;
+- Test Credentials clears only profile_data.currentData, so the next call
+  returned None too.
+parse_user() then failed on None["name"], and the GUI's auth_errors turns
+"'NoneType' object is not subscriptable" into a false "Wrong user".
+"""
+
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import pytest
+
+pytestmark = pytest.mark.unit
+from types import SimpleNamespace
+
+import httpx
+
+import ofscraper.data.api.me as me
+import ofscraper.utils.me as me_util
+import ofscraper.utils.profiles.data as profile_data
+import ofscraper.utils.settings as settings
+
+USER = {"isAuth": True, "id": 1, "username": "u1", "name": "n1"}
+
+
+@pytest.fixture
+def profile(monkeypatch):
+    monkeypatch.setattr(profile_data, "currentProfile", None)
+    monkeypatch.setattr(profile_data, "currentData", None)
+    monkeypatch.setattr(profile_data, "get_active_profile", lambda: "main_profile")
+    monkeypatch.setattr(settings, "get_settings", lambda: SimpleNamespace(anon=False))
+    calls = []
+
+    def scrape_user():
+        calls.append(1)
+        return dict(USER)
+
+    monkeypatch.setattr(me, "scrape_user", scrape_user)
+    return calls
+
+
+def test_profile_cleared_by_test_credentials_is_read_again(profile):
+    me_util.parse_user()
+    # what Test Credentials does before it checks new auth (auth_dialog.py)
+    profile_data.currentData = None
+
+    assert me_util.parse_user() == ("n1", "u1")
+    assert len(profile) == 2
+
+
+def test_failed_scrape_is_retried_on_the_next_call(profile, monkeypatch):
+    def offline():
+        raise httpx.ConnectTimeout("timed out")
+
+    monkeypatch.setattr(me, "scrape_user", offline)
+    with pytest.raises(httpx.ConnectTimeout):
+        profile_data.get_my_info()
+
+    monkeypatch.setattr(me, "scrape_user", lambda: dict(USER))
+    assert profile_data.get_my_info() == USER
+
+
+def test_successful_scrape_is_reused(profile):
+    profile_data.get_my_info()
+    profile_data.get_my_info()
+    assert len(profile) == 1
diff --git a/OF-Scraper-3.14.7/test/unit/test_session_cancel.py b/OF-Scraper-3.14.7/test/unit/test_session_cancel.py
new file mode 100644
index 0000000..67ccc9a
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_session_cancel.py
@@ -0,0 +1,176 @@
+"""Cancelling requests_async must stop the request, not retry it.
+
+The retry loop only skipped KeyboardInterrupt and SystemExit, so tenacity's
+attempt swallowed asyncio.CancelledError and sent the request again. A
+cancel while an error response's body is read for the log must also end
+with that response closed (aiohttp's read() closes it).
+"""
+
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import pytest
+
+pytestmark = pytest.mark.unit
+import asyncio
+from types import SimpleNamespace
+
+from aiohttp import web
+
+import ofscraper.utils.settings as settings
+from ofscraper.managers.sessionmanager.sessionmanager import sessionManager
+
+
+@pytest.fixture(autouse=True)
+def plain_settings(monkeypatch):
+    monkeypatch.setattr(
+        settings,
+        "get_settings",
+        lambda: SimpleNamespace(ssl_verify="false", cached_disabled=True),
+    )
+
+
+QUIET = SimpleNamespace(
+    traceback_=lambda *a, **k: None,
+    debug=lambda *a, **k: None,
+    warning=lambda *a, **k: None,
+)
+
+
+async def serve(handler):
+    app = web.Application()
+    app.router.add_get("/f", handler)
+    runner = web.AppRunner(app)
+    await runner.setup()
+    site = web.TCPSite(runner, "127.0.0.1", 0)
+    await site.start()
+    port = site._server.sockets[0].getsockname()[1]
+    return runner, f"http://127.0.0.1:{port}/f"
+
+
+async def cancel_after(c, url, delay=0.3, wait=3):
+    """Start a request, cancel it, and report whether the cancel stopped it."""
+
+    async def request():
+        async with c.requests_async(url=url):
+            pass
+
+    task = asyncio.create_task(request())
+    await asyncio.sleep(delay)
+    task.cancel()
+    done, _ = await asyncio.wait({task}, timeout=wait)
+    stopped = task in done and task.cancelled()
+    # clean up a request that kept going
+    while not task.done():
+        task.cancel()
+        await asyncio.wait({task}, timeout=1)
+    return stopped
+
+
+def test_cancel_while_waiting_for_headers_stops_the_request():
+    calls = []
+    release = asyncio.Event()
+
+    async def silent(request):
+        calls.append(1)
+        await release.wait()
+        return web.Response(text="late")
+
+    async def run():
+        runner, url = await serve(silent)
+        try:
+            async with sessionManager(
+                sem_count=1, retries=3, wait_min=0, wait_max=0, log=QUIET
+            ) as c:
+                stopped = await cancel_after(c, url)
+                attempts = len(calls)
+                free = c._sem._value
+        finally:
+            release.set()
+            await runner.cleanup()
+        return stopped, attempts, free
+
+    stopped, attempts, free = asyncio.run(run())
+    assert stopped, f"the cancel was swallowed; {attempts} requests were sent"
+    assert attempts == 1
+    assert free == 1
+
+
+def test_cancel_while_reading_an_error_body_closes_the_response():
+    calls = []
+    transports = []
+    release = asyncio.Event()
+
+    async def stalled_error(request):
+        calls.append(1)
+        transports.append(request.transport)
+        resp = web.StreamResponse(status=500, headers={"Content-Length": "100000"})
+        await resp.prepare(request)
+        await resp.write(b"e" * 100)
+        await release.wait()
+        return resp
+
+    async def run():
+        runner, url = await serve(stalled_error)
+        try:
+            async with sessionManager(
+                sem_count=1, retries=3, wait_min=0, wait_max=0, log=QUIET
+            ) as c:
+                stopped = await cancel_after(c, url)
+                attempts = len(calls)
+                in_use = len(c._session.connector._acquired)
+                await asyncio.sleep(0.2)
+                open_ = sum(1 for t in transports if t and not t.is_closing())
+                free = c._sem._value
+        finally:
+            release.set()
+            await runner.cleanup()
+        return stopped, attempts, in_use, open_, free
+
+    stopped, attempts, in_use, open_, free = asyncio.run(run())
+    assert stopped, f"the cancel was swallowed; {attempts} requests were sent"
+    assert attempts == 1
+    assert in_use == 0
+    assert open_ == 0
+    assert free == 1
+
+
+def test_timeout_around_a_request_ends_it():
+    calls = []
+    release = asyncio.Event()
+
+    async def silent(request):
+        calls.append(1)
+        await release.wait()
+        return web.Response(text="late")
+
+    async def run():
+        runner, url = await serve(silent)
+        try:
+            async with sessionManager(
+                retries=3, wait_min=0, wait_max=0, log=QUIET
+            ) as c:
+
+                async def request():
+                    async with c.requests_async(url=url):
+                        pass
+
+                outer = asyncio.create_task(asyncio.wait_for(request(), 0.3))
+                done, _ = await asyncio.wait({outer}, timeout=3)
+                result = outer.exception() if outer in done else "still running"
+                while not outer.done():
+                    outer.cancel()
+                    await asyncio.wait({outer}, timeout=1)
+        finally:
+            release.set()
+            await runner.cleanup()
+        return result, len(calls)
+
+    result, attempts = asyncio.run(run())
+    assert isinstance(result, asyncio.TimeoutError), f"{result}; {attempts} requests"
+    assert attempts == 1
diff --git a/OF-Scraper-3.14.7/test/unit/test_session_read_timeout.py b/OF-Scraper-3.14.7/test/unit/test_session_read_timeout.py
new file mode 100644
index 0000000..45b971e
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_session_read_timeout.py
@@ -0,0 +1,248 @@
+"""Requests without their own read timeout must still time out.
+
+The session took its default read timeout from OF_READ_TIMEOUT, which was
+never defined, so it was None: a server that accepted the connection and
+then sent nothing hung the run forever, on both the async (aiohttp) and the
+sync (httpx) path.
+"""
+
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import pytest
+
+pytestmark = pytest.mark.unit
+import asyncio
+import socket
+import threading
+import time
+from types import SimpleNamespace
+
+import aiohttp
+import httpx
+
+import ofscraper.utils.of_env.of_env as of_env
+import ofscraper.utils.settings as settings
+from ofscraper.managers.sessionmanager.sessionmanager import sessionManager
+from ofscraper.utils.of_env.values.req.req import load_network_config
+
+
+@pytest.fixture(autouse=True)
+def plain_settings(monkeypatch):
+    monkeypatch.setattr(
+        settings,
+        "get_settings",
+        lambda: SimpleNamespace(ssl_verify="false", cached_disabled=True),
+    )
+
+
+def set_default(monkeypatch, value):
+    """Set the default through its environment variable, as a user would."""
+    monkeypatch.setenv("OFSC_READ_TIMEOUT", value)
+    network = load_network_config()
+    real = of_env.getattr
+
+    def getattr_(key, default=None):
+        if key in network:
+            return network[key]
+        return real(key, default)
+
+    monkeypatch.setattr(of_env, "getattr", getattr_)
+
+
+@pytest.fixture
+def one_second_default(monkeypatch):
+    set_default(monkeypatch, "1")
+
+
+@pytest.fixture
+def no_limit_default(monkeypatch):
+    set_default(monkeypatch, "0")
+
+
+class SilentServer:
+    """Accepts connections, reads the request and never answers."""
+
+    reply_after = None
+
+    def __init__(self):
+        self.sock = socket.socket()
+        self.sock.bind(("127.0.0.1", 0))
+        self.sock.listen(8)
+        self.sock.settimeout(0.2)
+        self.url = f"http://127.0.0.1:{self.sock.getsockname()[1]}/api"
+        self.held = []
+        self.stop = threading.Event()
+        self.thread = threading.Thread(target=self._accept, daemon=True)
+        self.thread.start()
+
+    def _accept(self):
+        while not self.stop.is_set():
+            try:
+                conn, _ = self.sock.accept()
+                self.held.append(conn)
+                if self.reply_after is not None:
+                    threading.Thread(
+                        target=self._reply, args=(conn,), daemon=True
+                    ).start()
+            except OSError:
+                pass
+
+    def _reply(self, conn):
+        try:
+            conn.settimeout(5)
+            conn.recv(65536)
+            time.sleep(self.reply_after)
+            conn.sendall(
+                b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"
+            )
+        except OSError:
+            pass
+
+    def close(self):
+        self.stop.set()
+        self.thread.join(2)
+        for conn in self.held:
+            conn.close()
+        self.sock.close()
+
+
+class SlowServer(SilentServer):
+    """Answers each request after 1.5 s."""
+
+    reply_after = 1.5
+
+
+QUIET = SimpleNamespace(
+    traceback_=lambda *a, **k: None,
+    debug=lambda *a, **k: None,
+    warning=lambda *a, **k: None,
+)
+
+
+def run_with_cap(fetch, cap=10, server_class=SilentServer):
+    """Run fetch in a thread; report a hang instead of hanging the test."""
+    server = server_class()
+    result = {}
+
+    def worker():
+        start = time.monotonic()
+        try:
+            fetch(server.url)
+            result["error"] = None
+        except Exception as E:
+            result["error"] = E
+        result["seconds"] = time.monotonic() - start
+
+    thread = threading.Thread(target=worker, daemon=True)
+    thread.start()
+    thread.join(cap)
+    hung = thread.is_alive()
+    attempts = len(server.held)
+    server.close()
+    thread.join(5)
+    return hung, result, attempts
+
+
+def test_default_read_timeout_is_set():
+    assert load_network_config().get("OF_READ_TIMEOUT", 0) > 0
+    assert (sessionManager()._read_timeout or 0) > 0
+
+
+def test_async_request_to_a_silent_server_times_out_and_retries(one_second_default):
+    def fetch(url):
+        async def go():
+            async with sessionManager(
+                retries=2, wait_min=0, wait_max=0, log=QUIET
+            ) as c:
+                async with c.requests_async(url=url):
+                    pass
+
+        asyncio.run(go())
+
+    hung, result, attempts = run_with_cap(fetch)
+    assert not hung, "the request was still waiting for a response after 10 s"
+    assert isinstance(result["error"], aiohttp.ServerTimeoutError), result
+    assert attempts == 2
+    assert result["seconds"] < 6
+
+
+def test_sync_request_to_a_silent_server_times_out_and_retries(one_second_default):
+    def fetch(url):
+        with sessionManager(retries=2, wait_min=0, wait_max=0, log=QUIET) as c:
+            with c.requests(url):
+                pass
+
+    hung, result, attempts = run_with_cap(fetch)
+    assert not hung, "the request was still waiting for a response after 10 s"
+    assert isinstance(result["error"], httpx.ReadTimeout), result
+    assert attempts == 2
+    assert result["seconds"] < 6
+
+
+# A read timeout of 0 means "no limit". aiohttp already reads 0 that way, but
+# httpx reads 0 as "fail at once", so the session turns any 0 into None.
+
+
+def test_zero_from_any_source_means_no_limit(monkeypatch):
+    # a 0 that reaches the session from of_env without the OFSC_ loader
+    real = of_env.getattr
+    monkeypatch.setattr(
+        of_env,
+        "getattr",
+        lambda k, d=None: 0 if k == "OF_READ_TIMEOUT" else real(k, d),
+    )
+    assert sessionManager()._read_timeout is None
+    # and a 0 passed to the session
+    monkeypatch.setattr(of_env, "getattr", real)
+    assert sessionManager(read_timeout=0)._read_timeout is None
+
+
+def test_zero_passed_to_the_session_means_no_limit_on_the_sync_path():
+    body = {}
+
+    def fetch(url):
+        with sessionManager(retries=1, read_timeout=0, log=QUIET) as c:
+            with c.requests(url) as r:
+                body["text"] = r.text_()
+
+    hung, result, attempts = run_with_cap(fetch, server_class=SlowServer)
+    assert not hung
+    assert result["error"] is None, result
+    assert body["text"] == "ok"
+
+
+def test_zero_means_no_limit_on_the_async_path(no_limit_default):
+    body = {}
+
+    def fetch(url):
+        async def go():
+            async with sessionManager(retries=1, log=QUIET) as c:
+                async with c.requests_async(url=url) as r:
+                    body["text"] = await r.text_()
+
+        asyncio.run(go())
+
+    hung, result, attempts = run_with_cap(fetch, server_class=SlowServer)
+    assert not hung
+    assert result["error"] is None, result
+    assert body["text"] == "ok"
+
+
+def test_zero_means_no_limit_on_the_sync_path(no_limit_default):
+    body = {}
+
+    def fetch(url):
+        with sessionManager(retries=1, log=QUIET) as c:
+            with c.requests(url) as r:
+                body["text"] = r.text_()
+
+    hung, result, attempts = run_with_cap(fetch, server_class=SlowServer)
+    assert not hung
+    assert result["error"] is None, result
+    assert body["text"] == "ok"
diff --git a/OF-Scraper-3.14.7/test/unit/test_session_request_retry_args.py b/OF-Scraper-3.14.7/test/unit/test_session_request_retry_args.py
new file mode 100644
index 0000000..a6828fd
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_session_request_retry_args.py
@@ -0,0 +1,166 @@
+"""retries, wait_min, wait_max (and log, on the sync path) passed to a
+request must win over the session's defaults.
+
+Both request methods read them with kwargs.get(...), but they're named
+parameters, so they never land in kwargs and the passed value was ignored.
+"""
+
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import pytest
+
+pytestmark = pytest.mark.unit
+import asyncio
+import threading
+import time
+from types import SimpleNamespace
+
+from aiohttp import web
+
+import ofscraper.utils.settings as settings
+from ofscraper.managers.sessionmanager.sessionmanager import sessionManager
+
+
+@pytest.fixture(autouse=True)
+def plain_settings(monkeypatch):
+    monkeypatch.setattr(
+        settings,
+        "get_settings",
+        lambda: SimpleNamespace(ssl_verify="false", cached_disabled=True),
+    )
+
+
+class Log:
+    def __init__(self):
+        self.lines = []
+
+    def debug(self, msg, *a, **k):
+        self.lines.append(msg)
+
+    def warning(self, msg, *a, **k):
+        self.lines.append(msg)
+
+    def traceback_(self, *a, **k):
+        pass
+
+
+def session(log=None):
+    # session defaults: 5 tries, no wait
+    return sessionManager(retries=5, wait_min=0, wait_max=0, log=log or Log())
+
+
+class FailingServer:
+    """Answers every request with a 500, on its own thread and loop."""
+
+    def __init__(self):
+        self.calls = 0
+        self.loop = asyncio.new_event_loop()
+        self.ready = threading.Event()
+        self.thread = threading.Thread(target=self._run, daemon=True)
+        self.thread.start()
+        self.ready.wait(5)
+
+    async def _handler(self, request):
+        self.calls += 1
+        return web.Response(status=500, text="try again")
+
+    def _run(self):
+        asyncio.set_event_loop(self.loop)
+        app = web.Application()
+        app.router.add_get("/f", self._handler)
+        self.runner = web.AppRunner(app)
+        self.loop.run_until_complete(self.runner.setup())
+        site = web.TCPSite(self.runner, "127.0.0.1", 0)
+        self.loop.run_until_complete(site.start())
+        self.url = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/f"
+        self.ready.set()
+        self.loop.run_forever()
+
+    def close(self):
+        asyncio.run_coroutine_threadsafe(self.runner.cleanup(), self.loop).result(5)
+        self.loop.call_soon_threadsafe(self.loop.stop)
+        self.thread.join(5)
+        self.loop.close()
+
+
+@pytest.fixture
+def server():
+    s = FailingServer()
+    yield s
+    s.close()
+
+
+def fetch_async(url, **kw):
+    async def go():
+        async with session() as c:
+            async with c.requests_async(url=url, **kw):
+                pass
+
+    start = time.monotonic()
+    with pytest.raises(Exception):
+        asyncio.run(go())
+    return time.monotonic() - start
+
+
+def fetch_sync(url, log=None, **kw):
+    start = time.monotonic()
+    with pytest.raises(Exception):
+        with session(log) as c:
+            with c.requests(url, **kw):
+                pass
+    # the session pauses 1 s on close
+    return time.monotonic() - start - 1
+
+
+def test_async_request_uses_the_retries_passed_in(server):
+    fetch_async(server.url, retries=2)
+    assert server.calls == 2
+
+
+def test_async_request_uses_the_waits_passed_in(server):
+    seconds = fetch_async(server.url, retries=2, wait_min=0.6, wait_max=0.6)
+    assert server.calls == 2
+    assert seconds >= 0.5
+
+
+def test_sync_request_uses_the_retries_passed_in(server):
+    fetch_sync(server.url, retries=2)
+    assert server.calls == 2
+
+
+def test_sync_request_uses_the_waits_passed_in(server):
+    seconds = fetch_sync(server.url, retries=2, wait_min=0.6, wait_max=0.6)
+    assert server.calls == 2
+    assert seconds >= 0.5
+
+
+def test_sync_request_logs_to_the_log_passed_in(server):
+    session_log, request_log = Log(), Log()
+    with pytest.raises(Exception):
+        with session(session_log) as c:
+            with c.requests(server.url, retries=2, log=request_log):
+                pass
+    assert any("attempt: 2" in line for line in request_log.lines)
+    assert not any("attempt: 2" in line for line in session_log.lines)
+
+
+def test_zero_wait_passed_in_is_kept(server):
+    # 0 is a real value, not "use the default"
+    async def go():
+        async with sessionManager(retries=5, wait_min=1, wait_max=1, log=Log()) as c:
+            async with c.requests_async(
+                url=server.url, retries=3, wait_min=0, wait_max=0
+            ):
+                pass
+
+    start = time.monotonic()
+    with pytest.raises(Exception):
+        asyncio.run(go())
+    assert server.calls == 3
+    assert time.monotonic() - start < 1.5
diff --git a/OF-Scraper-3.14.7/test/unit/test_session_stream_cleanup.py b/OF-Scraper-3.14.7/test/unit/test_session_stream_cleanup.py
new file mode 100644
index 0000000..89caee4
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_session_stream_cleanup.py
@@ -0,0 +1,161 @@
+"""requests_async must close a streamed response when the caller's code fails.
+
+requests_async yielded the response from inside tenacity's retry attempt. An
+error raised while the caller was reading it (e.g. a read timeout on a
+stalled CDN download) was thrown back into that attempt, which swallows every
+exception: the response was never closed, the semaphore was released a
+second time, and a new request was sent and yielded again. The caller got a
+RuntimeError instead of the timeout, and each failed download left
+connections open with unread data (datawhores/OF-Scraper#655).
+"""
+
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import pytest
+
+pytestmark = pytest.mark.unit
+import asyncio
+import gc
+from types import SimpleNamespace
+
+from aiohttp import web
+
+import ofscraper.utils.settings as settings
+from ofscraper.managers.sessionmanager.sessionmanager import sessionManager
+
+QUIET = SimpleNamespace(
+    traceback_=lambda *a, **k: None,
+    debug=lambda *a, **k: None,
+    warning=lambda *a, **k: None,
+)
+
+
+@pytest.fixture(autouse=True)
+def plain_settings(monkeypatch):
+    monkeypatch.setattr(
+        settings,
+        "get_settings",
+        lambda: SimpleNamespace(ssl_verify="false", cached_disabled=True),
+    )
+
+
+async def serve(handler):
+    app = web.Application()
+    app.router.add_get("/f", handler)
+    runner = web.AppRunner(app)
+    await runner.setup()
+    site = web.TCPSite(runner, "127.0.0.1", 0)
+    await site.start()
+    port = site._server.sockets[0].getsockname()[1]
+    return runner, f"http://127.0.0.1:{port}/f"
+
+
+def session():
+    return sessionManager(
+        sem_count=2, retries=3, wait_min=0, wait_max=0, read_timeout=0.5, log=QUIET
+    )
+
+
+def connected(transports):
+    return sum(1 for t in transports if t is not None and not t.is_closing())
+
+
+def test_stalled_stream_is_closed_and_not_requested_again():
+    transports = []
+    stop = asyncio.Event()
+
+    async def stalled(request):
+        transports.append(request.transport)
+        resp = web.StreamResponse(headers={"Content-Length": str(10 * 1024 * 1024)})
+        await resp.prepare(request)
+        await resp.write(b"x" * 65536)
+        await stop.wait()
+        return resp
+
+    async def run():
+        runner, url = await serve(stalled)
+        errors = []
+        try:
+            async with session() as c:
+                for _ in range(3):
+                    try:
+                        async with c.requests_async(url=url, total_timeout=None) as r:
+                            async for _ in r.iter_chunked(65536):
+                                pass
+                    except Exception as E:
+                        errors.append(E)
+                    gc.collect()
+                    await asyncio.sleep(0.2)
+                in_use = len(c._session.connector._acquired)
+                still_connected = connected(transports)
+                free = c._sem._value
+        finally:
+            stop.set()
+            await runner.cleanup()
+        return errors, in_use, still_connected, free
+
+    errors, in_use, still_connected, free = asyncio.run(run())
+    # the caller sees the real timeout, once per download, and no retry inside
+    assert len(errors) == 3
+    assert all(isinstance(E, asyncio.TimeoutError) for E in errors), errors
+    assert len(transports) == 3, f"{len(transports)} requests for 3 downloads"
+    # and nothing is left open
+    assert in_use == 0
+    assert still_connected == 0
+    assert free == 2
+
+
+def test_completed_stream_is_released():
+    async def ok(request):
+        return web.Response(body=b"y" * 200000)
+
+    async def run():
+        runner, url = await serve(ok)
+        try:
+            async with session() as c:
+                async with c.requests_async(url=url) as r:
+                    body = b"".join([x async for x in r.iter_chunked(65536)])
+                in_use = len(c._session.connector._acquired)
+                free = c._sem._value
+        finally:
+            await runner.cleanup()
+        return body, in_use, free
+
+    body, in_use, free = asyncio.run(run())
+    assert body == b"y" * 200000
+    assert in_use == 0
+    assert free == 2
+
+
+def test_failed_status_is_still_retried():
+    calls = []
+
+    async def flaky(request):
+        calls.append(1)
+        if len(calls) < 3:
+            return web.Response(status=500, text="try again")
+        return web.Response(text="done")
+
+    async def run():
+        runner, url = await serve(flaky)
+        try:
+            async with session() as c:
+                async with c.requests_async(url=url) as r:
+                    text = await r.text_()
+                in_use = len(c._session.connector._acquired)
+                free = c._sem._value
+        finally:
+            await runner.cleanup()
+        return text, in_use, free
+
+    text, in_use, free = asyncio.run(run())
+    assert text == "done"
+    assert len(calls) == 3
+    assert in_use == 0
+    assert free == 2
diff --git a/OF-Scraper-3.14.7/test/unit/test_session_sync_connect_timeout.py b/OF-Scraper-3.14.7/test/unit/test_session_sync_connect_timeout.py
new file mode 100644
index 0000000..3856c40
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_session_sync_connect_timeout.py
@@ -0,0 +1,98 @@
+"""The sync requests path must time out a TLS handshake that never completes.
+
+It passed connect=None to httpx, which disables the connect timeout, and the
+TLS handshake counts as connect time. Behind a VPN that dropped the
+handshake reply, fetching the dynamic rules hung forever at "getting new
+signature" (datawhores/OF-Scraper#652).
+"""
+
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import pytest
+
+pytestmark = pytest.mark.unit
+import socket
+import threading
+import time
+from types import SimpleNamespace
+
+import httpx
+
+import ofscraper.utils.settings as settings
+from ofscraper.managers.sessionmanager.sessionmanager import sessionManager
+
+
+@pytest.fixture(autouse=True)
+def plain_settings(monkeypatch):
+    monkeypatch.setattr(
+        settings,
+        "get_settings",
+        lambda: SimpleNamespace(ssl_verify="false", cached_disabled=True),
+    )
+
+
+class SilentTLSServer:
+    """Accepts connections and never answers the ClientHello."""
+
+    def __init__(self):
+        self.sock = socket.socket()
+        self.sock.bind(("127.0.0.1", 0))
+        self.sock.listen(8)
+        self.sock.settimeout(0.2)
+        self.port = self.sock.getsockname()[1]
+        self.held = []
+        self.stop = threading.Event()
+        self.thread = threading.Thread(target=self._accept, daemon=True)
+        self.thread.start()
+
+    def _accept(self):
+        while not self.stop.is_set():
+            try:
+                conn, _ = self.sock.accept()
+                self.held.append(conn)
+            except OSError:
+                pass
+
+    def close(self):
+        self.stop.set()
+        self.thread.join(2)
+        for conn in self.held:
+            conn.close()
+        self.sock.close()
+
+
+def test_stalled_handshake_times_out_with_the_session_connect_timeout():
+    server = SilentTLSServer()
+    quiet_log = SimpleNamespace(
+        traceback_=lambda *a, **k: None, debug=lambda *a, **k: None
+    )
+    result = {}
+
+    def fetch():
+        start = time.monotonic()
+        try:
+            with sessionManager(
+                connect_timeout=0.5, retries=1, wait_min=0, wait_max=0, log=quiet_log
+            ) as c:
+                with c.requests(f"https://127.0.0.1:{server.port}/rules.json"):
+                    result["error"] = None
+        except Exception as E:
+            result["error"] = E
+        result["seconds"] = time.monotonic() - start
+
+    worker = threading.Thread(target=fetch, daemon=True)
+    worker.start()
+    worker.join(10)
+    hung = worker.is_alive()
+    server.close()
+    worker.join(5)
+
+    assert not hung, "the request was still waiting on the handshake after 10 s"
+    assert isinstance(result["error"], httpx.ConnectTimeout), result
+    assert result["seconds"] < 5
```
