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

import base64
import hashlib
import json
import logging
import random
import time
from urllib.parse import urlparse

import arrow
import httpx

import ofscraper.utils.auth.file as auth_file
import ofscraper.utils.cache.cache as cache
import ofscraper.utils.const as const
import ofscraper.utils.of_env.of_env as of_env
import ofscraper.utils.settings as settings
import ofscraper.managers.manager as manager

curr_auth = None
last_check = None

# tried in order when the chosen source fails or gives an unusable rule:
# all three gave a rule OnlyFans accepted in a live check on 2026-11-19,
# listed from the most recently updated
FALLBACK_SOURCES = ["digitalcriminals", "rafa", "xagler"]


class DynamicRuleUnavailable(Exception):
    """No dynamic rule source gave a rule that can sign requests.

    This says nothing about the auth: the rule hosts couldn't be reached,
    had an error, or sent a rule that can't be used.
    """

    def __init__(self, failures):
        self.failures = list(failures)
        reasons = "; ".join(
            f"{source}: {failure_reason(e)}" for source, e in self.failures
        )
        super().__init__(
            "Couldn't get a usable dynamic rule to sign requests"
            + (f" ({reasons})" if reasons else "")
            + ". This isn't a problem with your auth. Check your connection or "
            "VPN, try another dynamic rule, or try again later."
        )


def failure_reason(e):
    """A short reason a source gave no rule, for messages."""
    if isinstance(e, UnusableDynamicRule):
        return str(e)
    host = "the rule host"
    if isinstance(e, httpx.HTTPError):
        try:
            host = e.request.url.host
        except RuntimeError:
            pass
    if isinstance(e, httpx.TimeoutException):
        return f"couldn't reach {host} (timed out)"
    if isinstance(e, httpx.TransportError):
        # the same check as the auth check's message (data/api/init.py)
        from ofscraper.data.api.init import _cert_error

        cert_error = _cert_error(e)
        if cert_error:
            return (
                f"couldn't verify the certificate of {host} "
                f"({cert_error.verify_message})"
            )
        return f"couldn't reach {host} (connection failed)"
    if isinstance(e, httpx.HTTPStatusError):
        return f"{host} returned {e.response.status_code}"
    if isinstance(e, json.JSONDecodeError):
        return "the reply isn't JSON"
    return str(e) or type(e).__name__


def _fetch_rule(source):
    """The checked rule from one source; raises if it gives none."""
    return {
        "manual": get_request_auth_dynamic_rule_manual,
        "generic": get_request_auth_generic,
        "xagler": get_request_auth_xagler,
        "rafa": get_request_auth_rafa,
        "digitalcriminals": get_request_auth_digitalcriminals,
    }[source]()


def read_request_auth():
    request_auth = {
        "static_param": "",
        "format": "",
        "checksum_indexes": [],
        "checksum_constant": "0",
    }

    # get_request_auth returns a checked rule or raises
    (*values,) = get_request_auth()

    request_auth.update(zip(request_auth.keys(), values))
    return request_auth


def get_request_auth():
    global curr_auth
    global last_check
    if not last_check:
        pass
    elif curr_auth and (
        arrow.now().float_timestamp - last_check.float_timestamp
    ) < of_env.getattr("THIRTY_EXPIRY"):
        return curr_auth
    dynamic = settings.get_settings().dynamic_rules
    dynamic = const.DYNAMIC_ALIASES.get(dynamic, dynamic)
    source = None
    # (source, error) for each source that gave no usable rule
    failures = []
    if _manual_rule_content() and dynamic in {"manual"}:
        source = "manual"
    elif _generic_rule_url() and dynamic in {"generic"}:
        source = "generic"
    elif (dynamic) in {"xagler", "rafa", "digitalcriminals"}:
        source = dynamic
    elif dynamic == "manual":
        failures.append((dynamic, ValueError("OFSC_DYNAMIC_RULE_MANUAL isn't set")))
    elif dynamic == "generic":
        failures.append((dynamic, ValueError("OF_DYNAMIC_GENERIC_URL isn't set")))
    elif dynamic:
        # e.g. a name OFSC_DYNAMIC_OPTIONS still lists: the switch to a
        # fallback is logged with this reason
        removed = const.REMOVED_DYNAMIC_RULES.get(str(dynamic).lower())
        failures.append(
            (
                dynamic,
                ValueError(
                    f"removed because {removed}"
                    if removed
                    else "not a known dynamic rule"
                ),
            )
        )
    # the chosen source first; the fallbacks only if it gives no usable rule
    sources = [source] if source else []
    sources += [name for name in FALLBACK_SOURCES if name != source]
    auth = None
    for name in sources:
        try:
            auth = _fetch_rule(name)
        except Exception as e:
            failures.append((name, e))
            continue
        if failures:
            logging.getLogger("shared").info(
                f"Using the {name} dynamic rule instead ("
                + "; ".join(f"{s}: {failure_reason(err)}" for s, err in failures)
                + ")"
            )
        break
    if auth is None:
        # not cached, so the next request tries again. The last error is
        # chained for the debug log's traceback
        raise DynamicRuleUnavailable(failures) from (
            failures[-1][1] if failures else None
        )
    cache.set("api_onlyfans_sign", auth, of_env.getattr("THIRTY_EXPIRY"))
    curr_auth = auth
    last_check = arrow.now()
    return auth


def _config_value(getter):
    """A GUI setting from config.json (advanced_options), or None."""
    try:
        import ofscraper.utils.config.data as config_data

        return getattr(config_data, getter)()
    except Exception:
        return None


def _manual_rule_content():
    """The manual rule: OFSC_DYNAMIC_RULE_MANUAL, else the rule pasted in the
    config (GUI: Dynamic Mode manual), else None."""
    content = of_env.getattr("DYNAMIC_RULE_MANUAL")
    if content:
        return content
    from ofscraper.utils.dynamic_rules_manual import load_manual_rules_dict

    return load_manual_rules_dict(None, _config_value("get_dynamic_rules_manual")) or None


def _generic_rule_url():
    """The generic rule's URL: OF_DYNAMIC_GENERIC_URL, else the config's
    (GUI: Dynamic Mode generic), else None."""
    from ofscraper.utils.dynamic_rules_url import resolve_dynamic_rules_url

    return resolve_dynamic_rules_url(
        of_env.getattr("DYNAMIC_GENERIC_URL"), _config_value("get_dynamic_rules_url")
    ) or None


def invalidate_auth_cache():
    """Clear in-memory + disk signing-rule cache so the next request re-fetches rules."""
    global curr_auth, last_check
    curr_auth = None
    last_check = None
    try:
        cache.set("api_onlyfans_sign", None)
    except Exception:
        pass


def get_request_auth_dynamic_rule_manual():
    content = _manual_rule_content()
    # OFSC_DYNAMIC_RULE_MANUAL arrives as text: the rule's JSON
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except json.JSONDecodeError as E:
            raise ValueError(
                f"OFSC_DYNAMIC_RULE_MANUAL is not valid JSON: {E}"
            ) from E
    if not isinstance(content, dict):
        raise ValueError(
            "OFSC_DYNAMIC_RULE_MANUAL must be a JSON object holding the rule"
        )
    return request_auth_helper_picker(content)


def get_request_auth_generic():
    logging.getLogger("shared").debug("getting new signature with generic")
    with manager.Manager.session.get_session(
        retries=of_env.getattr("GIT_NUM_TRIES"),
        wait_min=of_env.getattr("GIT_MIN_WAIT"),
        wait_max=of_env.getattr("GIT_MAX_WAIT"),
    ) as c:

        with c.requests(
            _generic_rule_url(),
        ) as r:
            content = r.json_()
            return request_auth_helper_picker(content)


def get_request_auth_xagler():
    logging.getLogger("shared").debug("getting new signature with xagler")

    with manager.Manager.session.get_session(
        retries=of_env.getattr("GIT_NUM_TRIES"),
        wait_min=of_env.getattr("GIT_MIN_WAIT"),
        wait_max=of_env.getattr("GIT_MAX_WAIT"),
    ) as c:

        with c.requests(
            of_env.getattr("XAGLER_URL"),
        ) as r:
            content = r.json_()
            return request_auth_helper_picker(content)


def get_request_auth_rafa():
    logging.getLogger("shared").debug("getting new signature with rafa")

    with manager.Manager.session.get_session(
        retries=of_env.getattr("GIT_NUM_TRIES"),
        wait_min=of_env.getattr("GIT_MIN_WAIT"),
        wait_max=of_env.getattr("GIT_MAX_WAIT"),
    ) as c:

        with c.requests(
            of_env.getattr("RAFA_URL"),
        ) as r:
            content = r.json_()
            return request_auth_helper_picker(content)


def get_request_auth_digitalcriminals():
    logging.getLogger("shared").debug("getting new signature with digitalcriminals")

    with manager.Manager.session.get_session(
        retries=of_env.getattr("GIT_NUM_TRIES"),
        wait_min=of_env.getattr("GIT_MIN_WAIT"),
        wait_max=of_env.getattr("GIT_MAX_WAIT"),
    ) as c:
        with c.requests(
            of_env.getattr("DIGITALCRIMINALS"),
        ) as r:
            content = r.json_()
            return request_auth_helper_picker(content)


class UnusableDynamicRule(Exception):
    """The dynamic rule's content can't be used to sign requests."""


RULE_KEYS = ["static_param", "format", "checksum_indexes", "checksum_constant"]
SUFFIX_RULE_KEYS = [
    "static_param",
    "prefix",
    "suffix",
    "checksum_indexes",
    "checksum_constant",
]
# The first field of the sign in rules that are complete but that OnlyFans no
# longer accepts, so a generic URL or manual rule still set to one is caught.
# 26974 is a rule from 2024 that OnlyFans rejects
OBSOLETE_RULE_PREFIXES = {"26974"}


def _rule_prefix(content):
    if content.get("suffix"):
        return str(content["prefix"])
    return str(content["format"]).split(":")[0]


def check_rule(content):
    if not isinstance(content, dict):
        found = "null" if content is None else type(content).__name__
        problem = f"expected a JSON object, got {found}"
    else:
        keys = SUFFIX_RULE_KEYS if content.get("suffix") else RULE_KEYS
        missing = [key for key in keys if key not in content]
        if missing:
            problem = f"missing {', '.join(missing)}"
        elif _rule_prefix(content) in OBSOLETE_RULE_PREFIXES:
            problem = "obsolete, OnlyFans no longer accepts it"
        else:
            return
    raise UnusableDynamicRule(f"unusable rule: {problem}")


def request_auth_helper_picker(content):
    check_rule(content)
    token = content.get("app_token") or content.get("app-token")
    if token:
        import os
        os.environ["APP_TOKEN"] = str(token)
    if content.get("suffix"):
        return request_auth_helper(content)
    else:
        return request_auth_helper_alt_format(content)


def request_auth_helper_alt_format(content):
    static_param = content["static_param"]
    fmt = content["format"]
    checksum_indexes = content["checksum_indexes"]
    checksum_constant = content["checksum_constant"]
    return (static_param, fmt, checksum_indexes, checksum_constant)


def request_auth_helper(content):
    static_param = content["static_param"]
    fmt = f"{content['prefix']}:{{}}:{{:x}}:{content['suffix']}"
    checksum_indexes = content["checksum_indexes"]
    checksum_constant = content["checksum_constant"]
    return (static_param, fmt, checksum_indexes, checksum_constant)


def make_headers():
    if settings.get_settings().anon:
        return make_anon_headers()
    else:
        return make_login_headers()


def make_anon_headers():
    return {
        "accept": "application/json, text/plain, */*",
        "app-token": of_env.getattr("APP_TOKEN"),
        "x-bc": generate_xbc(),
        "referer": "https://onlyfans.com",
        "user-id": "0",
        "user-agent": of_env.getattr("ANON_USERAGENT"),
    }


def make_login_headers():
    import re
    auth = auth_file.read_auth()
    user_agent = auth.get("user_agent") or of_env.getattr("ANON_USERAGENT")
    x_bc = auth.get("x-bc") or generate_xbc(user_agent)
    
    headers = {
        "accept": "application/json, text/plain, */*",
        "app-token": of_env.getattr("APP_TOKEN"),
        "user-id": auth.get("auth_id", ""),
        "x-bc": x_bc,
        "referer": "https://onlyfans.com",
        "user-agent": user_agent,
    }

    if "Chrome" in user_agent or "Chromium" in user_agent:
        chrome_version = "120"
        match = re.search(r"Chrome/(\d+)", user_agent)
        if match:
            chrome_version = match.group(1)
        
        platform_name = "Windows"
        if "Linux" in user_agent:
            platform_name = "Linux"
        elif "Macintosh" in user_agent or "Mac OS" in user_agent:
            platform_name = "macOS"

        headers.update({
            "sec-ch-ua": f'"Not_A Brand";v="8", "Chromium";v="{chrome_version}", "Google Chrome";v="{chrome_version}"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": f'"{platform_name}"',
            "accept-language": "en-US,en;q=0.9",
        })
    else:
        headers.update({
            "accept-language": "en-US,en;q=0.5",
        })

    return headers


def add_cookies():
    if settings.get_settings().anon:
        return None
    auth = auth_file.read_auth()
    # Match stock OF-Scraper: only sess / auth_id / auth_uid_.
    # Do NOT synthesize auth_uid_<id> from auth_id — that cookie is a real
    # 2FA token in the browser; forging it with auth_id can trigger HTTP 400.
    cookies = {
        "sess": auth.get("sess") or "",
        "auth_id": auth.get("auth_id") or "",
        "auth_uid_": (auth.get("auth_uid") or auth.get("auth_id") or ""),
    }
    return cookies


def get_cookies_str():
    auth = auth_file.read_auth()
    # Stock string omits auth_uid_; include auth_uid_ only (never auth_uid_<id>).
    parts = [
        f"auth_id={auth.get('auth_id') or ''}",
        f"sess={auth.get('sess') or ''}",
        f"auth_uid_={auth.get('auth_uid') or auth.get('auth_id') or ''}",
    ]
    return ";".join(parts) + ";"


def create_sign(link, headers):
    """
    credit: DC and hippothon
    """
    if settings.get_settings().anon:
        return create_anon_sign(link, headers)
    else:
        return create_login_sign(link, headers)


def create_anon_sign(link, headers):
    return create_login_sign(link, headers)


def create_login_sign(link, headers):
    content = read_request_auth()
    time2 = str(round(time.time() * 1000))

    path = urlparse(link).path
    query = urlparse(link).query
    path = path if not query else f"{path}?{query}"

    static_param = content["static_param"]

    a = [static_param, time2, path, headers["user-id"]]
    msg = "\n".join(a)

    message = msg.encode("utf-8")
    hash_object = hashlib.sha1(message, usedforsecurity=False)
    sha_1_sign = hash_object.hexdigest()
    sha_1_b = sha_1_sign.encode("ascii")

    checksum_indexes = content["checksum_indexes"]
    checksum_constant = content["checksum_constant"]
    checksum = sum(sha_1_b[i] for i in checksum_indexes) + checksum_constant

    final_sign = content["format"].format(sha_1_sign, abs(checksum))

    headers.update({"sign": final_sign, "time": time2})
    return headers


def generate_xbc(user_agent=None):
    """Generates a token based on current time, random numbers, and user agent.

    Returns:
      A string containing the generated token.
    """
    if not user_agent:
        try:
            auth = auth_file.read_auth()
            user_agent = auth.get("user_agent")
        except Exception:
            user_agent = None
    if not user_agent:
        user_agent = of_env.getattr("ANON_USERAGENT")

    parts = [
        int(time.time() * 1000),  # Milliseconds since epoch
        int(1e12 * random.random()),
        int(1e12 * random.random()),
        user_agent,
    ]
    msg = ".".join(
        [base64.b64encode(str(p).encode("utf-8")).decode("utf-8") for p in parts]
    )
    token = hashlib.sha1(msg.encode("utf-8"), usedforsecurity=False).hexdigest()
    return token


