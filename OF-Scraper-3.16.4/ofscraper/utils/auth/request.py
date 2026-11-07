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

import ofscraper.utils.auth.file as auth_file
import ofscraper.utils.cache.cache as cache
import ofscraper.utils.const as const
import ofscraper.utils.of_env.of_env as of_env
import ofscraper.utils.settings as settings
import ofscraper.managers.manager as manager

curr_auth = None
last_check = None


def invalidate_auth_cache():
    """Clear in-memory + disk signing-rule cache so the next request re-fetches rules."""
    global curr_auth, last_check
    curr_auth = None
    last_check = None
    try:
        cache.delete("api_onlyfans_sign")
    except Exception:
        pass


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
    auth = None
    # GUI: manual rules and the generic URL can also come from config.json
    # (advanced_options.dynamic_rules_manual / dynamic_rules_url), not only
    # from OFSC_DYNAMIC_RULE_MANUAL / OF_DYNAMIC_GENERIC_URL
    if dynamic in {"manual"} and _manual_rules_set():
        auth = get_request_auth_dynamic_rule_manual()
    elif dynamic in {"generic"} and _generic_url_set():
        auth = get_request_auth_generic()
    elif (dynamic) in {"datawhores"}:
        auth = get_request_auth_datawhores()
    elif (dynamic) in {"xagler"}:
        auth = get_request_auth_xagler()
    elif (dynamic) in {"rafa"}:
        auth = get_request_auth_rafa()
    elif (dynamic) in {"digitalcriminals"}:
        auth = get_request_auth_digitalcriminals()
    if auth is None:
        auth = get_request_auth_datawhores()
    cache.set("api_onlyfans_sign", auth, of_env.getattr("THIRTY_EXPIRY"))
    curr_auth = auth
    last_check = arrow.now()
    return auth


def _config_value(getter_name):
    try:
        import ofscraper.utils.config.data as config_data

        return getattr(config_data, getter_name)()
    except Exception:
        return None


def _manual_rules_set():
    return bool(
        of_env.getattr("DYNAMIC_RULE_MANUAL")
        or _config_value("get_dynamic_rules_manual")
    )


def _generic_url_set():
    return bool(
        of_env.getattr("DYNAMIC_GENERIC_URL")
        or _config_value("get_dynamic_rules_url")
    )


def get_request_auth_dynamic_rule_manual():
    content = of_env.getattr("DYNAMIC_RULE_MANUAL")
    if content:
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
    # GUI: no environment value, so use the rules pasted into the GUI
    # (advanced_options.dynamic_rules_manual in config.json)
    from ofscraper.utils.dynamic_rules_manual import load_manual_rules_dict

    content = load_manual_rules_dict(None, _config_value("get_dynamic_rules_manual"))
    if not content:
        raise ValueError(
            "advanced_options.dynamic_rules_manual in config.json is not a usable rule"
        )
    return request_auth_helper_picker(content)


def get_request_auth_generic():
    logging.getLogger("shared").debug("getting new signature with generic")
    from ofscraper.utils.dynamic_rules_url import resolve_dynamic_rules_url

    env_value = of_env.getattr("DYNAMIC_GENERIC_URL")
    config_value = None
    try:
        import ofscraper.utils.config.data as config_data

        config_value = config_data.get_dynamic_rules_url()
    except Exception:
        config_value = None
    url = resolve_dynamic_rules_url(env_value, config_value)
    if not url:
        raise ValueError("No valid generic dynamic-rules URL (env or config)")
    with manager.Manager.session.get_session(
        retries=of_env.getattr("GIT_NUM_TRIES"),
        wait_min=of_env.getattr("GIT_MIN_WAIT"),
        wait_max=of_env.getattr("GIT_MAX_WAIT"),
    ) as c:

        with c.requests(
            url,
        ) as r:
            content = r.json_()
            return request_auth_helper_picker(content)


def get_request_auth_deviint():
    logging.getLogger("shared").debug("getting new signature with deviint")

    with manager.Manager.session.get_session(
        retries=of_env.getattr("GIT_NUM_TRIES"),
        wait_min=of_env.getattr("GIT_MIN_WAIT"),
        wait_max=of_env.getattr("GIT_MAX_WAIT"),
    ) as c:

        with c.requests(
            of_env.getattr("DEVIINT_URL"),
        ) as r:
            content = r.json_()
            return request_auth_helper_picker(content)


def get_request_auth_datawhores():
    logging.getLogger("shared").debug("getting new signature with datawhores")

    with manager.Manager.session.get_session(
        retries=of_env.getattr("GIT_NUM_TRIES"),
        wait_min=of_env.getattr("GIT_MIN_WAIT"),
        wait_max=of_env.getattr("GIT_MAX_WAIT"),
    ) as c:

        with c.requests(
            of_env.getattr("DATAWHORES_URL"),
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


def get_request_auth_riley():
    logging.getLogger("shared").debug("getting new signature with riley")

    with manager.Manager.session.get_session(
        retries=of_env.getattr("GIT_NUM_TRIES"),
        wait_min=of_env.getattr("GIT_MIN_WAIT"),
        wait_max=of_env.getattr("GIT_MAX_WAIT"),
    ) as c:

        with c.requests(
            of_env.getattr("RILEY_URL"),
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


def check_rule(content):
    if not isinstance(content, dict):
        found = "null" if content is None else type(content).__name__
        problem = f"expected a JSON object, got {found}"
    else:
        keys = SUFFIX_RULE_KEYS if content.get("suffix") else RULE_KEYS
        missing = [key for key in keys if key not in content]
        if not missing:
            return
        problem = f"missing {', '.join(missing)}"
    raise UnusableDynamicRule(
        f"The dynamic rule ({settings.get_settings().dynamic_rules}) is unusable: "
        f"{problem}. Try another dynamic rule, or try again later."
    )


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
