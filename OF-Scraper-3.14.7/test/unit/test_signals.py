import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import os
import signal
import subprocess
import sys
import textwrap

import pytest

pytestmark = pytest.mark.unit

import ofscraper.utils.context.exit as exit_ctx

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="SIGTERM cannot be delivered in-process on Windows"
)


@posix_only
def test_sigterm_raises_keyboard_interrupt():
    old = signal.getsignal(signal.SIGTERM)
    try:
        exit_ctx.sigterm_as_keyboard_interrupt()
        with pytest.raises(KeyboardInterrupt):
            os.kill(os.getpid(), signal.SIGTERM)
            signal.pause()  # the handler raises before this returns
    finally:
        signal.signal(signal.SIGTERM, old)


@posix_only
def test_sigterm_interrupts_blocked_main_thread_and_exits():
    # Mirrors daemon_process: main thread blocked on the job queue, scheduler
    # thread blocked in jobqueue.join(). SIGTERM must unblock and exit promptly.
    script = textwrap.dedent(
        """
        import os, queue, signal, threading
        import ofscraper.utils.context.exit as exit_ctx

        exit_ctx.sigterm_as_keyboard_interrupt()
        jobs = queue.Queue()
        jobs.put(lambda: None)
        threading.Thread(target=jobs.join, daemon=True).start()
        threading.Timer(0.2, os.kill, (os.getpid(), signal.SIGTERM)).start()
        try:
            jobs.get()
            jobs.get()  # blocks until SIGTERM
        except KeyboardInterrupt:
            print("interrupted")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "interrupted"
