import re
import ofscraper.utils.paths.common as paths
from typing import Any

# --- Default Patterns (Regex or Plain Text) ---
_DEFAULT_PATTERNS = {
    # Redacts API keys and session tokens (Fixed to stop at whitespace)
    r"&Policy=[^&\"'\s]+": "&Policy={hidden}",
    r"&Signature=[^&\"'\s]+": "&Signature={hidden}",
    r"&Key-Pair-Id=[^&\"'\s]+": "&Key-Pair-Id={hidden}",
    # Redacts common sensitive info
    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b": "{ip_address}",  # IP Addresses
    r"\"sess\":\"[^\"]+\"": '"sess":"{hidden}"',  # Session tokens
    # Auth values by name, whatever their value. Masking only the values from
    # auth.json misses others: OnlyFans can send a new session in a response's
    # set-cookie, and request headers are logged when a request fails.
    # Cookie form: sess=abc; auth_id=123
    r"\bsess=[^;\s'\",]+": "sess={sess}",
    r"\b(auth_id|auth_uid\w*)=[^;\s'\",]+": r"\1={hidden}",
    # Header or dict form: 'x-bc': 'abc', "sess": "abc"
    r"""(['"])sess\1(\s*:\s*)(['"])[^'"]+\3""": r"\1sess\1\2\3{sess}\3",
    r"""(['"])(x-bc|auth_id|auth_uid\w*|user-id)\1(\s*:\s*)(['"])[^'"]+\4""": r"\1\2\1\3\4{hidden}\4",
    # Plain header line: x-bc: abc
    r"\bx-bc(\s*[:=]\s*)[^\s'\",;]+": r"x-bc\1{hidden}",
}

# This dictionary will be populated at runtime by your add_sensitive_pattern function
_USER_ADDED_PATTERNS = {}


def add_sensitive_pattern(pattern: Any, replacement: Any = "{hidden}"):
    """
    Dynamically adds a new pattern. It intelligently handles strings,
    numbers, and compiled regex objects to prevent errors.
    """
    key = ""
    # If the pattern is a compiled regex object (re.Pattern)
    if isinstance(pattern, re.Pattern):
        # Use its .pattern attribute to get the original string
        key = pattern.pattern
    else:
        # For anything else (numbers, strings), use str() as a safe fallback
        key = str(pattern)

    _USER_ADDED_PATTERNS[key] = str(replacement)


def getSenstiveDict() -> dict:
    """
    Returns a combined dictionary of default, user-added, and dynamic patterns.
    """
    # Dicts keep insertion order, which is the order they're applied in:
    # built-in rules, then patterns added during the session (exact values
    # such as the session cookie or user id), then the home folder name last.
    # The home folder name is short and could otherwise rewrite part of a
    # secret so it no longer matches.
    combined_patterns = _DEFAULT_PATTERNS.copy()
    combined_patterns.update(_USER_ADDED_PATTERNS)

    # --- Add Dynamic Patterns ---
    # These are generated based on the current user's specific info.

    # 2. Redact profile/download directory paths
    profile_dir = paths.get_username()
    if profile_dir:
        # Escape the name for regex and replace it where it's a whole name, not
        # inside a longer word: a home folder called "dan" must not turn
        # "danger" into "{home_directory}ger". "_" doesn't count as part of a
        # word, so the name is still hidden in a file name like "dan_log.txt".
        combined_patterns.setdefault(
            rf"(?<![^\W_]){re.escape(str(profile_dir))}(?![^\W_])",
            "{home_directory}",
        )

    return combined_patterns
