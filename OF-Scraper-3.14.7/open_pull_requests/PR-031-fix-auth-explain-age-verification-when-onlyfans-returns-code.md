# PR #31: fix(auth): explain age verification when OnlyFans returns code 117

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/31
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/auth-code-117` → `main`
- **Created:** 2026-11-06T12:26:41Z  ·  **Updated:** 2026-11-07T00:03:15Z
- **Draft:** False
- **Changes:** 3 files, +77 / -0

## Description

**What was broken:** When OnlyFans requires age verification (400, code 117), Test Credentials showed the generic failure text, which points at the wrong causes.

**What was fixed:** Code 117 gets a message explaining the age verification and the steps. `GUI_HELP.md` has a new section with the same steps.

Tested: `test_auth_errors.py`.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/gui/help/GUI_HELP.md`
- `OF-Scraper-3.14.7/ofscraper/gui/utils/auth_errors.py`
- `OF-Scraper-3.14.7/test/unit/test_auth_errors.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/gui/help/GUI_HELP.md b/OF-Scraper-3.14.7/ofscraper/gui/help/GUI_HELP.md
index 6ae1309..c24a64c 100644
--- a/OF-Scraper-3.14.7/ofscraper/gui/help/GUI_HELP.md
+++ b/OF-Scraper-3.14.7/ofscraper/gui/help/GUI_HELP.md
@@ -1589,6 +1589,14 @@ OnlyFans **Wrong user** (API error **code 301**) means the API does not accept t
 5. Do not keep retrying the same cookies after Wrong user — obtain a fresh set.
 6. If credentials test OK but models still fail, continue with **§4** (Dynamic Mode / SSL Verify).
 
+### Age verification (code 117)
+
+In some countries OnlyFans asks you to verify your age after you log in. Until that step is finished, OnlyFans rejects the cookies with **400 Bad Request, code 117**, and **Test Credentials** shows **Credentials Invalid**. Import Cookies and the System / App Browser login don't pick up the verified session, and changing Dynamic Mode or SSL Verify doesn't help.
+
+1. Log into OnlyFans in your browser on this computer and finish the age verification.
+2. Follow **§2** above to copy the auth by hand, from a request made **after** the verification.
+3. Click **Save**, then **Test Credentials** again.
+
 ### 4. Credentials look correct but models still will not load
 
 - Try changing **Dynamic Mode** under **Configuration → Advanced** (signing-rules source).
diff --git a/OF-Scraper-3.14.7/ofscraper/gui/utils/auth_errors.py b/OF-Scraper-3.14.7/ofscraper/gui/utils/auth_errors.py
index fe585eb..3c906e5 100644
--- a/OF-Scraper-3.14.7/ofscraper/gui/utils/auth_errors.py
+++ b/OF-Scraper-3.14.7/ofscraper/gui/utils/auth_errors.py
@@ -22,6 +22,25 @@ def wrong_user_help_message(*, detail: str = "") -> str:
     )
 
 
+def age_verification_help_message(*, detail: str = "") -> str:
+    """User-facing text for OnlyFans code 117: age verification not finished."""
+    return (
+        "OnlyFans has not finished verifying your age (code 117).\n\n"
+        "In some countries OnlyFans asks you to verify your age after you log in.\n"
+        "Cookies captured before that step is finished are rejected.\n\n"
+        "How to fix:\n"
+        "1. Log into OnlyFans in your browser on this computer and finish the\n"
+        "   age verification.\n"
+        "2. Copy sess + auth_id (+ auth_uid* if present) + User-Agent + x-bc\n"
+        "   by hand from the SAME Network request, after the verification\n"
+        "   (Help → Auth Issues → manual copy).\n"
+        "   Import Cookies and the System/App Browser login don't pick up the\n"
+        "   verified session.\n"
+        "3. Click Save, then Test Credentials again.\n"
+        f"{detail}"
+    )
+
+
 def extract_of_error(exc) -> tuple[int | None, str | None, str]:
     """Return (code, message, detail_suffix) from an HTTP-ish exception if possible."""
     of_code = None
@@ -73,6 +92,8 @@ def format_cred_test_failure(exc) -> str:
     of_code, of_message, detail = extract_of_error(exc)
     if is_wrong_user_failure(exc, of_code, of_message):
         return wrong_user_help_message(detail=detail)
+    if str(of_code) == "117":
+        return age_verification_help_message(detail=detail)
 
     msg = str(exc)
     if "401" in msg or "unauthorized" in msg.lower():
diff --git a/OF-Scraper-3.14.7/test/unit/test_auth_errors.py b/OF-Scraper-3.14.7/test/unit/test_auth_errors.py
new file mode 100644
index 0000000..d469f62
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_auth_errors.py
@@ -0,0 +1,48 @@
+from ofscraper.gui.utils.auth_errors import format_cred_test_failure
+
+
+class _Response:
+    def __init__(self, body):
+        self._body = body
+
+    def json(self):
+        return self._body
+
+
+class _HTTPError(Exception):
+    def __init__(self, message, body):
+        super().__init__(message)
+        self.response = _Response(body)
+
+
+def _bad_request(code, message=""):
+    return _HTTPError(
+        "Client error '400 Bad Request' for url "
+        "'https://onlyfans.com/api2/v2/subscriptions/count/all'",
+        {"error": {"code": code, "message": message}},
+    )
+
+
+def test_code_117_explains_age_verification():
+    text = format_cred_test_failure(_bad_request(117))
+    assert "verifying your age (code 117)" in text
+    assert "manual copy" in text
+    # the generic hints don't apply to this failure
+    assert "Dynamic Mode" not in text
+
+
+def test_code_117_as_text_is_recognised():
+    text = format_cred_test_failure(_bad_request("117"))
+    assert "verifying your age" in text
+
+
+def test_wrong_user_is_unchanged():
+    text = format_cred_test_failure(_bad_request(301, "Wrong user"))
+    assert "Wrong user" in text
+    assert "verifying your age" not in text
+
+
+def test_other_codes_keep_the_generic_message():
+    text = format_cred_test_failure(_bad_request(999))
+    assert text.startswith("Could not verify credentials against OnlyFans.")
+    assert "verifying your age" not in text
```
