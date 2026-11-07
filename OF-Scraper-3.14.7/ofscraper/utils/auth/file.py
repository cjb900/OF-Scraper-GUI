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
import re

from rich.console import Console

import ofscraper.utils.auth.make as make
import ofscraper.utils.auth.schema as auth_schema
import ofscraper.utils.auth.utils.error as auth_error
import ofscraper.utils.auth.utils.dict as auth_dict
import ofscraper.utils.paths.common as common_paths
import ofscraper.utils.logs.utils.sensitive as sensitive
console = Console()


def read_auth():
    """
    Reads and validates the auth file, handling errors interactively.
    Returns the auth dictionary
    """
    while True:
        try:
            # Attempt to get the auth data
            old_auth = auth_dict.get_auth_dict()
            auth = auth_schema.auth_schema(old_auth)

            # Perform normal logic checks
            if auth_schema.auth_key_missing(old_auth):
                auth = write_auth(auth)
            if auth_schema.auth_key_null(auth):
                # In GUI mode skip interactive prompts; the GUI auth dialog handles it
                import ofscraper.utils.args.accessors.read as read_args
                if not getattr(read_args.retriveArgs(), "gui", False):
                    auth,_ = make.make_auth(auth)
            
            # If all checks pass, break the loop and return the auth data
            break

        except (FileNotFoundError, json.JSONDecodeError) as e:
            result = auth_error.handle_auth_errors(e)
            if result =="quit":
                logging.getLogger("shared").info("unable to read auth file")
                quit()
    hide_secrets(auth)
    return auth


MIN_SECRET_LENGTH = 8


def hide_secrets(auth):
    """Mask the session cookie wherever it appears in a log line.

    Request headers are logged when a request fails, and the cookie header
    holds ``sess=<value>``. Registering the value itself covers every form it
    is logged in (cookie header, dict repr, JSON).
    """
    if not isinstance(auth, dict):
        return
    # a real value is long; a stray short one (e.g. a placeholder) would mask
    # ordinary words in every log line
    for key, label in (("sess", "{sess}"), ("x-bc", "{x-bc}")):
        value = auth.get(key)
        if value and len(str(value)) >= MIN_SECRET_LENGTH:
            sensitive.add_sensitive_pattern(re.compile(re.escape(str(value))), label)


def edit_auth():
    """
    Opens the auth editing menu, handling errors interactively.
    Returns the new auth dictionary or a command string ('quit', 'main').
    """
    while True:
        try:
            auth_dict.get_auth_dict()           
            break
        except (FileNotFoundError, json.JSONDecodeError) as e:
            # Delegate error handling
            result = auth_error.handle_auth_errors(e,include_main_menu=True)
            if result in {"quit", "main"}:
                return result
    
    current_auth = auth_dict.get_auth_dict()
    new_auth,result = make.make_auth(current_auth, include_main_menu=True)
    
    # Check if the user quit from the edit menu itself
    if result in {"quit", "main"}:
        return result

    console.print("Your `auth.json` file has been edited.")
    return new_auth


def write_auth(auth):
    """Write auth.json with allowlisted keys only and restrictive file permissions."""
    import ofscraper.utils.auth.cookie_allowlist as cookie_allowlist

    if isinstance(auth, str):
        try:
            parsed = json.loads(auth)
        except json.JSONDecodeError:
            parsed = {}
    elif isinstance(auth, dict):
        parsed = auth
    else:
        parsed = {}

    cleaned = cookie_allowlist.sanitize_auth_dict(parsed)
    auth_path = common_paths.get_auth_file()
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(cleaned, indent=4)
    with open(auth_path, "w", encoding="utf-8") as f:
        f.write(text)
    cookie_allowlist.harden_auth_file_permissions(auth_path)
    return auth_dict.get_auth_dict(text)
