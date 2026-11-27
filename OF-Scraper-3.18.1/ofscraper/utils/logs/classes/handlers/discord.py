"""Posts log lines to the configured Discord webhook.

Lines are collected and sent together instead of one message per line: a
message holds what was logged within FLUSH_SECONDS, a new one starts at each
creator ("Progress 3/15"), and long text is split on line breaks under
Discord's 2,000-character limit. Run summaries go in a code block so their
columns stay lined up, and a record logged with ``extra={"discord_embed":
{...}}`` (the run totals) is posted as an embed card instead of its text
block. Messages post as "OF-Scraper · OnlyFans" or "OF-Scraper · Fansly".

Creator avatars ("Avatar : https://...") are left out, and Discord makes no
link previews, unless ``discord_avatars`` is true in config.json. A signed
avatar link (Fansly) has its signature hidden in the text, and Fansly's CDN
won't serve Discord's image fetcher anyway, so the line is dropped: the
picture is downloaded here from the real link (logged with
``extra={"discord_avatar": url}``) and uploaded with the message.
"""

import asyncio
import json
import logging
import time

import httpx
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
MAX_EMBEDS = 10
# Discord's upload limit for a webhook without boosts is 10 MB
MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_TIMEOUT = 30
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


def avatar_image(text: str, url) -> str:
    """The link to show as an image embed for an avatar line, or "" when the
    line's own link works (it was not redacted)."""
    if not url or not AVATAR_LINE.match(text) or url in text:
        return ""
    return url


def image_headers(url) -> dict:
    """Browser-like headers for a CDN file (Fansly's CDN refuses requests
    without them); never the API token."""
    try:
        from ofscraper.sites.fansly import headers as fansly_headers

        if not fansly_headers.is_api_url(url):
            return fansly_headers.cdn_headers(fansly_headers.fansly_auth.read_auth())
    except Exception:
        pass
    return {}


def image_type(content: bytes):
    """(content type, extension) from the file's first bytes, or None. The
    CDN's own label can't be trusted: Fansly's avatars come back as a
    generic binary type, which is why Firefox wouldn't show them."""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp", "webp"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", "gif"
    return None


def fetch_image(url):
    """(content, content type, extension) of the picture at ``url``, or None."""
    try:
        r = httpx.get(
            url,
            headers=image_headers(url),
            timeout=IMAGE_TIMEOUT,
            follow_redirects=True,
        )
    except Exception as e:
        print(f"Could not download an avatar for Discord: {type(e).__name__}")
        return None
    found = image_type(r.content or b"") if r.status_code == 200 else None
    if not found:
        print(f"Could not download an avatar for Discord: status {r.status_code}")
        return None
    if len(r.content) > MAX_IMAGE_BYTES:
        return None
    return (r.content, *found)


def _safe(error) -> str:
    """An error as text without secrets: httpx's message names the link it
    failed on, which for Discord is the webhook with its token. print() goes
    to the console (and the Docker log) without the log formatters."""
    try:
        import ofscraper.utils.logs.utils.sensitive as sensitive

        text = str(error)
        for pattern, replacement in sensitive.getSenstiveDict().items():
            try:
                text = re.sub(pattern, replacement, text)
            except re.error:
                pass
        return text
    except Exception:
        return type(error).__name__


def post_with_files(url, payload, files):
    """Post ``payload`` with ``files`` [(name, content, type)] as multipart;
    the status code, or None when it could not be sent."""
    body = {"payload_json": json.dumps(payload)}
    parts = [(f"files[{i}]", (name, content, ctype)) for i, (name, content, ctype) in enumerate(files)]
    for _ in range(3):
        try:
            r = httpx.post(url, data=body, files=parts, timeout=IMAGE_TIMEOUT)
        except Exception as e:
            print(f"Error sending a Discord message: {_safe(e)}")
            return None
        if r.status_code != 429:
            return r.status_code
        try:
            wait = float(r.json().get("retry_after", 1))
        except Exception:
            wait = 1.0
        time.sleep(min(max(wait, 0.5), 30))
    return r.status_code


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
    # bold marks show as literal ** inside a code block
    text = text.replace("**", "")
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
        # a line whose text is sent with send_message() already (an alert)
        if getattr(record, "skip_discord", False):
            return
        text = self.format(record)
        embed = getattr(record, "discord_embed", None)
        if (not text or not text.strip()) and not embed:
            return
        image = avatar_image((text or "").strip(), getattr(record, "discord_avatar", None))
        self.queue.put((text or "", embed, image))

    def _worker(self):
        pending, images = [], []
        while True:
            try:
                item = self.queue.get(timeout=FLUSH_SECONDS if pending or images else None)
            except queue.Empty:
                self._flush(pending, images)
                continue
            if item is None:
                self._flush(pending, images)
                self.queue.task_done()
                break
            try:
                # a log line is (text, embed, picture); send_message() puts
                # plain text, as upstream's handler does
                text, embed, image = (item, None, None) if isinstance(item, str) else item
                if embed or is_summary(text):
                    self._flush(pending, images)
                    self._send_summary(text, embed)
                else:
                    if CREATOR_START.match(text) and (pending or images):
                        self._flush(pending, images)
                    if image:
                        # the line's link doesn't work; the picture goes as an embed
                        images.append(image)
                    else:
                        pending.append(text.strip("\n"))
                    if len("\n".join(pending)) >= MAX_MESSAGE:
                        self._flush(pending, images)
            except Exception as e:
                print(f"Error preparing a Discord message: {_safe(e)}")
            finally:
                self.queue.task_done()

    def send_message(self, text):
        """Send text as one message whatever this handler's level, redacted
        like a log line (the run summary at --discord SUMMARY)."""
        record = logging.makeLogRecord({"msg": text, "levelno": logging.CRITICAL, "levelname": "CRITICAL"})
        message = self.format(record)
        if message and message.strip():
            self.queue.put(message)

    def close(self) -> None:
        self.queue.put(None)
        self._thread.join()
        if of_env.getattr("DISCORD_ASYNC") and self._tasks:
            self.loop.run_until_complete(asyncio.gather(*self._tasks))
            self.loop.close()
        super().close()

    # --- sending ------------------------------------------------------------

    def _flush(self, pending, images=None):
        images = images if images is not None else []
        if not pending and not images:
            return
        text = "\n".join(pending)
        pending.clear()
        found = list(dict.fromkeys(images))[:MAX_EMBEDS]
        images.clear()
        avatars = show_avatars()
        if not avatars:
            text = without_avatars(text)
            found = []
        files = []
        for url in found:
            image = fetch_image(url)
            if image:
                content, ctype, ext = image
                files.append((f"avatar{len(files)}.{ext}", content, ctype))
        pieces = split_lines(text)
        for i, piece in enumerate(pieces):
            if files and i == len(pieces) - 1:
                self._post_files({"content": piece}, files)
            else:
                self._post({"content": piece}, previews=avatars)
        if files and not pieces:
            self._post_files({}, files)

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

    def _post_files(self, payload, files):
        """``payload`` with the pictures uploaded as attachments, which every
        Discord client shows inline. An image embed pointing at the
        attachment (attachment://) showed as an empty box in the desktop and
        web clients (Firefox-based browsers), only the phone app drew it."""
        if not self._url:
            return
        payload = dict(payload)
        payload.setdefault("username", webhook_name())
        payload["attachments"] = [{"id": i, "filename": name} for i, (name, _, _) in enumerate(files)]
        status = post_with_files(self._url, payload, files)
        if status is not None and status not in {200, 204}:
            print(f"Discord message not sent: status {status}")
            if payload.get("content"):
                # still send the text
                self._post({"content": payload["content"]})

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
            print(f"Error sending a Discord message: {_safe(e)}")

    # kept for callers of the old names
    def split_text_by_word_chunks(self, text):
        return split_lines(text, self.chunk_size)

    def _send_to_discord(self, log_message):
        self._flush([log_message])
