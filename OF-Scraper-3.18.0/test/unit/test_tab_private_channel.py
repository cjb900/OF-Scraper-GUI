"""Programs a tab starts can't read or close the tab window's channel."""

import subprocess
import sys
import textwrap

TAB = textwrap.dedent('''
    import subprocess, sys
    from ofscraper.gui import site_context
    channel = site_context.private_channel()
    # e.g. the DRM key tool: started with the defaults, it inherits stdin
    seen = subprocess.run(
        [sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"],
        capture_output=True, text=True, timeout=20,
    ).stdout.strip()
    print("program saw", seen)
    print("tab got", repr(channel.readline()))
''')


def _run(code, data):
    return subprocess.run(
        [sys.executable, "-c", code], input=data, capture_output=True, text=True, timeout=60,
    )


def test_a_started_program_gets_empty_input_and_the_tab_keeps_the_channel():
    out = _run(TAB, "quit\n")
    assert out.returncode == 0, out.stderr
    assert "program saw ''" in out.stdout
    assert "tab got 'quit\\n'" in out.stdout


def test_without_it_the_program_would_take_the_quit():
    # the problem this fixes: the started program reads the tab's "quit"
    code = TAB.replace("channel = site_context.private_channel()", "channel = sys.stdin")
    out = _run(code, "quit\n")
    assert "program saw 'quit\\n'" in out.stdout
    assert "tab got ''" in out.stdout


def test_no_stdin_means_no_channel(monkeypatch):
    from ofscraper.gui import site_context

    monkeypatch.setattr(sys, "stdin", None)
    assert site_context.private_channel() is None
