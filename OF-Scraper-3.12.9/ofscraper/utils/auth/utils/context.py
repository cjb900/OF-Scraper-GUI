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
from contextlib import contextmanager

from rich.console import Console

import ofscraper.prompts.prompts as prompts
import ofscraper.utils.auth.make as make
import ofscraper.utils.auth.utils.dict as auth_dict
import ofscraper.utils.paths.common as common_paths
import ofscraper.utils.args.accessors.read as read_args

console = Console()
log = logging.getLogger("shared")


def _is_gui_mode():
    try:
        return getattr(read_args.retriveArgs(), "gui", False)
    except Exception:
        return False


@contextmanager
def auth_context():
    try:
        yield
    except FileNotFoundError:
        # In GUI mode, create an empty auth.json so the while-True retry loop in
        # file.py can read it successfully on the next iteration.  Without this
        # the loop spins forever because the context manager just returns (= retry)
        # but auth.json never gets created.
        if _is_gui_mode():
            try:
                import ofscraper.utils.paths.common as _cp
                import ofscraper.utils.auth.utils.dict as _ad
                _auth_path = _cp.get_auth_file()
                _auth_path.parent.mkdir(parents=True, exist_ok=True)
                if not _auth_path.exists():
                    import json as _json
                    with open(_auth_path, "w") as _f:
                        _f.write(_json.dumps(_ad.get_empty(), indent=4))
                    log.info(f"GUI mode: created empty auth.json at {_auth_path}")
            except Exception as _ce:
                log.warning(f"GUI mode: could not create auth.json ({_ce})")
            return
        console.print("You don't seem to have an `auth.json` file")
        make.make_auth()
    except json.JSONDecodeError as e:
        if _is_gui_mode():
            log.warning(f"auth.json syntax error: {e} — GUI will prompt user")
            return
        while True:
            try:
                print("Your auth.json has a syntax error")
                print(f"{e}\n\n")
                auth_prompt = prompts.reset_auth_prompt()
                if auth_prompt == "manual":
                    authStr = auth_dict.get_auth_string()
                    with open(common_paths.get_auth_file(), "w") as f:
                        f.write(prompts.manual_auth_prompt(authStr))
                elif auth_prompt == "reset":
                    with open(common_paths.get_auth_file(), "w") as f:
                        f.write(json.dumps(auth_dict.get_empty()))
                auth_dict.get_auth_dict()
                break
            except Exception:
                continue
