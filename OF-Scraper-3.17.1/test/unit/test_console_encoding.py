import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

pytestmark = pytest.mark.unit



def test_unencodable_output_is_replaced_not_raised():
    import io

    from rich.console import Console

    from ofscraper.utils.console import replace_unencodable_output

    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    replace_unencodable_output([stream])
    Console(file=stream, force_terminal=False).print("Cherry \U0001F352 model")
    stream.flush()
    assert stream.buffer.getvalue().decode("cp1252").strip() == "Cherry ? model"


def test_utf8_output_is_left_alone():
    import io

    from ofscraper.utils.console import replace_unencodable_output

    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    replace_unencodable_output([stream])
    assert stream.errors == "strict"
