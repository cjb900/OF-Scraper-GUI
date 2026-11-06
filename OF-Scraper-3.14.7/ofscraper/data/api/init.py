r"""

 _______  _______         _______  _______  _______  _______  _______  _______  _______
(  ___  )(  ____ \       (  ____ \(  ____ \(  ____ )(  ___  )(  ____ )(  ____ \(  ____ )
| (   ) || (    \/       | (    \/| (    \/| (    )|| (   ) || (    )|| (    \/| (    )|
| |   | || (__     _____ | (_____ | |      | (____)|| (___) || (____)|| (__    | (____)|
| |   | ||  __)   (_____)(_____  )| |      |     __)|  ___  ||  _____)|  __)   |     __)
| |   | || (                   ) || |      | (\ (   | (   ) || (      | (      | (\ (
| (___) || )             /\____) || (____/\| ) \ \__| )   ( || )      | (____/\| ) \ \__
(_______)|/              \_______)(_______/|/   \__/|/     \||/       (_______/|/   \__/

"""

import json
import logging
import traceback

import aiohttp
import httpx

import ofscraper.utils.auth.request as auth_requests
import ofscraper.utils.console as console
import ofscraper.utils.settings as settings
from . import me

log = logging.getLogger("shared")


def print_sign_status():
    status = getstatus()
    if status == "UP":
        console.get_shared_console().print("Status - [bold green]🟢 UP[/bold green]")
    else:
        console.get_shared_console().print("Status - [bold red]🔴 DOWN[/bold red]")


def _host(e) -> str:
    try:
        if isinstance(e, aiohttp.ClientResponseError):
            return e.request_info.url.host
        if isinstance(e, aiohttp.ClientConnectorError):
            return e.host
        return e.request.url.host
    except (AttributeError, RuntimeError):
        return "the server"


def unavailable_message(e: Exception) -> str | None:
    """
    Returns a message for a failure that says nothing about the auth
    (network errors, server errors, a reply that isn't JSON, no usable
    dynamic rule), else None.
    """
    if isinstance(e, auth_requests.DynamicRuleUnavailable):
        return str(e)
    if isinstance(e, (httpx.TransportError, aiohttp.ClientConnectionError)):
        timed_out = isinstance(
            e, (httpx.TimeoutException, aiohttp.ServerTimeoutError)
        )
        reason = "timed out" if timed_out else "connection failed"
        return f"Couldn't reach {_host(e)} ({reason}). Check your connection or VPN."
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
    elif isinstance(e, aiohttp.ClientResponseError):
        status = e.status
    else:
        status = None
    if status == 429:
        return f"{_host(e)} is rate limiting requests. Try again later."
    if status is not None and status >= 500:
        return (
            f"{_host(e)} returned {status}: the server had an error. "
            "Try again later."
        )
    if isinstance(e, json.JSONDecodeError):
        # the parse error doesn't say which request it came from
        return (
            "Got a reply that isn't JSON from OnlyFans. It may be a captive "
            "portal or a VPN block page, or the server may be having problems. "
            "Check your connection or VPN."
        )
    return None


def auth_status():
    """
    Returns (status, message). status is UP, DOWN (the auth was rejected) or
    UNAVAILABLE (the auth couldn't be checked; message says why).
    """
    if settings.get_settings().anon:
        return "UP", None
    try:
        # fetch the dynamic rule once, with its own retries. Otherwise each
        # retry of /me fetches it again from every rule host
        auth_requests.read_request_auth()
        me.scrape_user()
        return "UP", None
    except Exception as e:
        log.traceback_(e)
        log.traceback_(traceback.format_exc())
        message = unavailable_message(e)
        if message:
            log.error(message)
            return "UNAVAILABLE", message
        return "DOWN", None


def getstatus():
    return auth_status()[0]
