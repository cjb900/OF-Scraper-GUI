#!/root/OF-Scraper/.venv/bin/python
import multiprocessing
import warnings

# ofscraper 3.12.9 uses invalid escape sequences (e.g. "\." in regex strings)
# that emit SyntaxWarning on Python 3.12+.  Suppress them before importing.
warnings.filterwarnings("ignore", category=SyntaxWarning)

import ofscraper.runner.open.load as load
import ofscraper.utils.system.system as system


def main():
    if system.get_parent():
        load.main()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
