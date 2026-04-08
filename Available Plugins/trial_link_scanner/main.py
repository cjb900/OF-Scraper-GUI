plugin_enabled = 1  # set to 0 to prevent this plugin from loading at all

"""
Trial Link Scanner Plugin for OF-Scraper GUI
=============================================
Scans direct message text for OnlyFans trial links during scraping.

Settings (edit below or in settings.json):
  POST_MODE     "link"      — send only the trial URL to Discord
                "full"      — send the full message text containing the link
  POST_TIMING   "immediate" — send a Discord message for each link as it is found
                "summary"   — collect all links and send one summary when the scrape ends
  DISCORD_ENABLED  True/False  — send matches to your configured Discord webhook
  ENABLED       True/False  — set to False to disable this plugin entirely
"""

import html
import json
import re
from datetime import datetime
from pathlib import Path

# ── Default settings ────────────────────────────────────────────────────────
_DEFAULTS = {
    "ENABLED": False,
    "POST_MODE": "link",          # "link" | "full"
    "POST_TIMING": "immediate",   # "immediate" | "summary"
    "DISCORD_ENABLED": True,
}

# ── Trial link regex ─────────────────────────────────────────────────────────
TRIAL_LINK_RE = re.compile(
    r"https://onlyfans\.com/[^/\s\"'<>]+/trial/[A-Za-z0-9_-]+"
)

from ofscraper.plugins.base import BasePlugin


class TrialLinkScannerPlugin(BasePlugin):
    """Scans scraped message text for OnlyFans trial/free-trial links."""

    def __init__(self, metadata, plugin_dir):
        super().__init__(metadata, plugin_dir)
        self._settings = dict(_DEFAULTS)
        self._load_settings()
        self._pending: list[dict] = []   # collected links for summary mode
        self._log_file = None            # opened on first write
        self._seen_links: set[str] = set()  # dedup within a scrape session

    # ── Settings ─────────────────────────────────────────────────────────────

    def _load_settings(self):
        settings_path = Path(self.plugin_dir) / "settings.json"
        if settings_path.exists():
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._settings.update(saved)
            except Exception as e:
                self.log.warning(f"[TrialLinkScanner] Could not load settings.json: {e}")

    @property
    def enabled(self):
        return bool(self._settings.get("ENABLED", False))

    @property
    def post_mode(self):
        return self._settings.get("POST_MODE", "link")

    @property
    def post_timing(self):
        return self._settings.get("POST_TIMING", "immediate")

    @property
    def discord_enabled(self):
        return bool(self._settings.get("DISCORD_ENABLED", True))

    # ── Plugin lifecycle ──────────────────────────────────────────────────────

    def on_load(self):
        self.log.info(
            f"[TrialLinkScanner] Loaded. enabled={self.enabled} "
            f"mode={self.post_mode} timing={self.post_timing} discord={self.discord_enabled}"
        )

    def on_ui_setup(self, main_window):
        """Add a settings/log viewer page to the sidebar."""
        try:
            from .gui import TrialLinkScannerPage
            from ofscraper.gui.widgets.styled_button import NavButton

            page = TrialLinkScannerPage(self, main_window)
            main_window._add_page("trial_link_scanner", page)

            btn = NavButton("Trial Links")
            main_window._nav_group.addButton(btn)
            main_window._nav_buttons["trial_link_scanner"] = btn

            nav_layout = main_window._nav_frame.layout()
            # Insert before the stretch spacer (above theme/verbose buttons)
            from PyQt6.QtCore import Qt as _Qt
            stretch_idx = -1
            for i in range(nav_layout.count()):
                item = nav_layout.itemAt(i)
                if item and item.spacerItem() is not None:
                    if item.expandingDirections() & _Qt.Orientation.Vertical:
                        stretch_idx = i
                        break
            if stretch_idx >= 0:
                nav_layout.insertWidget(stretch_idx, btn)
            else:
                theme_idx = nav_layout.indexOf(main_window._theme_btn)
                if theme_idx >= 0:
                    nav_layout.insertWidget(theme_idx, btn)
                else:
                    nav_layout.addWidget(btn)

            btn.clicked.connect(lambda checked: main_window._navigate("trial_link_scanner"))
            self.log.info("[TrialLinkScanner] Settings page attached to sidebar.")
        except Exception as e:
            self.log.error(f"[TrialLinkScanner] Failed to attach GUI: {e}")

    def on_scrape_start(self, config, models):
        if self.enabled:
            self._pending.clear()
            self._seen_links.clear()
            self.log.debug("[TrialLinkScanner] New scrape started — state cleared.")
        return models

    def on_posts_collected(self, posts, model_username):
        """Called for every batch of messages added to the collection."""
        if not self.enabled:
            return
        self.log.debug(
            f"[TrialLinkScanner] on_posts_collected: {len(posts)} posts for {model_username!r}"
        )
        for post in posts:
            text = self._get_text(post)
            if not text:
                continue
            for match in TRIAL_LINK_RE.finditer(text):
                link = match.group(0)
                dedup_key = f"{model_username}:{link}"
                if dedup_key in self._seen_links:
                    continue
                self._seen_links.add(dedup_key)
                entry = {
                    "model": model_username,
                    "link": link,
                    "text": text,
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "post_date": self._get_post_date(post),
                    "media_urls": self._get_media_urls(post),
                }
                self._on_link_found(entry)

    def on_scrape_complete(self, stats):
        if not self.enabled:
            return
        if self.post_timing == "summary" and self._pending:
            self._send_summary()
        self._pending.clear()
        self._seen_links.clear()

    def on_unload(self):
        if self._log_file:
            try:
                self._log_file.close()
            except Exception:
                pass

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _strip_html(text: str) -> str:
        """Remove HTML tags and decode entities from a string."""
        cleaned = re.sub(r"<[^>]+>", "", text)
        return html.unescape(cleaned).strip()

    @staticmethod
    def _get_post_date(post) -> str:
        """Return the message's original creation date as a readable string."""
        raw = getattr(post, "_post", None)
        created_at = None
        if isinstance(raw, dict):
            created_at = raw.get("createdAt") or raw.get("postedAt") or raw.get("changedAt")
        if not created_at:
            try:
                created_at = getattr(post, "date", None) or getattr(post, "created_at", None)
            except Exception:
                pass
        if not created_at:
            return ""
        # Handle ISO string, Unix int/float
        try:
            if isinstance(created_at, (int, float)):
                return datetime.fromtimestamp(created_at).strftime("%Y-%m-%d %H:%M")
            if isinstance(created_at, str):
                # Strip trailing Z / timezone for fromisoformat compat
                clean = created_at.rstrip("Z").split("+")[0].split(".")[0]
                return datetime.fromisoformat(clean).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(created_at)[:16]
        return ""

    @staticmethod
    def _get_media_urls(post, max_images: int = 4) -> list:
        """Extract image/gif CDN URLs from a message's media list.

        OF media URLs are nested under files.thumb.url (thumbnail) or files.full.url.
        These are CloudFront signed URLs that are IP-restricted to the local machine,
        so they must be downloaded locally before uploading to Discord.
        """
        urls = []
        raw = getattr(post, "_post", None)
        if not isinstance(raw, dict):
            return urls
        for item in raw.get("media") or []:
            if not isinstance(item, dict):
                continue
            if (item.get("type") or "").lower() not in ("photo", "gif"):
                continue
            files = item.get("files")
            if not isinstance(files, dict):
                continue
            # Prefer thumb (300×300) — small and fast; fall back to full
            for key in ("thumb", "full"):
                file_obj = files.get(key)
                if isinstance(file_obj, dict):
                    url = file_obj.get("url")
                    if url and isinstance(url, str) and url.startswith("http"):
                        urls.append(url)
                        break
            if len(urls) >= max_images:
                break
        return urls

    @staticmethod
    def _get_text(post) -> str:
        """Return the raw HTML text from the message.

        We deliberately avoid db_sanitized_text — that method strips HTML tags
        and leaves only the truncated display URL (e.g. https://onlyfans.com/user/…),
        which hides the full trial URL that lives inside the <a href="..."> attribute.
        The raw 'text' property returns the original HTML which our regex can search.
        """
        # Prefer the raw _post dict to bypass any property-level processing
        raw = getattr(post, "_post", None)
        if isinstance(raw, dict):
            text = raw.get("text")
            if text:
                return text
        # Fallback: the .text property (same value in most versions)
        try:
            text = post.text
            if text:
                return text
        except Exception:
            pass
        return ""

    def _on_link_found(self, entry: dict):
        self._write_log(entry)
        self.log.info(
            f"[TrialLinkScanner] Trial link found — model={entry['model']} link={entry['link']}"
        )
        if self.post_timing == "immediate":
            self._send_discord(entry)
        else:
            self._pending.append(entry)

    # ── Logging ───────────────────────────────────────────────────────────────

    def _get_log_file(self):
        """Open (or reuse) the daily log file inside the plugin's logs/ folder."""
        if self._log_file is None:
            logs_dir = Path(self.plugin_dir) / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now().strftime("%Y-%m-%d")
            log_path = logs_dir / f"trial_links_{date_str}.log"
            self._log_file = open(log_path, "a", encoding="utf-8")
        return self._log_file

    def _write_log(self, entry: dict):
        try:
            f = self._get_log_file()
            line = (
                f"[{entry['timestamp']}] model={entry['model']} "
                f"link={entry['link']}\n"
            )
            if self.post_mode == "full":
                clean_text = self._strip_html(entry["text"])
                indented = "\n".join("    " + l for l in clean_text.splitlines())
                line += indented + "\n"
            line += "\n"
            f.write(line)
            f.flush()
        except Exception as e:
            self.log.warning(f"[TrialLinkScanner] Failed to write log: {e}")

    # ── Discord ───────────────────────────────────────────────────────────────

    def _get_webhook_url(self) -> str | None:
        try:
            from ofscraper.utils.config.data import get_discord
            url = get_discord()
            return url if url and url.startswith("http") else None
        except Exception:
            return None

    def _send_discord(self, entry: dict):
        if not self.discord_enabled:
            return
        webhook_url = self._get_webhook_url()
        if not webhook_url:
            self._write_discord_error("No Discord webhook URL found in config — skipping.")
            return

        date_str = entry.get("post_date", "")
        date_part = f" · {date_str}" if date_str else ""

        if self.post_mode == "link":
            content = (
                f"**Trial link found** — `{entry['model']}`{date_part}\n"
                f"{entry['link']}"
            )
        else:
            clean_text = self._strip_html(entry["text"])
            text_preview = clean_text[:1800] if len(clean_text) > 1800 else clean_text
            content = (
                f"**Trial link found** — `{entry['model']}`{date_part}\n"
                f"{entry['link']}\n\n"
                f"**Message text:**\n```\n{text_preview}\n```"
            )

        # Build embeds for each image (Discord limit: 10 per message)
        embeds = [{"image": {"url": url}} for url in entry.get("media_urls") or []]
        self._post_to_discord(webhook_url, content, embeds=embeds)

    def _send_summary(self):
        if not self.discord_enabled or not self._pending:
            return
        webhook_url = self._get_webhook_url()
        if not webhook_url:
            self._write_discord_error("No Discord webhook URL found in config — skipping summary.")
            return

        # Send a header, then reuse _send_discord for each entry so images are included
        header = f"**Trial links found this session — {len(self._pending)} total**"
        self._post_to_discord(webhook_url, header)
        for entry in self._pending:
            self._send_discord(entry)

    def _write_discord_error(self, message: str):
        """Write a Discord error/diagnostic message to a persistent file."""
        try:
            logs_dir = Path(self.plugin_dir) / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            err_path = logs_dir / "discord_errors.log"
            ts = datetime.now().isoformat(timespec="seconds")
            with open(err_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {message}\n")
        except Exception:
            pass

    def _post_to_discord(self, webhook_url: str, content: str, embeds: list = None):
        """Post content to a Discord webhook.

        OF CDN image URLs are IP-restricted (CloudFront signed), so Discord's servers
        can't fetch them directly.  We download each image locally first, then upload
        them as multipart file attachments so Discord can display them inline.
        """
        try:
            import requests

            image_urls = [
                e["image"]["url"]
                for e in (embeds or [])
                if isinstance(e.get("image"), dict) and e["image"].get("url")
            ]

            # Download images while we're on the authorized IP
            downloaded = []   # list of (filename, bytes, content-type)
            for i, url in enumerate(image_urls[:4]):
                try:
                    r = requests.get(url, timeout=15)
                    if r.status_code == 200:
                        ct = r.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
                        ext = {"image/jpeg": "jpg", "image/png": "png",
                               "image/gif": "gif", "image/webp": "webp"}.get(ct, "jpg")
                        downloaded.append((f"image_{i}.{ext}", r.content, ct))
                    else:
                        self._write_discord_error(f"Image download HTTP {r.status_code}: {url[:80]}")
                except Exception as e:
                    self._write_discord_error(f"Image download failed: {e}: {url[:80]}")

            payload = {"content": content}

            if downloaded:
                # Multipart upload: files + payload_json
                files = {}
                attachments = []
                for idx, (fname, data, ct) in enumerate(downloaded):
                    files[f"files[{idx}]"] = (fname, data, ct)
                    attachments.append({"id": idx, "filename": fname})
                payload["attachments"] = attachments
                files["payload_json"] = (None, json.dumps(payload), "application/json")
                resp = requests.post(webhook_url, files=files, timeout=30)
            else:
                resp = requests.post(webhook_url, json=payload, timeout=10)

            if resp.status_code not in (200, 204):
                self._write_discord_error(
                    f"Discord returned HTTP {resp.status_code}: {resp.text[:300]}"
                )
        except Exception as e:
            self._write_discord_error(
                f"Unexpected error: {type(e).__name__}: {e}"
            )


# ── Plugin entry point ────────────────────────────────────────────────────────
# The plugin manager instantiates the module-level `Plugin` class.
Plugin = TrialLinkScannerPlugin
