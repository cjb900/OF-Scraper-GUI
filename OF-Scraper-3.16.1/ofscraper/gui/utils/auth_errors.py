"""Shared user-facing auth failure messages (Test Credentials / model load)."""
from __future__ import annotations


def wrong_user_help_message(*, detail: str = "") -> str:
    """User-facing text for OnlyFans 301 Wrong user / sess↔auth_id mismatch."""
    return (
        "OnlyFans rejected the session (“Wrong user”, code 301).\n\n"
        "What this usually means:\n"
        "• sess and auth_id are not from the same logged-in browser session\n"
        "• the session was invalidated (including after an earlier Wrong user)\n"
        "• auth_uid is required for 2FA but missing, or was copied from a different login\n\n"
        "How to fix:\n"
        "1. Log into OnlyFans in your browser on this computer.\n"
        "2. Re-import cookies (Zen/Firefox Import, or System/App Browser login),\n"
        "   OR copy sess + auth_id (+ auth_uid* if present) + User-Agent + x-bc\n"
        "   from the SAME Network request (Help → Auth Issues → manual copy).\n"
        "3. Click Save, then Test Credentials again.\n"
        "4. If it still fails, try Configuration → Advanced → Dynamic Mode,\n"
        "   and see Help → Auth Issues.\n"
        f"{detail}"
    )


def extract_of_error(exc) -> tuple[int | None, str | None, str]:
    """Return (code, message, detail_suffix) from an HTTP-ish exception if possible."""
    of_code = None
    of_message = None
    detail = ""
    resp = getattr(exc, "response", None)
    if resp is None:
        return of_code, of_message, detail
    try:
        resp_json = resp.json()
        err_obj = resp_json.get("error", {}) if isinstance(resp_json, dict) else {}
        if isinstance(err_obj, dict):
            of_code = err_obj.get("code")
            of_message = err_obj.get("message", "")
            if of_message or of_code is not None:
                detail = f"\n\nOnlyFans Server Response: {of_message} (code {of_code})"
                return of_code, of_message, detail
    except Exception:
        pass
    try:
        resp_text = getattr(resp, "text", None) or ""
        if resp_text:
            detail = f"\n\nServer Response: {str(resp_text)[:200]}"
    except Exception:
        pass
    return of_code, of_message, detail


def is_wrong_user_failure(exc=None, of_code=None, of_message=None, text: str | None = None) -> bool:
    msg = str(exc or text or "").lower()
    if of_code == 301:
        return True
    if of_message and "wrong user" in str(of_message).lower():
        return True
    if "wrong user" in msg:
        return True
    # me.scrape_user() can raise TypeError when /users/me returns null/empty JSON
    if isinstance(exc, TypeError) and "not subscriptable" in msg:
        return True
    if "empty or invalid profile" in msg or "invalid profile response" in msg:
        return True
    if "not subscriptable" in msg and "nonetype" in msg:
        return True
    return False


def format_cred_test_failure(exc) -> str:
    """Turn credential-test exceptions into actionable GUI text."""
    of_code, of_message, detail = extract_of_error(exc)
    if is_wrong_user_failure(exc, of_code, of_message):
        return wrong_user_help_message(detail=detail)

    msg = str(exc)
    if "401" in msg or "unauthorized" in msg.lower():
        return (
            "Auth error — session may be expired or invalid.\n\n"
            "Re-import credentials from a logged-in browser, Save, then Test again.\n"
            "See Help → Auth Issues for Import / Login / manual copy steps."
            f"{detail}\n\nDetail: {msg}"
        )
    return (
        "Could not verify credentials against OnlyFans.\n\n"
        f"{msg}{detail}\n\n"
        "Check Authentication fields, then Help → Auth Issues "
        "(Wrong user / sess and auth_id mismatch, Dynamic Mode, SSL Verify)."
    )


def model_load_failure_dialog_text(detail=None) -> tuple[str, str | None]:
    """Main + optional detailed text for Unable to Load Models dialogs."""
    detail_s = str(detail).strip() if detail else ""
    if detail_s and is_wrong_user_failure(text=detail_s):
        return (
            "Unable to get list of models — OnlyFans rejected the session "
            "(“Wrong user”).\n\n"
            "Usually sess and auth_id are not from the same login, the session "
            "was invalidated, or auth_uid is needed for 2FA.\n\n"
            "Open Authentication → re-import or copy cookies from one Network "
            "request → Save → Test Credentials.\n"
            "Help / README → Auth Issues has the full steps.",
            detail_s,
        )
    main = (
        "Unable to get list of models.\n"
        "Please check your auth information.\n\n"
        "If your auth is correct and the issue persists, try "
        "Configuration → Advanced:\n"
        "• change Dynamic Mode, and/or\n"
        "• set SSL Verify to false "
        "(helps some TLS/cert proxy setups; less secure).\n\n"
        "For “Wrong user” / sess and auth_id mismatch, see Help → Auth Issues."
    )
    return main, (detail_s or None)
