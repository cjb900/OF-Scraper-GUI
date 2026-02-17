import logging
import html
import re
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QDesktopServices, QTextDocument
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QUrl

from ofscraper.gui.signals import app_signals
from ofscraper.gui.styles import c

log = logging.getLogger("shared")

DISCORD_HELP_URL = "https://discord.gg/wN7uxEVHRK"

_RE_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_RE_BOLD = re.compile(r"\*\*(.+?)\*\*")
_RE_CODE = re.compile(r"`([^`]+)`")


def _inline_to_html(text: str) -> str:
    """Convert a small subset of inline markdown to HTML safely."""
    if text is None:
        return ""
    t = html.escape(str(text), quote=False)
    # links first so link text can contain bold/code after escaping
    t = _RE_LINK.sub(r'<a href="\2">\1</a>', t)
    t = _RE_BOLD.sub(r"<b>\1</b>", t)
    t = _RE_CODE.sub(r"<code>\1</code>", t)
    return t


def _help_md_to_html(md: str) -> str:
    """Convert our help markdown into HTML with reliable anchors.

    Qt's setMarkdown/scrollToAnchor behavior can be inconsistent, especially with
    embedded HTML anchors. By rendering our own HTML we ensure:
    - TOC links are clickable
    - scrollToAnchor() works with <a id="..."></a>
    """
    lines = (md or "").splitlines()
    out = []
    ul_stack = []  # indent levels
    in_para = False

    def close_paragraph():
        nonlocal in_para
        if in_para:
            out.append("</p>")
            in_para = False

    def close_lists(to_level: int = 0):
        nonlocal ul_stack
        while len(ul_stack) > to_level:
            out.append("</ul>")
            ul_stack.pop()

    for raw in lines:
        line = raw.rstrip("\n")

        # Preserve explicit anchor tags from the file.
        if line.strip().startswith("<a ") and line.strip().endswith("</a>"):
            close_paragraph()
            close_lists(0)
            out.append(line.strip())
            continue

        # Horizontal rules
        if line.strip() == "---":
            close_paragraph()
            close_lists(0)
            out.append("<hr/>")
            continue

        # Headings
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            close_paragraph()
            close_lists(0)
            level = len(m.group(1))
            text = _inline_to_html(m.group(2).strip())
            # Keep headings within h2-h4 visually (h1 is huge)
            h_level = min(max(level + 1, 2), 4)
            out.append(f"<h{h_level}>{text}</h{h_level}>")
            continue

        # Blank line: end paragraphs/lists cleanly
        if not line.strip():
            close_paragraph()
            close_lists(0)
            continue

        # List items (supports indentation by 2-space steps)
        lm = re.match(r"^(\s*)-\s+(.*)$", line)
        if lm:
            close_paragraph()
            indent = len(lm.group(1).replace("\t", "  "))
            level = indent // 2
            # open/close lists to current level
            if len(ul_stack) < level + 1:
                while len(ul_stack) < level + 1:
                    out.append("<ul>")
                    ul_stack.append(level)
            elif len(ul_stack) > level + 1:
                close_lists(level + 1)
            out.append(f"<li>{_inline_to_html(lm.group(2).strip())}</li>")
            continue

        # Default: paragraph text
        close_lists(0)
        if not in_para:
            out.append("<p>")
            in_para = True
            out.append(_inline_to_html(line.strip()))
        else:
            out.append("<br/>" + _inline_to_html(line.strip()))

    close_paragraph()
    close_lists(0)

    body = "\n".join(out)
    return f"""
    <html>
      <head>
        <style>
          body {{ font-family: Segoe UI, Consolas, monospace; font-size: 13px; color: {c('text')}; }}
          a {{ color: {c('blue')}; text-decoration: none; }}
          a:hover {{ text-decoration: underline; }}
          h2,h3,h4 {{ color: {c('green')}; margin: 14px 0 6px 0; }}
          hr {{ border: 0; border-top: 1px solid {c('sep')}; margin: 14px 0; }}
          code {{ background: {c('mantle')}; color: {c('text')}; padding: 1px 4px; border-radius: 4px; }}
          ul {{ margin-top: 6px; margin-bottom: 6px; }}
        </style>
      </head>
      <body>
        {body}
      </body>
    </html>
    """


class HelpBrowser(QTextBrowser):
    """QTextBrowser that reliably detects link clicks.

    QTextBrowser's anchorClicked can be inconsistent with markdown-rendered links.
    This uses anchorAt() on mouse release to detect the href directly.
    """

    href_clicked = pyqtSignal(str)

    def mouseReleaseEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                href = self.anchorAt(event.pos())
                if href:
                    self.href_clicked.emit(str(href))
                    event.accept()
                    return
        except Exception:
            pass
        super().mouseReleaseEvent(event)


_FALLBACK_HELP_MD = """\
# OF-Scraper GUI Help / README

This page explains what each section of the GUI does and how to use it.

## Left navigation

- **Scraper**: Main workflow for downloading/liking content.
- **Authentication**: Enter your cookies/headers (stored in your profile `auth.json`).
- **Configuration**: Edit `config.json` settings (save location, formats, performance, etc.).
- **Profiles**: Manage profiles (each profile has separate auth + `.data`).
- **Merge DBs**: Merge `user_data.db` files into a single database.

## Scraper workflow (Scraper →)

### 1) Select Action
Choose what you want to do:

- **Download content from a user**: Scrape content and build the table.
- **Like / Unlike**: Perform like/unlike actions on supported areas.
- **Download + Like / Unlike**: Do both.

### 2) Select Content Areas & Filters

#### Content Areas
These are the sources to scan (depending on action):

- **Profile, Timeline, Pinned, Archived, Highlights, Stories, Messages, Purchased, Streams, Labels**

#### Additional Options
- **Scrape entire paid page (slower but more comprehensive)**: Tries harder to enumerate paid items (may be slower).
- **Scrape labels**: Pull content via labels when available.

#### Advanced Scrape Options
- **Allow duplicates (do NOT skip duplicates; treat reposts as new items)**: Disables duplicate-skipping logic.
- **Rescrape everything (ignore cache / scan from the beginning)**: Forces a full history scan.
  - **Delete model DB before scraping (resets downloaded/unlocked history)**: Deletes the model DB folder so the run starts “fresh”.
  - **Also delete existing downloaded files for selected models**: Removes downloaded files under your save location for that model.

#### Daemon Mode (Auto-Repeat Scraping)
- **Enable daemon mode**: Automatically re-runs scraping on an interval.
- **Interval**: Minutes between runs.
- Optional notification/sound toggles.

#### Filters (on this page)
This page contains an embedded version of the same filter panel used on the table page.

### 3) Select Models
Search and select creators to process.

Tips:
- Use the search box (supports comma-separated values).
- Use **Select All / Deselect All / Toggle** to bulk change.

### 4) Scraping / Table page

#### Toolbar buttons
- **Filters**: Show/hide the filter sidebar.
- **Reset**: Reset filters.
- **Apply Filters**: Apply the current filter state.
- **Start Scraping >>**: Begin scraping the selected areas/models.
- **New Scrape**: Return to the first step for a new run.
- **Stop Daemon**: Stops daemon mode if enabled.
- **Select All / Deselect All**: Controls the download cart selection.
- **>> Send Downloads**: Queues selected rows for downloading.

#### Table basics
- Click a cell in **Download Cart** to toggle adding/removing it.
- Right-click any cell to filter by that value.
- Click headers to sort.

#### Progress + logs
- The **overall progress bar** is shown in the footer at the bottom of the table page.
- The console area shows detailed logs and trace output.

#### “Unlocked” column meanings (important)

The **Unlocked** column is not a direct 1:1 match with “purchased”.

- **Locked**: Not viewable (paywalled).
- **Preview**: Viewable teaser/preview media for a priced item.
- **Included**: Viewable media inside a priced message **without purchasing** (e.g., teaser media that OnlyFans still marks as viewable even though the message is priced).
- **True**: Treated as fully unlocked/accessible (typically purchased / opened content).

## Filters panel (Table page)

- **Text Search**: Regex/substring search (toggle **Full string match**).
- **Media Type**: Audios / Images / Videos.
- **Response Type**: Pinned / Archived / Timeline / Stories / Highlights / Streams.
- **Status**
  - **Downloaded**: True / False / No (Paid)
  - **Unlocked**: True / False / Locked
- **Post Date Range**, **Duration (Length)**, **Price Range**, **ID Filters**, **Username**

## Merge DBs

1. Pick a **Source Folder** that contains one or more `user_data.db` files.
2. Pick a **Destination** folder for the merged output.
3. Click **Start Merge** (back up first).

## Common troubleshooting

- If a purge option deletes files/DB and you immediately start a download scrape, the scraper may recreate folders/databases right away.
- “Unlocked” values can include non-purchased viewable media depending on the source type (messages/PPV behavior differs from timeline posts).
"""


class HelpPage(QWidget):
    """In-app README / help page for the GUI."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._pending_anchor = None
        self._setup_ui()
        self._load_help_text()
        app_signals.theme_changed.connect(lambda _: self._load_help_text())

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QLabel("Help / README")
        header.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        header.setProperty("heading", True)
        layout.addWidget(header)

        subtitle = QLabel(
            "Quick guide to the OF-Scraper GUI: what each section does and how to use it."
        )
        subtitle.setProperty("subheading", True)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Actions row
        actions = QHBoxLayout()
        self.jump_combo = QComboBox()
        self.jump_combo.setMinimumWidth(260)
        self.jump_combo.addItem("Jump to…", "")
        self.jump_combo.addItem("Left navigation", "nav-left")
        self.jump_combo.addItem("Scraper workflow", "scraper-workflow")
        self.jump_combo.addItem("Select Content Areas & Filters", "sca-root")
        self.jump_combo.addItem("Select Models", "models-root")
        self.jump_combo.addItem("Configuration (config.json)", "config-root")
        self.jump_combo.addItem("Table / Scraping page", "table-root")
        self.jump_combo.addItem("Filters", "filters-root")
        self.jump_combo.addItem("Table columns", "table-columns")
        self.jump_combo.addItem("Merge DBs", "merge-dbs")
        self.jump_combo.addItem("Troubleshooting notes", "troubleshooting")
        self.jump_combo.currentIndexChanged.connect(self._on_jump_changed)
        actions.addWidget(self.jump_combo)
        actions.addStretch()

        self.additional_help_btn = QPushButton("Additional Help")
        self.additional_help_btn.clicked.connect(self._on_additional_help)
        actions.addWidget(self.additional_help_btn)

        self.reload_btn = QPushButton("Reload Help")
        self.reload_btn.clicked.connect(self._load_help_text)
        actions.addWidget(self.reload_btn)
        layout.addLayout(actions)

        self.viewer = HelpBrowser()
        # We'll handle all links ourselves for reliability.
        self.viewer.setOpenExternalLinks(False)
        self.viewer.setOpenLinks(False)
        # With HTML rendering, QTextBrowser's anchorClicked is reliable; keep the
        # mouse-based fallback too.
        try:
            self.viewer.anchorClicked.connect(
                lambda url: self._handle_href(url.toString())
            )
        except Exception:
            pass
        self.viewer.href_clicked.connect(self._handle_href)
        self.viewer.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        layout.addWidget(self.viewer, stretch=1)

    def _on_jump_changed(self, idx: int):
        try:
            anchor = self.jump_combo.currentData()
            if anchor:
                self.scroll_to_anchor(str(anchor))
                # reset back to placeholder
                self.jump_combo.blockSignals(True)
                self.jump_combo.setCurrentIndex(0)
                self.jump_combo.blockSignals(False)
        except Exception:
            pass

    def _handle_href(self, href: str):
        """Handle internal #anchors and external links."""
        try:
            href = (href or "").strip()
            if not href:
                return
            if href.startswith("#"):
                self.scroll_to_anchor(href[1:])
                return
            url = QUrl(href)
            if url.isValid():
                QDesktopServices.openUrl(url)
        except Exception:
            pass

    def _on_additional_help(self):
        msg = f"For additional help join our discord {DISCORD_HELP_URL}"
        reply = QMessageBox.question(
            self,
            "Additional Help",
            msg + "\n\nOpen Discord invite in your browser?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                QDesktopServices.openUrl(QUrl(DISCORD_HELP_URL))
            except Exception:
                pass

    def _help_md_path(self) -> Path:
        # ofscraper/gui/pages/help_page.py → ofscraper/gui/help/GUI_HELP.md
        return Path(__file__).resolve().parents[1] / "help" / "GUI_HELP.md"

    def scroll_to_anchor(self, anchor: str):
        """Scroll the viewer to an internal anchor (used by '?' help buttons)."""
        try:
            anchor = (anchor or "").strip().lstrip("#")
            if not anchor:
                return
            self._pending_anchor = anchor

            def _do_scroll():
                try:
                    if not self._pending_anchor:
                        return
                    # With HTML rendering, scrollToAnchor should be reliable.
                    self.viewer.scrollToAnchor(self._pending_anchor)
                except Exception:
                    pass

            # Defer so markdown→html render/layout is complete
            QTimer.singleShot(0, _do_scroll)
        except Exception:
            pass

    def _load_help_text(self):
        md = None
        p = self._help_md_path()
        try:
            if p.exists():
                md = p.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            log.debug(f"Failed reading help markdown: {e}")

        if not md:
            md = _FALLBACK_HELP_MD

        try:
            self.viewer.setHtml(_help_md_to_html(md))
        except Exception:
            self.viewer.setPlainText(md)

        # If we have a pending anchor request, scroll after loading.
        try:
            if self._pending_anchor:
                QTimer.singleShot(0, lambda: self.viewer.scrollToAnchor(self._pending_anchor))
        except Exception:
            pass

