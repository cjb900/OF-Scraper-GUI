"""The Developer panel's settings, kept in this site's gui_settings.json
under "devtools" (each site's window has its own server and port)."""

from __future__ import annotations

import secrets

KEY = "devtools"
HOST = "127.0.0.1"
# OnlyFans and Fansly run as separate processes, each with its own server
DEFAULT_PORTS = {"onlyfans": 8765, "fansly": 8766}

DEFAULTS = {
    "enabled": False,
    "port": None,  # the site's default port
    # off until turned on: a screenshot leaves the computer with what it shows
    "screenshots": False,
    # Like / Unlike act on the account: refused unless allowed
    "account_actions": False,
    "token": "",
}


def site() -> str:
    try:
        from ofscraper.gui import site_context

        return site_context.current_site()
    except Exception:
        return "onlyfans"


def default_port() -> int:
    return DEFAULT_PORTS.get(site(), 8765)


def new_token() -> str:
    return secrets.token_urlsafe(24)


def load() -> dict:
    """The settings, with defaults filled in. A missing token is made and
    saved, so the command shown to connect stays the same."""
    from ofscraper.gui.utils.gui_settings import load_gui_settings

    stored = load_gui_settings().get(KEY)
    values = {**DEFAULTS, **(stored if isinstance(stored, dict) else {})}
    try:
        values["port"] = int(values["port"]) if values["port"] else default_port()
    except (TypeError, ValueError):
        values["port"] = default_port()
    if not values["token"]:
        values["token"] = new_token()
        save(values)
    return values


def save(values: dict) -> bool:
    from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings

    data = load_gui_settings()
    data[KEY] = {k: values.get(k, DEFAULTS[k]) for k in DEFAULTS}
    return save_gui_settings(data, quiet=True)


def connect_command(values: dict) -> str:
    """The Claude Code command that adds this window's server."""
    name = f"ofscraper-gui-{site()}"
    url = f"http://{HOST}:{values['port']}/mcp"
    return (
        f'claude mcp add --transport http {name} {url} '
        f'--header "Authorization: Bearer {values["token"]}"'
    )
