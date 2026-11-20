"""Posts log lines to the configured Discord webhook.

Lines are collected and sent together instead of one message per line: a
message holds what was logged within FLUSH_SECONDS, a new one starts at each
creator ("Progress 3/15"), and long text is split on line breaks under
Discord's 2,000-character limit. Run summaries go in a code block so their
columns stay lined up, and a record logged with ``extra={"discord_embed":
{...}}`` (the run totals) is posted as an embed card instead of its text
block. Messages post as "OF-Scraper · OnlyFans" or "OF-Scraper · Fansly".

Creator avatars ("Avatar : https://...") are left out, and Discord makes no
link previews, unless ``discord_avatars`` is true in config.json.
"""

import asyncio
import logging
import queue
import re
import threading

import ofscraper.managers.sessionmanager.sessionmanager as sessionManager
import ofscraper.utils.config.data as data
import ofscraper.utils.of_env.of_env as of_env
import ofscraper.utils.system.system as system
from ofscraper.managers.sessionmanager.sleepers import sleepers

# Discord's limit is 2,000 characters; leave room for a code fence
MAX_MESSAGE = 1900
FLUSH_SECONDS = 2.0
# message flag: don't turn links into previews
SUPPRESS_EMBEDS = 1 << 2

AVATAR_LINE = re.compile(r"^\s*Avatar\s*:\s*\S*\s*$")
CREATOR_START = re.compile(r"^\s*Progress \d+/\d+\b")
TOTALS_TITLE = "📊 GLOBAL RUN TOTALS"
SUMMARY_MARKERS = ("--- Final Stats Summary", "--- Scrape Results ---", TOTALS_TITLE)
MENTIONS = ("@here", "@everyone")


def show_avatars() -> bool:
    try:
        return bool(data.get_discord_avatars())
    except Exception:
        return False


def webhook_name() -> str:
    try:
        from ofscraper.managers.stats import run_site_label

        return f"OF-Scraper · {run_site_label()}"
    except Exception:
        return "OF-Scraper"


def split_lines(text: str, limit: int = MAX_MESSAGE) -> list:
    """``text`` in pieces of at most ``limit`` characters, cut at line
    breaks; a single longer line is cut at spaces, or anywhere."""
    pieces, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            cut = line.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            if current:
                pieces.append(current)
                current = ""
            pieces.append(line[:cut])
            line = line[cut:].lstrip(" ")
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            pieces.append(current)
            current = line
        else:
            current = candidate
    if current.strip():
        pieces.append(current)
    return [p for p in pieces if p.strip()]


def without_avatars(text: str) -> str:
    return "\n".join(line for line in text.split("\n") if not AVATAR_LINE.match(line))


def is_summary(text: str) -> bool:
    return any(marker in text for marker in SUMMARY_MARKERS)


def take_mention(text: str):
    """(mention, rest) when the text starts with @here or @everyone."""
    stripped = text.lstrip("\n")
    first, _, rest = stripped.partition("\n")
    if first.strip() in MENTIONS:
        return first.strip(), rest
    return "", text


def cut_totals(text: str) -> str:
    """The text before the run totals block (and the ===== line above it)."""
    at = text.find(TOTALS_TITLE)
    if at == -1:
        return text
    head = text[:at].rstrip(" \n")
    if head.endswith("=" * 10):
        head = head[: head.rfind("\n")] if "\n" in head else ""
    return head.rstrip()


def code_blocks(text: str) -> list:
    return [f"```\n{piece}\n```" for piece in split_lines(text.strip("\n"), MAX_MESSAGE - 8)]


class DiscordHandler(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.sess = sessionManager.sessionManager(
            total_timeout=of_env.getattr("DISCORD_TOTAL_TIMEOUT"),
            retries=of_env.getattr("DISCORD_NUM_TRIES"),
            wait_min=of_env.getattr("DISCORD_MIN_WAIT"),
            wait_max=of_env.getattr("DISCORD_MAX_WAIT"),
            forbidden_sleeper=sleepers.discord_forbidden_session_sleeper,
            rate_limit_sleeper=sleepers.discord_rate_limit_session_sleeper,
        )
        self.sess._set_session(async_=False)

        self._baseurl = data.get_discord()
        self._url = self._baseurl
        self.chunk_size = MAX_MESSAGE

        self.queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

        self._tasks = []
        try:
            self.loop = asyncio.get_running_loop()
        except Exception:
            self.loop = system.new_event_loop()
            asyncio.set_event_loop(self.loop)

    # --- receiving ---------------------------------------------------------

    def emit(self, record):
        text = self.format(record)
        embed = getattr(record, "discord_embed", None)
        if (not text or not text.strip()) and not embed:
            return
        self.queue.put((text or "", embed))

    def _worker(self):
        pending = []
        while True:
            try:
                item = self.queue.get(timeout=FLUSH_SECONDS if pending else None)
            except queue.Empty:
                self._flush(pending)
                continue
            if item is None:
                self._flush(pending)
                self.queue.task_done()
                break
            try:
                text, embed = item
                if embed or is_summary(text):
                    self._flush(pending)
                    self._send_summary(text, embed)
                else:
                    if CREATOR_START.match(text) and pending:
                        self._flush(pending)
                    pending.append(text.strip("\n"))
                    if len("\n".join(pending)) >= MAX_MESSAGE:
                        self._flush(pending)
            except Exception as e:
                print(f"Error preparing a Discord message: {e}")
            finally:
                self.queue.task_done()

    def close(self) -> None:
        self.queue.put(None)
        self._thread.join()
        if of_env.getattr("DISCORD_ASYNC") and self._tasks:
            self.loop.run_until_complete(asyncio.gather(*self._tasks))
            self.loop.close()
        super().close()

    # --- sending ------------------------------------------------------------

    def _flush(self, pending):
        if not pending:
            return
        text = "\n".join(pending)
        pending.clear()
        avatars = show_avatars()
        if not avatars:
            text = without_avatars(text)
        for piece in split_lines(text):
            self._post({"content": piece}, previews=avatars)

    def _send_summary(self, text, embed=None):
        mention, text = take_mention(text)
        if embed:
            text = cut_totals(text)
        sent = False
        for i, block in enumerate(code_blocks(text) if text.strip() else []):
            content = f"{mention}\n{block}" if mention and i == 0 else block
            self._post({"content": content})
            sent = True
        if embed:
            payload = {"embeds": [embed]}
            if mention and not sent:
                payload["content"] = mention
            self._post(payload)
        elif mention and not sent:
            self._post({"content": mention})

    def _post(self, payload, previews=False):
        if not self._url:
            return
        payload = dict(payload)
        payload.setdefault("username", webhook_name())
        if not previews and "embeds" not in payload:
            payload["flags"] = SUPPRESS_EMBEDS
        try:
            with self.sess.requests(
                self._url,
                method="post",
                headers={"Content-type": "application/json"},
                json=payload,
            ) as response:
                if response.status_code not in {200, 204}:
                    print(f"Discord message not sent: status {response.status_code}")
        except Exception as e:
            print(f"Error sending a Discord message: {e}")

    # kept for callers of the old names
    def split_text_by_word_chunks(self, text):
        return split_lines(text, self.chunk_size)

    def _send_to_discord(self, log_message):
        self._flush([log_message])
