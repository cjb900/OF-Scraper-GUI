# OF-Scraper GUI Patch

A self-contained Python script that patches an installed (non-binary) copy of [OF-Scraper](https://github.com/datawhores/OF-Scraper) to add a full **PyQt6 GUI** accessible via the `--gui` flag.

**Supported versions:** `3.12.9`, `3.14.3`, `3.14.5`, and `3.14.7`

> **Python version requirement**
> Python **3.11.x** or **3.12.x** is required. Python 3.13+ and versions below 3.11 are **not supported** and may cause issues with OF-Scraper or this patch.
> Recommended: [Python 3.11.6](https://www.python.org/downloads/release/python-3116/)

## Table of Contents

- [Supported platforms and install methods](#supported-platforms-and-install-methods)
  - [Platform notes](#platform-notes)
  - [Python version](#python-version)
- [Usage](#usage)
- [After patching](#after-patching)
- [Pages](#pages)
  - [Scraper — Select Action](#scraper--select-action)
  - [Select Content Areas & Filters](#select-content-areas--filters)
  - [Select Models](#select-models)
  - [Scraping page](#scraping-page)
  - [Confirm scrape (pre-start review)](#confirm-scrape-pre-start-review-3147)
  - [Check Mode](#check-mode-3143-3145-and-3147)
  - [Authentication](#authentication)
  - [Configuration](#configuration)
  - [DRM Key Creation](#drm-key-creation)
  - [Profile Manager](#profile-manager)
  - [Merge Databases](#merge-databases)
  - [Help / README](#help--readme)
- [GUI features](#gui-features)
  - [Application icon](#application-icon)
  - [Theme](#theme)
  - [About & text size](#about--text-size-3147)
  - [Verbose Log](#verbose-log)
  - [Privacy / demo mode](#privacy--demo-mode-3147)
  - [Context-sensitive help](#context-sensitive-help)
  - [Startup dependency check](#startup-dependency-check)
  - [Auth failure handling](#auth-failure-handling)
  - [Scraper workflow](#scraper-workflow)
  - [Safer cancel & confirms](#safer-cancel--confirms-3147)
  - [Status strip & health chips](#status-strip--health-chips-3147)
  - [Daemon mode](#daemon-mode-auto-repeat-scraping)
  - [Table page](#table-page)
  - [Check mode](#check-mode-3143-3145-and-3147)
  - [Progress bar](#progress-bar)
  - [CLI auto-start](#cli-auto-start)
  - [Crash diagnostics](#crash-diagnostics-3147)
  - [Scrape individual posts by URL or Post ID](#scrape-individual-posts-by-url-or-post-id-3145-and-3147)
  - [Discord webhook integration](#discord-webhook-integration)
  - [User Lists](#user-lists-3145-and-3147)
  - [Login in Browser](#login-in-browser-3147)
  - [Download integrity & security](#download-integrity--security-3147)
- [Plugin system](#plugin-system-all-versions)
  - [Plugins page](#plugins-page-3147)
  - [JoyCaption Tagger](#joycaption-tagger-joycaption_tagger-all-versions)
  - [LLM Assistant](#llm-assistant-llm_assistant-all-versions)
  - [Live Stream Monitor](#live-stream-monitor-live_stream_monitor-all-versions)
  - [Trial Link Scanner](#trial-link-scanner-trial_link_scanner-all-versions)
- [Docker](#docker)
  - [Running the GUI in Docker](#running-the-gui-in-docker)
  - [Auto-starting a scrape on container startup](#auto-starting-a-scrape-on-container-startup)
  - [Selecting the patch version at build time](#selecting-the-patch-version-at-build-time)
  - [Volumes, CDM keys, and crash logs](#volumes-cdm-keys-and-crash-logs)
- [Supported versions](#supported-versions)
- [How it detects your installation](#how-it-detects-your-installation)
  - [Broken installation detection](#broken-installation-detection)
- [If OF-Scraper is not detected](#if-of-scraper-is-not-detected)
- [OF-Scraper Tools](#of-scraper-tools)
- [Notes](#notes)
- [Disclaimer](#disclaimer)

## Supported platforms and install methods

Check this **before** installing or patching. Unsupported or untested platforms may fail in ways that are hard to diagnose.

| Platform | pip | pipx | uv |
|----------|:---:|:----:|:--:|
| Windows  | ✅  | ✅   | ✅ |
| Linux (Debian-based) | ❌  | ✅   | ✅ |
| Mac OS   | ❌ | ❌  | ❌ |
| Docker   | ✅ | — | — |
* ❌ not tested

### Platform notes

- **Windows**: Tested on **Windows 11** but should work on Windows 10 and other versions
- **Linux**: Only **Debian-based** distributions are supported (Ubuntu, Debian, Linux Mint, KDE Neon, Pop!_OS, etc.). Other distributions (Arch, Fedora, etc.) have not been tested and may require additional setup
- **Mac**: Mac OS has not been tested with this GUI patch
- **Docker**: Runs on any host that supports Docker. The container uses Ubuntu 24.04 with Xvfb and noVNC — no display required on the host. See [Docker](#docker)

### Python version

- **Supported**: Python **3.11.x** and **3.12.x**
- **Recommended**: Python **3.11.6** ([download here](https://www.python.org/downloads/release/python-3116/))
- Python versions below 3.11 or 3.13+ are **not supported** and may cause issues with OF-Scraper or this patch
- The patch script will warn you if an unsupported Python version is detected

## Usage

```bash
# Basic usage — auto-detect and patch (replace version number as needed)
python patch_ofscraper_3.14.7_gui.py

# Skip confirmation prompt
python patch_ofscraper_3.14.7_gui.py -y

# Dry run — see what would happen without making changes
python patch_ofscraper_3.14.7_gui.py --dry-run

# Specify install path manually
python patch_ofscraper_3.14.7_gui.py --target /path/to/site-packages/ofscraper

# Skip PyQt6 installation (if already installed)
python patch_ofscraper_3.14.7_gui.py --skip-pyqt6

# Restore original files from backup
python patch_ofscraper_3.14.7_gui.py --restore /path/to/backup
```

The same flags apply to `patch_ofscraper_3.14.5_gui.py`, `patch_ofscraper_3.14.3_gui.py`, and `patch_ofscraper_3.12.9_gui.py`.

## After patching

Launch the GUI with:

```bash
ofscraper --gui
```

The patch script will also offer to launch the GUI for you immediately after a successful patch.

> **Note:** If you run the patch script from inside a source directory (e.g. `OF-Scraper-3.14.7/`), use `python -m ofscraper --gui` from a different directory (e.g. your home directory) to ensure the installed version is used rather than the local source files.

---

## Pages

A visual walkthrough of each page in the GUI.

---

### Scraper — Select Action

<img src="https://github.com/user-attachments/assets/e7c590a6-3b05-4e93-9d8c-f35eb673aa46" width="600" alt="Main Window — Select Action">
<img src="https://github.com/user-attachments/assets/98ef9690-5594-4ff8-b5e0-222e7fe53525" width="600" alt="Main Window — User List">


The starting point of every scrape. Choose what you want OF-Scraper to do:

- **Download** — download media files from your subscribed creators
  - **User Lists** *(3.14.5 and 3.14.7)* — filter which models are loaded by entering one or more OnlyFans list names (comma-separated). Leave blank to load all subscribed models. Equivalent to `--ul` on the command line.

- **Like/Unlike** — automate liking or unliking posts
- **Metadata** — update your local database without downloading files
- **Check modes** *(3.14.3, 3.14.5, and 3.14.7)* (Post Check, Message Check, Paid Check, Story Check) — browse all content for a creator in a table view and selectively download individual items
- **Scrape individual posts by URL or Post ID** *(3.14.5 and 3.14.7)* — download specific posts by pasting OnlyFans post URLs or post IDs directly, bypassing model and area selection entirely

After selecting an action, click **Next** to move on.

--- 

### Select Content Areas & Filters

<img src="https://github.com/user-attachments/assets/bd4c6ed1-7b4a-44f9-a81e-7b14168d64c4" width="600" alt="Select Content Areas & Filters">

Choose which types of posts to scrape and apply filters before the scrape begins:

- **Content areas** — Profile, Timeline, Pinned, Archived, Highlights, Stories, Messages, Purchased, Streams, Labels
- **Post Date Range** — filter content by post date using independent **After** and **Before** controls; each side can be enabled or disabled independently:
  - **Fixed date** — pick a specific calendar date with the date picker
  - **Relative** — enter a number + unit (e.g. *7 days ago*); the date is computed fresh at each scrape run so saved relative settings always mean the last N days
  - Equivalent to the `--after` / `--before` CLI flags
- **Media type filter** — limit the scrape to Images, Videos, and/or Audios
- **Post count limit** — cap the number of posts fetched per creator
- **Rescrape everything** — force a full history scan, ignoring the "start after last seen" cache; use this after changing filters or to do a complete rebuild
- **Include Post Text** *(3.14.3, 3.14.5, and 3.14.7)* — when enabled, the text body of each post is included alongside the downloaded media
- **Video quality** *(3.14.7)* — choose **Default**, **240**, **720**, or **source**; equivalent to the `-q` / `--quality` CLI flag
- **Daemon Mode** — set a repeat interval (1–1440 minutes) so the scraper runs automatically on a schedule; optional system notification, sound alert, and **@here Discord ping when new content is found**
- **Allow duplicates** *(3.14.7)* — when enabled, keep multiple copies of the same `media_id` across posts/areas. Optional sub-option: **Also keep Messages + Purchased copies of the same media** (default off) — collapses Messages↔Purchased/Paid to Messages only while still keeping other area reposts
- **Username filter** — pre-filter the model list to only show specific creators

Once you're happy with your selections, click **Next** to load and choose your models.

Settings on this page are **not saved automatically**. Use the buttons in the lower-right of the navigation bar to manage persistence:
- **Save Settings** — saves the current selections to `gui_settings.json` so they are restored on the next launch *(3.14.7: shows a confirmation dialog before saving)*
- **Reset Settings** — clears all saved area settings and restores every option to its default state *(3.14.7: shows a confirmation dialog before resetting — defaults to No to prevent accidental clears)*

---

### Select Models

<img src="https://github.com/user-attachments/assets/2cec0d50-a4a8-4180-8202-bde316003406" width="600" alt="Select Models">

A searchable, filterable table of all creators you are subscribed to. From here you can:

- **Search** by username, display name, or any column
- **Right-click** any cell to instantly filter the table by that value
- **Sort** by clicking any column header
- **Select** individual creators or use Select All / Select None
- **Click a username** *(3.14.7)* — toggles that model's checkbox (avatar click still opens OnlyFans without changing selection)
- **Show Avatars** — toggle to display each creator's profile picture alongside their name in the table. Clicking an avatar opens that creator's OnlyFans page in your browser
- The footer shows how many rows are displayed vs the total (e.g. `42 / 1200 rows (filtered)`)
- **Reload Models** *(3.14.5 and 3.14.7)* — a **Reload Models** button appears in the navigation bar after models load, letting you re-fetch the model list without going back to the Select Action page

Click **Next >>** when you have selected the creators you want to process. That opens the **Scraping page** (media table), where you review filters and start the job.

---

### Scraping page

<img src="https://github.com/user-attachments/assets/0d04b396-9ae2-40db-a29e-c40bf6f55f7a" width="600" alt="Scraping page — media table">


The main scrape workspace after models are selected. Until you press **Start Scraping >>**, the table may show **Ready to scrape** with guidance to begin fetching media for your selected models and areas.

**Toolbar**
- **Filters** — show/hide the left filter sidebar *(3.14.7: collapsible; remembers width)*
- **Reset** / **Apply Filters** — clear or apply table filters
- **Start Scraping >>** — begin the scrape for the selected models/areas (may open **Confirm scrape** first — see below)
- **New Scrape** — return to the start of the wizard (asks to cancel first if a run is active)
- **Open Downloads Folder** — opens your configured Save Location in the file manager
- **History** *(3.14.7)* — recent scrape / check runs (Details, Re-run, delete)
- **Export CSV** *(3.14.7)* — export visible (or selected) rows; respects Privacy mode usernames
- Check-mode-only cart actions (**Select All**, **Add Selected**, **>> Send Downloads**) appear only in check modes

**While a scrape runs**
- **Log panel** — streams OF-Scraper output in real time
- **Progress bar** (footer) — overall download progress and a running total of bytes downloaded (bytes only ever increase mid-scrape)
- **Cart counter** (toolbar) — items queued for download (especially useful in check mode)
- **Cancel** — cooperative stop (API pagination, mid-file chunks, and between models); shows **Cancelling…** until the worker exits
- **Per-model badge bar** *(3.14.7)* — live status chips above the table
- **Scrape summary** *(3.14.7)* — at the end of each run, a TUI-style summary in the log: per-model action line plus **GLOBAL RUN TOTALS** (items, data transferred, videos/audios/images, skipped, failed)

**Table**
- Filter sidebar: text search, media type, response type, downloaded/unlocked status, post date range, duration, price, IDs, and more
- **Filter presets** *(3.14.7)* — save / rename / delete named filter sets; last-used restored on startup
- Sort by column header; right-click a cell to filter by that value
- **Duplicate** column *(3.14.7)* — highlights repeated `media_id` rows that the download pipeline will skip when Allow duplicates is off
- Sticky columns, remembered column layout, and empty-table guidance overlay *(3.14.7)*

See also [Table page](#table-page) under GUI features for sticky columns, CSV, History, and Duplicate-column details.

---

### Confirm scrape (pre-start review) *(3.14.7)*

<img src="https://github.com/user-attachments/assets/e66b13cf-45a1-491f-a91c-52cf3a2d3283" width="600" alt="Confirm scrape — Review this scrape before starting">

Before a larger or high-impact job starts, **Start Scraping >>** opens a **Confirm scrape** dialog titled **Review this scrape before starting**. Use it to double-check the job, then **Start Scraping** or **Cancel**.

The summary includes:
- **Actions** — e.g. download, like/unlike, metadata, or a check mode
- **Models** — count and names (shown as `[Hidden for Privacy]` when Privacy mode is on)
- **Areas** — content areas selected on the Areas page (Timeline, Messages, Labels, …)
- **Media types** — Images / Videos / Audios (or config default)
- **Options** — high-impact flags when enabled, for example:
  - Allow duplicates
  - **Rescrape everything** (emphasized)
  - Scrape entire paid page / Scrape labels
  - Daemon interval
  - Date filter range
  - Manual URL/ID count (manual scrape)
  - **Delete model DB** / **Delete downloaded files** (emphasized as destructive)
- **Rough ETA** — a low–high minute band (e.g. `~5–60 min (large job — time varies with content volume)`), with a note that ETA is only a guide until the scrape measures real media volume

**When the dialog appears**
- Always for **destructive** options (delete DB / delete downloads)
- Also for high-impact jobs: rescrape everything, allow duplicates, scrape paid page, daemon mode
- Also for multi-model runs (2+ models), many areas (4+), check mode, or large manual URL lists (10+)
- Small single-model jobs with no high-impact flags may start without prompting

**Don't ask again**
- Checkbox: **Don't ask again for typical jobs (still warn for delete DB/files)**
- Saves `skip_scrape_confirm` in `gui_settings.json` and skips typical confirms afterward
- Destructive delete-DB / delete-files jobs **always** confirm, even after opting out

Related prompts on the same page: **disk space** check against Save Location before start, and **Confirm downloads** when a check-mode cart has 25+ items (see [Safer cancel & confirms](#safer-cancel--confirms-3147)).

---

### Check Mode *(3.14.3, 3.14.5, and 3.14.7)*

<img src="https://github.com/user-attachments/assets/9f50a722-4f76-40cb-8367-ab5f2dbe1b1d" width="600" alt="Check Mode table">

Check modes (**Post Check**, **Message Check**, **Paid Check**, **Story Check**) let you browse every piece of media for a creator before committing to a download. Instead of queuing everything at once, you see a full table first and pick exactly what to save.

- **Locked / paywalled items** are clearly labeled **Locked** in the Download Cart column — grey background, cannot be selected — so you can instantly see what is behind a paywall without trying to download it
- **Toggle rows** for download by clicking the Download Cart cell, then click **Send Downloads** to download only what you selected
- **Filters** work the same as on the main table — narrow by media type, response type, date range, price, and more
- **Progress bar** in the footer tracks each selected download individually: e.g. `3 / 10` as items complete
- Items update in real time as they finish: `[downloaded]`, `[skipped]`, or `[failed]`

> **Which check mode to use:**
> - **Post Check** — timeline, pinned, archived, streams, and label posts
> - **Message Check** — direct messages and PPV messages
> - **Paid Check** — explicitly purchased content
> - **Story Check** — stories and highlights

---

### Authentication

<img src="https://github.com/user-attachments/assets/4213c577-1064-4f38-860a-43c6dbfc80bc" width="600" alt="Authentication">

Manage the credentials OF-Scraper uses to connect to OnlyFans. Each option has a **?** button that jumps to the matching Help section:

- **Credentials** — paste `sess` / `auth_id` / `auth_uid` / user-agent / `x-bc` manually from DevTools
- **Import Cookies** *(recommended when already logged in)* — read allowlisted cookies from the selected browser profile on disk (Zen/Firefox on Windows; any listed browser on Linux). Chrome-family **Import Cookies** is Linux-only on Windows builds
<img src="https://github.com/user-attachments/assets/90cb1eec-4f76-46f8-8737-693a3e7836f4" width="600" alt="Import Cookies Dropdown">
<img src="https://github.com/user-attachments/assets/3a825b47-7e8d-4bed-a945-ef132ca01491" width="600" alt="Import Cookies loading">
<img src="https://github.com/user-attachments/assets/2a2cce6a-dea1-443f-9efd-56a50cc9f669" width="600" alt="Imported Cookies">
  - **User-Agent *(3.14.7)*** — filled to match the selected browser: live `navigator.userAgent` when the browser is available via remote debugging, otherwise the install / profile Gecko user agent
 
- **Login in System Browser…** *(3.14.7)* — opens a temporary copy of any browser from the dropdown (including Chrome on Windows) and captures credentials after you log in
<img src="https://github.com/user-attachments/assets/b18b70c4-c349-435e-be52-0cb398e980a6" width="600" alt="Login System Browser">
<img src="https://github.com/user-attachments/assets/1c324b6a-e00d-459b-b85a-29dd183a4963" width="600" alt="Login System Browser Credentials captured">
<img src="https://github.com/user-attachments/assets/80ab1b74-a12c-402e-9a5a-4ba085b4e971" width="600" alt="Login System Browser Credentials imported">
  
- **Login in App Browser…** *(3.14.7)* — embedded Chromium window inside the app (`PyQt6-WebEngine`)
- Cookie allowlist + restrictive `auth.json` file permissions *(3.14.7)* — only auth cookies/headers are kept; unrelated browser cookies are dropped
- Cancel support for Import Cookies and browser login, plus an optional hard login timeout *(3.14.7)*

<img src="https://github.com/user-attachments/assets/f2d615cc-5064-4caf-afd7-dca6dcbdb574" width="600" alt="Login in App Browser">

If scraping fails with an auth error, the GUI will offer a direct link to jump to this page. Footer **Auth / Config / Key** health chips also surface auth problems at a glance *(3.14.7)*.

---


### Configuration

Edit all OF-Scraper settings without touching `config.json` directly. Settings are organized into tabs. Each tab’s **?** button jumps to the matching section in the built-in Help page (full field reference, placeholders, and examples).

**Save** and scrape start both validate key settings (Save Location, File Format uniqueness, Directory Format under Save Location, length bounds, FFmpeg path, empty download filters). **Errors block** save/start; **warnings** ask whether to continue.

- **General** — profile name, metadata path, Discord webhook
<img src="https://github.com/user-attachments/assets/99b30f74-3a1e-4ee8-94bc-6b523cd3ed81" width="600" alt="Configuration">

  - **Main Profile** / **Metadata Path** — default profile and where model DB/metadata files live (supports placeholders)
  - **Discord Webhook URL** — optional; [Discord webhook setup](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks). Enable sending from **Select Content Areas → Additional Options** after pasting the URL

- **File Options** — where files are saved, folder and filename format, date format, text length. *(3.14.7 on Windows: filesystem paths display and save with backslashes; `config.json` stores them as escaped `\\`. Directory/File Format templates still use `/`.)*
<img src="https://github.com/user-attachments/assets/0c83a457-b49a-4ffb-95b6-7fdc6f90aa07" width="600" alt="File Options">

  - **Save Location** — root download directory
  - **Directory Format** — folder template under Save Location (must stay **relative**; no absolute paths or `..`). Invalid templates are blocked on Save / scrape start
  - **File Format** — must include a uniqueness token: `{filename}`, `{media_id}`, or `{original_filename}`
  - **Date Format** — Arrow/Moment-style tokens (e.g. `YYYY-MM-DD`); avoid Windows-illegal characters like `:`
  - **Text Length / Space Replacer / Truncation** — caption length in names, space substitution, OS path truncation
  - Full placeholder list: in-app **Help → Configuration → File Options**

- **Download** — free space minimum, auto-resume, post count limit, media type filter (Images / Audios / Videos / Text); *(3.14.7)* **DRM Duration Match %**, Verify All Integrity, FFmpeg path
<img src="https://github.com/user-attachments/assets/f9ff5b18-f616-44f2-8014-fcc940c56b93" width="600" alt="Downloads">

  - **DRM Duration Match %** (default **98**) — after remux, rejects truncated/empty files vs expected duration (higher = stricter). DRM merges always use this gate; enable **Verify All Integrity** to apply it to non-DRM media too
  - **FFmpeg Path** — required to merge DRM audio/video and for duration checks; recommended **FFmpeg 7.1.1 or lower**
  - Automatic resilience: stall timeout/retry, stricter `.part` finalize, media/DRM host allowlist (`onlyfans.com` / `cloudfront.net` + **Media Host Suffixes**), paths confined under Save Location

- **Scripts** *(3.14.7)* — optional external scripts under `script_options` in `config.json` (leave paths empty/`null` to disable):
<img src="https://github.com/user-attachments/assets/ca9e90a8-1429-4089-adbf-2c87a5f665ae" width="600" alt="Scripts">

  - **After Action Script** — runs after an action for each model has completed
  - **Post Script** — runs after all actions for all models have completed
  - **Naming Script** — can rewrite the final filename/path before download (disabled by default)
  - **Preferred file extensions** — optional per-type remaps (each type off by default). Check **Images**, **Videos**, and/or **Audios** to replace only that type’s `{ext}` in the saved filename (**no convert/remux**). Settings live under `file_options` (`override_*_extension` + `image_extension` / `video_extension` / `audio_extension`)
  - **After Download Script** — runs after each individual media download completes
  - **Skip Download Script** — runs before a download; return `"False"` or empty stdout to skip that file
  - Older builds used typo key `scripts_options`; current **Save** migrates values into `script_options`

- **Performance** — concurrent downloads, thread count, speed limit
<img src="https://github.com/user-attachments/assets/4575261f-3377-497a-baad-a6d4105e2335" width="600" alt="Performance">

  - **Thread Count**, **Download Semaphores** (downloader concurrency), **Download Speed Limit** (KB/s; `0` = unlimited)

- **Content** — file size limits, duration limits, ad blocking
<img src="https://github.com/user-attachments/assets/71b71f09-e35f-4390-9753-1ff80f6f6ce1" width="600" alt="Content">

  - **Block Ads**; min/max file size (e.g. `500MB`, `2GB`, or `0` for no limit); min/max length in **seconds**

- **CDM** — DRM key mode and key file paths (needed for protected content); *(3.14.7)* new installs default to **manual**; remote modes warn and never send session cookies
<img src="https://github.com/user-attachments/assets/1745e364-f032-4760-9a1a-c6a0e3b40c3b" width="600" alt="CDM">

  - Prefer **manual** + local `client_id.bin` / `private_key.pem` (use **DRM Key Creation**). Remote modes (`cdrm` / `cdrm2` / `keydb`) are opt-in and may fail on OnlyFans licenses
  - **KeyDB** is currently not working — avoid for now
  - Existing configs keep their saved key mode (new-install default does not rewrite `config.json`)

- **Advanced** — dynamic mode, cache mode, download bars, logging options, and more. *(3.14.7)* **OnlyFans API resilience** settings:
<img src="https://github.com/user-attachments/assets/e6d7c171-79e9-404d-8ae6-2cc7ce81d4e2" width="600" alt="Advanced">

  - **Dynamic Mode** — signing-rules source (`datawhores`, `digitalcriminals` / `dc`, `xagler`, `rafa`, `generic`, `manual`). Try switching on 401/403 or signature failures
  - **SSL Verify** — `custom` (built-in CA bundle), `true` (system certs), or `false` (disable verification). If auth/model load fails with good credentials (proxies / TLS-inspecting AV / broken CA store), try **`false`**, Save, then Retry — less secure; use only when needed
  - **API Path** — change the `/api2/v2` prefix globally if OnlyFans renames the API path (`OFSC_API_PATH`)
  - **Manual Dynamic Rules** — paste / load local signing-rules JSON when Dynamic Mode is `manual` (`OFSC_DYNAMIC_RULE_MANUAL`)
  - **Dynamic Rules URL** — custom remote rules JSON URL when Dynamic Mode is `generic` (`OF_DYNAMIC_GENERIC_URL` / `OFSC_DYNAMIC_GENERIC_URL`)
  - **API Endpoint Overrides** — JSON map of individual endpoint keys (e.g. `meEP`) to full URL templates (`OFSC_API_*` env still wins when set)
  - **Media Host Suffixes** — extra allowed media/DRM CDN hosts beyond `onlyfans.com` / `cloudfront.net` (`OFSC_MEDIA_HOST_SUFFIXES`)
  - **Backend** — `aio` (aiohttp) or `httpx`; switch if proxy/TLS issues
  - **Cache Mode** — `sqlite` / `json` / `disabled` (prefer GUI rescrape over disabling cache globally)
  - **Code Execution** — enables `eval()` in placeholders; leave off for untrusted content
  - **Download Bars / Append Log / Sanitize Text** — console bars (can slow high thread counts); daily vs per-run logs; clean text before DB insert
  - **Remove Hash Match** — skip hash / hash only / hash + **delete** duplicate files (deletion is permanent)
  - **Enable Auto After** — speeds rescrapes via cutoff; disable temporarily if older content seems missing
  - **Temp Directory** — optional temp/`.part` root; empty = default
  - **Infinite Loop (Action Mode)** / **Default User & Black Lists** — mainly CLI/automation defaults (comma-separated list names)

- **Response Type** — customize how content type folders are named
<img src="https://github.com/user-attachments/assets/277d208c-cfe4-432a-850c-2a4e51841f54" width="600" alt="Response Type">

  - Rename aliases for posts / messages / paid / archived / etc. These pair with `{responsetype}` / `{response_type}` in Directory Format

- **Overwrites** *(3.12.9 only)* — per-media-type overrides for file format, size limits, and more

Deep field docs, placeholders, and DRM Match % details: in-app **Help / README → Configuration**. Background: [OF-Scraper GitBook](https://of-scraper.gitbook.io/of-scraper).


### DRM Key Creation

<img src="https://github.com/user-attachments/assets/cedb95a7-0aa7-4f1b-97cb-17e71cc3175b" width="600" alt="DRM Key Creation">
<img src="https://github.com/user-attachments/assets/71750dba-0777-4c4a-b5c6-3228caea5bdf" width="600" alt="DRM Key Created">
<img src="https://github.com/user-attachments/assets/f862e757-df08-444a-95de-65010bfe6def" width="600" alt="DRM Key Creation Clean up">

A built-in tool for generating the DRM decryption keys required to download protected (DRM-locked) content. You need these keys if you want to download videos that are encrypted with Widevine DRM.

> **Note:** DRM key generation is **not supported in Docker**. Use the GUI on a normal host system (Windows/Linux desktop) instead of a container when generating `client_id.bin` and `private_key.pem`.

- **Fully automated** — downloads the Android SDK, sets up an emulator, and extracts the keys without any manual steps
- **Streams output** directly into the app so you can follow progress in real time — the Generate Keys button and live console are at the top of the page; Requirements & Information sits below the console *(3.14.7)*
- **Auto-configures** — once keys are generated, the CDM key paths in your config are updated automatically. No need to edit `config.json` manually
- **Virtualization checks** *(3.14.7)* — checks that CPU virtualization / Hyper-V is available before running the Android emulator used for key extraction
- Accessible from the sidebar or via the quick link in the startup notice if CDM keys are not yet configured

> The key extraction process can take 10–90 minutes depending on your hardware. A progress log is shown throughout.

---

### Profile Manager

<img src="https://github.com/user-attachments/assets/003fe840-0604-4c58-b16d-05c496639718" width="600" alt="Profile Manager">

Profiles let you maintain completely separate configurations and credentials — useful if you manage multiple accounts or want different download settings for different use cases.

- **Create** a new profile with a custom name
- **Rename** or **delete** existing profiles
- **Switch** between profiles — the active profile is shown in the navigation bar
- Each profile has its own `auth.json` and data directory

---

### Merge Databases

<img src="https://github.com/user-attachments/assets/c7916662-5dc8-4f7d-a81a-47a136f93643" width="600" alt="Merge Database">

Merge data from one OF-Scraper database into another. This is useful if you have downloaded content across multiple profiles or machines and want to consolidate your records.

- Select a **source database** (the one to merge from)
- Select a **target database** (the one to merge into)
- Duplicate records are handled automatically — only new entries are added

---

### Help / README

<img src="https://github.com/user-attachments/assets/fd82cfcc-6ca4-4fba-9099-e9d1b0515b52" width="600" alt="Help / README">

Built-in documentation available at any time without leaving the app:

- **Table of contents** with clickable links — each entry scrolls directly to the matching section
- **Jump to…** dropdown for fast navigation to any section by name
- **About** and **Text size** — see [About & text size](#about--text-size-3147); Help toolbar also has **A−** / **A+** / size dropdown / **Reset**
- **Show Welcome** — reopen the first-run welcome tip
- **Additional Help** button links to the project Discord if you need further assistance
- Every **?** button throughout the GUI links directly to the relevant section here
- *(3.14.7)* **Configuration** in this Help page and the public GUI README are kept in sync for each config tab (General through Response Type), including Advanced **API resilience** settings
- *(3.14.7)* **Auth Issues** walks built-in capture methods first, then **manual DevTools copy** (Network → filter **`init`** → main timeline → refresh → Request Headers) if Import/Login fail, then a **Wrong user / sess–auth_id** section, then Dynamic Mode / SSL Verify and related tips

---

## GUI features

### Application icon
- The GUI displays its own icon in the **title bar**, **taskbar**, and **system tray** instead of the generic Python icon
- On Windows, the correct AppUserModelID is registered so the taskbar groups and identifies the app as OF-Scraper rather than Python

### Theme
- Toggle between **Dark** and **Light** mode using the button at the bottom of the left sidebar
- Theme preference is saved to `gui_settings.json` in your ofscraper config directory
- Left-nav pages use **colored icons** next to each label (Scraper, Authentication, Configuration, …); plugin pages get their own sidebar entry when loaded
- *(3.14.7)* While a model list is loading or a scrape is running, theme changes wait until that work finishes

### About & text size *(3.14.7)*

Click the sidebar version button (e.g. **`v3.14.7`**) — or **Help / README → About** — to open **About OF-Scraper**. Opening it again focuses the same window (it does not stack duplicates).

<img src="https://github.com/user-attachments/assets/ba6fbb2e-1638-481d-9d6e-6e2159ee1bde" width="600" alt="About">

**About shows**
- **App version** — installed OF-Scraper version
- **GUI patch** — applied patch id (useful when reporting issues)
- **Operating system**, **FFmpeg**, and **FFprobe** paths/status
- **Updates** — status line after you run **Check for updates** (PyPI, same source as the CLI), plus **Open PyPI** when a newer release is available
- On startup the GUI also quietly checks PyPI; if a newer release exists you get a one-time prompt (Open PyPI / Dismiss this version / Later)

**Text size (global GUI scaling)**
- Controls live in **About** and on the **Help / README** toolbar: **A−**, size dropdown, **A+**, and **Reset**
- Sizes: **12**, **13** (default), **14**, **16**, **18**, **20** px
- Scales the whole app (theme, pages, dialogs, Help). Preference is saved as `gui_font_size` in `gui_settings.json` (legacy `help_font_size` is migrated)
- **Reset** restores the default **13** px
- The sidebar ASCII logo stays at a fixed size and is **not** scaled with text size
- Like the theme toggle, size changes wait if a model list is loading or a scrape is running

### Verbose Log
- Toggle **Verbose Log** mode using the button in the bottom-left navigation bar (below the Theme button)
- When enabled, all log levels are shown in the in-app log panel and a dedicated verbose log file is written to your ofscraper config directory (e.g. `ofscraper_gui_verbose_<profile>_<timestamp>.log`)
- Verbose logging is disabled by default and the preference is saved to `gui_settings.json`

### Privacy / demo mode *(3.14.7)*

<table>
  <tr>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/07de2297-8a07-412c-9247-a23baac8d5f5" width="100%" alt="Privacy Mode Off">
    </td>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/9ea980c7-328c-423d-8557-ea5d2c1daf59" width="100%" alt="Privacy Mode On">
    </td>
  </tr>
</table>

- Toggle **Privacy** in the bottom of the sidebar for safe screenshots / demos
- Masks auth fields, Save Location / webhook / FFmpeg / CDM paths, model names, and table usernames
- Extra redaction in the console log; preference saved in `gui_settings.json`

### Context-sensitive help
- Every section and option throughout the GUI has a small **?** button next to it
- Clicking a **?** button navigates directly to the matching section in the Help / README page
- Authentication options (Credentials, Import Cookies, System Browser, App Browser) each have dedicated Help sections *(3.14.7)*

### Welcome to OF-Scraper GUI
- An initial start-up window welcoming you to OF-Scraper GUI with brief helpful information
- *(3.14.7)* Shown **before** the Missing FFmpeg/CDM paths dialog so first-run messaging is not buried behind dependency prompts
<img src="https://github.com/user-attachments/assets/5bc8e9d4-7619-4475-9873-be4f6c14546d" width="600" alt="Welcome to OF_Scraper GUI">

### Startup dependency check
- On launch (after Welcome when applicable), the GUI checks whether **FFmpeg** and **CDM key paths** are configured
- If either is missing, a notice appears from **Configuration** (and related entry points). On the Areas page, missing paths are shown as a status tip so you can keep configuring while models load
- **Open Config → Download (FFmpeg)** and **Open Config → CDM (Manual keys)** navigate the main window to the relevant config tab
- **Generate DRM Keys** closes the dialog and navigates to the DRM Key Creation page

<img src="https://github.com/user-attachments/assets/3ad709d5-6bbd-429c-b772-1f75c2217172" width="600" alt="Missing Configuration Paths">

### Auth failure handling
- When the model list cannot be loaded (auth error), a dialog appears offering:
  - **Retry** — re-fetch models without leaving the page
  - **Go to Authentication** — jump directly to the auth page
  - **Dynamic Mode (Config)** — jump directly to Configuration → Advanced → Dynamic Mode field
  - **SSL Verify (Config)** — jump to Configuration → Advanced → SSL Verify (try **`false`** if credentials are correct but TLS/proxy issues persist; less secure)
  - **Help / README** — navigate to the Auth Issues section of the built-in help
- A **Retry** button also appears inline in the navigation bar
- Dialog text also suggests trying Dynamic Mode and/or SSL Verify → `false` when auth looks correct but model load still fails

### Login in Browser *(3.14.7)*

<img src="https://github.com/user-attachments/assets/f2d615cc-5064-4caf-afd7-dca6dcbdb574" width="600" alt="Login in App Browser">


Two ways to capture credentials by logging in (plus Import Cookies / manual paste):

**Login in App Browser…**
- Opens an embedded Chromium window inside the app
- Log in to OnlyFans normally — the GUI watches for session cookies in the background
- All credential fields start blank (`—`); values are revealed only after `auth_id` is confirmed
- **"Use These Credentials"** is only enabled after a valid `auth_id` is confirmed
- `x-bc` is captured automatically; if missing, use DevTools Network tab
- Requires `PyQt6-WebEngine` — `pip install PyQt6-WebEngine` or `pipx inject ofscraper PyQt6-WebEngine`
- **Cancel Login** aborts without importing; optional hard timeout (default 10 minutes)

**Login in System Browser…**
- Opens a **temporary** copy of whichever browser is selected under **Select Browser** (including Chrome / Edge / Brave on Windows)
- Fresh empty profile — you must log in again; this is not your everyday session
- The Import Cookies “Linux only” limit does **not** apply here
- Prefer Import Cookies when you are already logged in on Zen/Firefox (Windows) or any browser (Linux)

> **KDE Plasma note:** On KDE Plasma / KDE neon the embedded App Browser view may briefly appear blank while the page loads. This is cosmetic — the page loads correctly regardless.

### User Lists *(3.14.5 and 3.14.7)*
- On the **Select Action** page, a **User Lists** field appears under "Download content from a user"
- Enter one or more OnlyFans list names (comma-separated) to load only models who are members of those lists
- Leave blank to load all subscribed models (default behavior)
- Equivalent to the `--ul` / `--userlist` CLI flag — also supported for CLI auto-start
- After models load, a **Reload Models** button appears in the navigation bar so you can re-fetch without going back to the start

### Scraper workflow
- **Area Selector page**: models are loaded from the API in the background while you configure options; an inline progress indicator shows loading state
- Filters configured on the Area Selector page are automatically carried over to the Scraping page sidebar when models are confirmed
- **Username filter** on the Area Selector page pre-narrows the Model Selector list
- After models: **Scraping page** → **Start Scraping >>** → optional **Confirm scrape** review → run

### Safer cancel & confirms *(3.14.7)*

- **Cancel** shows a Cancelling… state and cooperatively stops API pagination, mid-file chunk downloads, and between models — not only between queued media items
- **Confirm scrape** — for larger / high-impact jobs, a pre-start **Review this scrape before starting** dialog summarizes actions, models, areas, media types, options (rescrape, allow duplicates, daemon, deletes, …), and a rough ETA. Full details: [Confirm scrape (pre-start review)](#confirm-scrape-pre-start-review-3147)
- **Confirm downloads** when the check-mode cart has 25+ items
- **Disk space check** before scrape / Send Downloads against Save Location
- **Config validation** on Save and before scrape (File Format uniqueness tokens, Directory Format under Save Location, FFmpeg path, etc.)

### Status strip & health chips *(3.14.7)*

- **Before Scan**

<img src="https://github.com/user-attachments/assets/3f7e2241-1dbc-45f1-93ab-ea735e9a76c5" width="100%" alt="Status Strip Before Scan">

- **During Scan**

<img src="https://github.com/user-attachments/assets/53770370-5d6c-4830-9e35-cf25294ff74b" width="100%" alt="Status Strip During Scan">

- **Scan Finished**

<img src="https://github.com/user-attachments/assets/acc32487-ef11-4796-b06a-1d973f9eeb3b" width="100%" alt="Status Strip Scan Finished">


- Unified footer: phase badge (Ready / Running / Cancelling / Daemon / Complete), status text, progress, row count
- Live **elapsed timer** while a scrape is running *(3.14.7)*
- Clickable **Auth**, **Config**, and **Key** health chips (green / orange / red) — hover for detail; click to open the matching settings page
- Live **per-model badge bar** above the table during scrapes
- After a run, a **Download failures** dialog lists failed items (filter table / add to cart in check mode)
- Console panel **height is remembered** across relaunch / returning to the scrape page *(3.14.7)*

### Daemon mode (auto-repeat scraping)
- Enable from **Select Content Areas & Filters → Daemon Mode**
- Sets an interval (1–1440 minutes) for repeated scraping runs
- While waiting between runs, a **countdown timer** is shown in the table toolbar with wall-clock ETA *(3.14.7)*
- **Last-run chip** between cycles shows downloads / fails / size from the previous cycle *(3.14.7)*
- Optional **system tray notification** when each run starts (all platforms)
- Optional **sound alert** when each run starts (Windows)
- Optional **@here Discord mention** — when enabled, the Discord scrape summary is prefixed with `@here` only when new content was downloaded in that run. No ping is sent for runs that find nothing new. Requires a Discord webhook to be configured
- A **Stop Daemon** button appears in the toolbar; clicking it gracefully stops the loop after the current run

### Table page 
- **Right-click** any cell to instantly filter the table by that cell's value
- Click any **column header** to sort by that column
- The footer shows the current row count and filtered vs total count (e.g. `42 / 1200 rows (filtered)`)
- The toolbar shows a live **Cart: N items** counter as you select rows for download
- **Open Downloads Folder** button in the toolbar — opens the configured `save_location` from your config directly in your file manager
- **New Scrape** button: if scraping is active, confirms cancellation first; optionally resets all options and model selections back to defaults before returning to the start
- **Collapsible filter sidebar** *(3.14.7)* — click **◀ Filters** in the toolbar to hide the left-hand filter panel and give the table the full window width. The button changes to **▶ Filters** when the sidebar is hidden; clicking it again restores the sidebar to exactly the width it was before it was collapsed
- **Filter presets** *(3.14.7)* — save / save as / rename / delete named filter sets; last-used restored on startup
- **Column layout** *(3.14.7)* — remembered width / order / visibility; **Sticky columns** keep Number / Download Cart (and optionally UserName) visible while scrolling horizontally
- **Export CSV** *(3.14.7)* — export visible (or selected) rows; respects Privacy mode usernames
- **History** *(3.14.7)* — browse recent scrape / check runs; Details, Re-run, delete
- **Click Post ID / Media ID** *(3.14.7)* — opens the OnlyFans post in your browser
- Empty-table guidance overlay when no rows are visible *(3.14.7)*
- Check-mode cart actions (Select All / Add Selected / Send Downloads) only appear in check mode *(3.14.7)*
- **Duplicate column** *(3.14.7)* — shown between **Downloaded** and **Unlocked**. When the same `media_id` appears more than once in the API response (e.g. a post indexed in both Timeline and Archived), every occurrence after the first shows **Duplicate** highlighted in orange with a tooltip explaining the row will be skipped by the download pipeline. When **Allow duplicates** is disabled (the default), duplicate rows also show `Downloaded: False` to make clear those specific rows were not downloaded

<table>
  <tr>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/a5903ecf-8192-473c-9bc2-ca8125c4000b" width="100%" alt="Duplicate Column">
    </td>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/3d6cdf5a-9208-41e6-9e93-4e08f8514c92" width="100%" alt="Table with sticky columns">
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/ac4bb037-c9e9-481e-bdcf-377ddc470062" width="100%" alt="History toolbar">
    </td>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/c180f03f-65bd-43eb-873a-8bf4dde20b26" width="100%" alt="Post ID / Media ID link cells opening OnlyFans">
    </td>
  </tr>
  <tr>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/b6611159-7970-4556-898f-84e552e2c05f" width="100%" alt="Export CSV">
    </td>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/b616a244-b630-4654-8980-07a903f28c4a" width="100%" alt="Cancel">
    </td>
  </tr>
</table>




### Check mode *(3.14.3, 3.14.5, and 3.14.7)*
- Select **Post Check**, **Message Check**, **Paid Check**, or **Story Check** from the action selector to enter check mode
- A full media table is shown for the selected creator(s) — including content that is behind a paywall
- **Locked** items (paywalled, no download URL) are clearly marked in the Download Cart column with a grey cell that cannot be clicked
- Select any unlocked rows and click **Send Downloads** to download only those items
- The footer progress bar tracks check mode downloads individually (e.g. `3 / 10` as items complete)

### Progress bar
- A compact progress bar in the footer shows overall download progress and a running total of bytes downloaded
- The bytes counter is **monotonically increasing** — it only ever goes up during a session and never drops back down mid-scrape
- Resets automatically when a new scrape is started

### CLI auto-start
- If launched with `ofscraper --gui` together with action, area, and username flags, the GUI wizard is skipped and scraping begins automatically — matching the TUI behavior for scripted/automated workflows
- `--ul` user list auto-start *(3.14.5 and 3.14.7)*: `ofscraper --gui --ul testing -a download -o all`
- *(3.14.7)* Unattended CLI / Docker `GUI_ARGS` auto-start skips interactive scrape-confirm / disk / remote-key dialogs so a container can start without a click
- This is also how the Docker container starts a scrape automatically via the `GUI_ARGS` environment variable (see [Docker](#docker))

### Crash diagnostics *(3.14.7)*
- If the GUI exits unexpectedly, diagnostic files are written under your ofscraper config directory:
  - `~/.config/ofscraper/gui_crash_logs/model_fetch_breadcrumbs.log` — recent UI / scrape stage markers (includes whether a model fetch or scrape was in progress)
  - `~/.config/ofscraper/gui_crash_logs/faulthandler.log` — native / fatal dumps when available
- When reporting a problem, include the last ~30 breadcrumb lines and your GUI patch id (sidebar version → About)
- In Docker these files live on the mounted config volume (see [Docker](#docker))

--- 

### Scrape individual posts by URL or Post ID *(3.14.5 and 3.14.7)*

<table>
  <tr>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/35f61e72-fab7-46b2-a637-082bfa558cf8" width="100%" alt="Scrape individual posts">
    </td>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/b8df0702-ff0a-4fd5-98fc-3ab3cf141c42" width="100%" alt="Scrape individual posts by URL or Post ID">
    </td>
  </tr>
</table>


A dedicated action for downloading specific posts without going through model or area selection.

**How to use:**
1. On the **Select Action** page, choose **Scrape individual posts by URL or Post ID** and click **Next**
2. On the URL input page, paste one or more post URLs or post IDs — one per line, or comma-separated
3. Click **▶ Start Scraping**

**Accepted formats:**
- Full post URL: `https://onlyfans.com/123456789/username`
- Post ID only: `123456789`
- Profile URL: `https://onlyfans.com/username` (scrapes all accessible posts for that creator)

**Notes:**
- Model selection and area selection pages are skipped entirely
- Multiple URLs/IDs can be entered at once — separate by newlines or commas
- Lines starting with `#` are treated as comments and ignored
- Equivalent to the TUI command `ofscraper manual --url <url>`

---

### Discord webhook integration

The GUI includes a Discord webhook toggle that controls whether scraping activity is posted to your configured Discord channel.

**Discord toggle (GUI)**
- A Discord enable/disable toggle is available on the scrape settings pages (all versions)
- When enabled and a webhook URL is set in Configuration → General, notifications are sent during the scrape
- When the `--discord` flag is also passed on the command line, the CLI value takes precedence

**Notification level selector** *(3.14.5 and 3.14.7)*
- Choose **LOW** (warnings, errors, and run summary only) or **NORMAL** (all events). Defaults to **LOW**
- On first enable, a one-time prompt asks if you want to save `LOW` as the permanent default in `gui_settings.json`
- In 3.14.3 and 3.12.9, Discord always fires at the `NORMAL` level with no selector

**Per-run scrape summary** *(all versions)*

After each completed scrape run, a summary is automatically posted to your Discord webhook showing what was downloaded in **that run** alongside the cumulative totals from the database:

```
--- Scrape Results ---
[creator_username] 12 new this run [8 videos, 0 audios, 4 photos] | 12/198 total in DB
```

- Shows each creator's name, new files downloaded this run with type breakdown, and total downloaded vs total in DB
- Per-run counts reset to zero at the start of each run — if nothing new was downloaded, the summary shows `0 new this run`
- Works with any Discord level (`LOW` or `NORMAL`)
- Requires a webhook URL configured in Configuration → General

**@here Discord ping** *(daemon mode, all versions)*

When using daemon mode, an optional **@here Discord mention when new content is found** checkbox is available in the Daemon Mode section:

- When enabled, `@here` is prepended to the scrape summary message — notifying your whole Discord server
- The ping is sent **only when new content was downloaded** in that run; runs that find nothing new send the summary quietly with no mention
- The checkbox is only active when daemon mode is enabled
- The preference is saved to `gui_settings.json` and persists across sessions

<img src="https://github.com/user-attachments/assets/85312a79-061b-4ee6-8520-1439ebd39cc6" width="600" alt="Discord @here">

---

### Download integrity & security *(3.14.7)*

- **DRM Duration Match %** (default 98%) — reject empty/tiny muxes and files whose playback duration is too short vs expected; failed checks delete the bad file for retry
- Download stall watchdog and stricter `.part` finalize (Content-Range aware resume)
- Media / DRM / license URLs must use allowlisted hosts (`onlyfans.com`, `cloudfront.net`; extend via Configuration → Advanced → **Media Host Suffixes** or `OFSC_MEDIA_HOST_SUFFIXES`)
- Download paths confined under Save Location (and temp root for `.part` files)
- Remote Key Mode (`cdrm` / `cdrm2` / `keydb`) warnings; new installs default to **manual** CDM; remote helpers never send session cookies
- About / sidebar version check against PyPI; first-run welcome for `--gui` and plugins
- **API resilience** (Configuration → Advanced) — **API Path**, **Manual Dynamic Rules**, **Dynamic Rules URL**, **API Endpoint Overrides**, and **Media Host Suffixes** so many OnlyFans signing/path/CDN breaks can be handled from config without a code patch (see [Configuration](#configuration))

---

## Plugin system *(all versions)*

> **⚠️ Experimental:** Plugins are experimental and a work in progress. They are **not guaranteed to work 100%** in every environment. Use them at your own risk and report issues you encounter. The Plugins page and host hooks are part of the GUI patch; optional plugin packages (e.g. Trial Link Scanner) are separate installs.

OF-Scraper GUI includes an extensible plugin system. Plugins are placed in your ofscraper config directory and are loaded automatically on startup.

**Plugin directory:**
- **Windows:** `C:\Users\<YourUser>\.config\ofscraper\plugins\`
- **Linux:** `/home/<YourUser>/.config/ofscraper/plugins/`

### Plugins page *(3.14.7)*

<table>
  <tr>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/37aa3377-85a4-47d8-85bc-9bb33628863f" width="100%" alt="Plugin Page">
    </td>
    <td align="center">
      <img src="https://github.com/user-attachments/assets/e491ed59-cd6b-46f9-96d4-b16ad3b3d6a9" width="100%" alt="Plugin Loaded">
    </td>
  </tr>
</table>

- Left-nav **Plugins** page lists installed plugins (name, version, Loaded / Disabled / Not loaded)
- **Enable / Disable** writes `plugin_enabled` in the plugin’s `main.py`
- **Load now** / **Unload now** — bring a plugin into (or out of) the current GUI session without restarting (runs `on_ui_setup` / `on_ui_teardown`)
- Open plugins folder / selected plugin folder; Refresh after copying a new plugin in

Each plugin is a subfolder containing at minimum a `main.py` with a `Plugin` class that inherits from `BasePlugin`. Plugins can hook into the following events:

| Hook | When it fires |
| :--- | :--- |
| `on_load()` | When the plugin is first loaded at startup |
| `on_ui_setup(main_window)` | After the GUI window is built *(GUI mode only)* |
| `on_ui_teardown(main_window)` | Before unload / **Unload now** — remove pages/nav *(3.14.7)* |
| `on_item_downloaded(item_data, file_path)` | Every time a file is saved to disk |
| `on_scrape_start(config, models)` | When a new scrape begins |
| `on_posts_collected(posts, model_username)` | After each batch of posts/messages is collected for a model |
| `on_scrape_complete(stats)` | When the scrape finishes |
| `on_unload()` | When the plugin is unloaded |

Plugins that declare a `requirements.txt` will trigger a one-click dependency install dialog if their packages are missing.

For full documentation on writing plugins see [`ofscraper/plugins/PLUGIN_DEVELOPMENT.md`](OF-Scraper-3.14.7/ofscraper/plugins/PLUGIN_DEVELOPMENT.md).

### Available plugins

Example plugins are included (see below). They are typically **disabled by default** — enable via `plugin_enabled = 1` in each plugin’s `main.py`, or use the **Plugins** page *(3.14.7)*.

#### JoyCaption Tagger (`joycaption_tagger`) *(all versions)*

Sends downloaded images to a [JoyCaption Alpha Two](https://huggingface.co/fancyfeast/llama-joycaption-alpha-two-hf-llava) node running inside ComfyUI (local or Docker) and stores the captions in a local database. JoyCaption Alpha Two natively supports adult/explicit content captioning, making it well-suited for OF-Scraper content. Caption style and length are configurable per the plugin settings panel. A built-in image gallery lets you browse and search tagged images by caption content, browse by model (click a model to see all their tagged images), and open any image in your system's external image viewer. The gallery has no cap on the number of images displayed, and all tagging activity is logged so you can see exactly what the plugin is doing during folder scans.

> **Performance note:** JoyCaption sends each image to ComfyUI for AI inference, which is compute-intensive. Captioning a single image can take anywhere from a few seconds to several minutes depending on your hardware (CPU vs. GPU, available RAM, etc.).
>
> When **Auto-tag images on download** is enabled, every downloaded image is sent to ComfyUI during the scrape — this can significantly slow down large scraping sessions. For better performance, consider leaving auto-tagging **disabled** and using the **Scan Folder** tool from the plugin page to tag images after your scrape finishes.

**Screenshots**

<table>
<tr>
<td align="center"><img src="https://github.com/user-attachments/assets/c9230326-0161-4728-a17c-a87bf0b3a300" width="380"><br><em>Missing dependencies prompt</em></td>
<td align="center"><img src="https://github.com/user-attachments/assets/c8eff70c-c70b-4784-bb36-7091a8d9baf9" width="380"><br><em>Dependency install dialog</em></td>
</tr>
<tr>
<td align="center"><img src="https://github.com/user-attachments/assets/f1451662-2409-48ab-ae6c-a34502be3b41" width="380"><br><em>Plugin page — no images tagged yet</em></td>
<td align="center"><img src="https://github.com/user-attachments/assets/2ef20d8f-da26-493e-b02f-8d3337cf5753" width="380"><br><em>Scanning folder</em></td>
</tr>
<tr>
<td align="center"><img src="https://github.com/user-attachments/assets/531b93ec-953b-4770-a91e-380ee43947b4" width="380"><br><em>Image gallery with captions</em></td>
<td align="center"><img src="https://github.com/user-attachments/assets/b6063b08-d4ed-43f8-8322-1f47e5631ba4" width="380"><br><em>Searching by caption content</em></td>
</tr>
<tr>
<td align="center"><!-- Screenshot placeholder: Gallery browse-by-model view showing model list --><br><em>Browse by model</em></td>
<td align="center"><!-- Screenshot placeholder: Image opened in external image viewer --><br><em>Open in external image viewer</em></td>
</tr>
<tr>
<td align="center"><img src="https://github.com/user-attachments/assets/18c7f8ee-ef12-45b0-8308-282177518162" width="380"><br><em>Settings dialog</em></td>
<td align="center"><img src="https://github.com/user-attachments/assets/cc174331-628e-4cf2-b697-91bfd7f9ecc8" width="380"><br><em>Full image view with caption/tags</em></td>
</tr>
</table>

**System requirements**

| | Minimum | Recommended |
| :--- | :--- | :--- |
| RAM | 8 GB | 16 GB+ |
| Disk | 20 GB free | 30 GB+ free |
| GPU | Not required | NVIDIA GPU with 8 GB+ VRAM for faster inference |
| OS | Any Docker host | Linux preferred |

> The JoyCaption model (`llama-joycaption-alpha-two-hf-llava`) is approximately **15 GB**. The included Docker setup runs in **CPU-only mode** — captioning will be noticeably slower than GPU inference but works on any machine with enough RAM.

**Setup with Docker (recommended)**

A ready-made Docker Compose setup is included in `docker/comfyui-joycaption/`.

1. **Download the model weights** (~15 GB, resumes if interrupted):
   ```bash
   cd docker/comfyui-joycaption
   pip install huggingface_hub
   python download_models.py
   ```

2. **Build and start the container:**
   ```bash
   docker compose build
   docker compose up -d
   ```

3. **Verify ComfyUI is running** by opening `http://localhost:8188` in your browser.

4. **Install the JoyCaption custom node** inside ComfyUI:
   - Open ComfyUI Manager (top menu → Manager)
   - Search for **JoyCaption** and install the node
   - Restart the container after installing

5. **Configure the plugin** by opening the JoyCaption Tagger settings in the OF-Scraper GUI and setting the ComfyUI URL to `http://localhost:8188`. If ComfyUI is running on a different machine on your network, replace `localhost` with that machine's local IP address (e.g. `http://192.168.1.50:8188`).

**Setup without Docker**

If you already have ComfyUI running locally, install the JoyCaption custom node via ComfyUI Manager, ensure the `llama-joycaption-alpha-two-hf-llava` model is in your ComfyUI `models/LLM/` folder, then point the plugin at your existing ComfyUI URL.

**Plugin settings**

| Setting | Description |
| :--- | :--- |
| ComfyUI URL | URL of your ComfyUI server (default: `http://localhost:8188`). Use `localhost` if ComfyUI is on the same machine, or replace it with the local IP address of another device on your network (e.g. `http://192.168.1.50:8188`). Click **Test** to verify the connection. |
| Caption Type | Style of caption: Descriptive, Stable Diffusion Prompt, Danbooru tag list, e621 tags, etc. |
| Caption Length | `any`, `very short`, `short`, `medium-length`, `long`, `very long` |
| Extra Options | Free-text modifiers appended to the caption prompt (e.g. `Do not include low quality, Do not use vague language`) |
| Subject Name | Optional name hint passed to the model — useful if you want captions to reference the creator or subject by name |
| Timeout | Seconds to wait for a ComfyUI response before giving up (default: 600) |
| Max stored parts | Maximum number of tag/caption parts stored per image (default: 20) |
| Auto-tag images | Automatically caption each image as it is downloaded. See performance note above. |
| Enable Smart Folders | When enabled, copies each tagged image into a named subfolder based on its primary tag (see below) |
| Smart Folder Path | Root folder where Smart Folder subfolders are created (default: `Smart_Tags/` in the plugin directory) |
| Workflow | ComfyUI workflow JSON file to use (default: `joycaption.json`) — must be in the plugin's `workflows/` folder |

**Smart Folders**

When **Enable Smart Folders** is turned on, every image that gets tagged is automatically **copied** (not moved — your originals are untouched) into a subfolder under the Smart Folder Path, named after its primary tag:

- For **tag-list caption types** (Danbooru, e621, Rule34, etc.): the top-ranked tag becomes the folder name
- For **descriptive caption types**: the first comma-separated phrase from the caption becomes the folder name

This builds a browsable folder structure organized by image content automatically as you tag images. For example, an image captioned `"woman, outdoor, sunset, ..."` would be copied to `Smart_Tags/woman/filename.jpg`.

> Smart Folders only copies images that have been tagged. Images that fail tagging or are skipped will not appear in the Smart Folders output.

---

#### LLM Assistant (`llm_assistant`) *(all versions)*

Adds a **🤖 AI Assistant** chat panel to the sidebar. Type plain English commands — the assistant translates them into GUI actions such as setting usernames, selecting content areas, and starting downloads.

*(3.14.7)* Compact **Ask AI** bars on Action / Areas / Table pages; Areas state mirror on the AI tab; if you Ask before the model is loaded, the plugin opens the AI page, starts Load Model, and queues your prompt.

**Screenshots**

<table>
<tr>
<td align="center"><img src="https://github.com/user-attachments/assets/f465046f-d6a8-4282-9839-9e459a2e8e1f" width="380"><br><em>AI model selection (first launch)</em></td>
<td align="center"><img src="https://github.com/user-attachments/assets/996a3d4d-be3a-478e-85fd-e61242f62409" width="380"><br><em>Dependency install dialog</em></td>
</tr>
<tr>
<td align="center" colspan="2"><img src="https://github.com/user-attachments/assets/0a9df78b-054e-4b6b-9e0b-61d6d3f4af5d" width="500"><br><em>AI Assistant chat panel</em></td>
</tr>
</table>

**System requirements**

| | Minimum | Recommended |
| :--- | :--- | :--- |
| RAM | 1 GB free | 2 GB+ free |
| Disk | 600 MB free | 2 GB free (for larger model) |
| GPU | Not required | Not required — CPU inference only |
| Internet | Required once (model download) | — |

**Available models**

Three GGUF models are available to choose from at first launch. All run on CPU with no GPU required:

| Model | Size | RAM needed | Notes |
| :--- | :--- | :--- | :--- |
| Qwen2.5 0.5B Q8_0 | ~530 MB | ~530 MB | Fastest, lowest accuracy |
| Qwen2.5 1.5B Q4_K_M | ~1.1 GB | ~1.1 GB | **Recommended** — good balance |
| Qwen2.5 3B Q4_K_M | ~2.0 GB | ~2.0 GB | Best accuracy, needs 2+ GB free RAM |

**Setup**

The plugin handles its own setup on first enable:

1. Set `plugin_enabled = 1` in `llm_assistant/main.py` and restart the GUI.
2. A **model selection dialog** appears automatically — pick the model that fits your available RAM.
3. The plugin checks for and installs missing dependencies (`llama-cpp-python`, `huggingface-hub`) with a one-click dialog.
4. The selected model is downloaded from HuggingFace (~530 MB – 2 GB depending on choice).
5. On subsequent launches the model loads automatically in the background.

> **Manual dependency install** (if the GUI dialog fails):
> ```bash
> # pip
> pip install llama-cpp-python huggingface-hub
> # pipx
> pipx inject ofscraper llama-cpp-python huggingface-hub
> ```

--- 

#### Live Stream Monitor (`live_stream_monitor`) *(all versions)*

Adds a **📺 Live Monitor** sidebar page that polls your subscriptions, detects when a creator goes live, and captures the stream with Playwright Chromium into `{username}/Live_Streams/`.

This is **separate** from the Areas checkbox **Streams** (API VODs / stream posts in your normal scrape folders).

**Highlights *(3.14.7 plugin v1.3.x)***
- Privacy mode masks usernames/paths in the plugin UI and console
- Windows capture paths use normal backslash display
- Injects `sess` / `auth_id` / `auth_uid*` from Authentication; Playwright login only when a capture starts and no valid session/profile exists
- Chromium install prompt when needed; Stop / Unload while a capture is running
- Subscriptions table expands to fill the page (resizable columns); terminal sits full-width at the bottom
- **Capture selected** plus **Stop selected** / **Stop all** / per-row **Stop** (poller can keep running)
- Capture cooldown after stop/fail so Auto-Capture does not immediately re-spawn the same creator
- **Show diagnostics** (off by default) reveals optional tools:
  - *Diagnostics probe only* / **Probe selected…** — join live ~45s, redacted HLS/WebRTC/API evidence under `live_probe_reports/` (no WebM)
  - **Fetch live API dump…** — redacted `/streams/active` + `/streams/active/url` JSON under `live_api_dumps/`
- Native Agora Server SDK joins are **not** supported (OF rejects them); Playwright is the capture path on Windows and Linux

**Setup**
1. Copy `live_stream_monitor` into your plugins folder (or use the copy shipped with the 3.14.7 patch under `ofscraper/plugins/`)
2. Enable via Plugins page or `plugin_enabled = 1`, then Load now / restart
3. Install Chromium from the Live Monitor page if prompted
4. Enable Auto-Capture — polling uses normal GUI auth; Chromium opens only when someone goes live

---

#### Trial Link Scanner (`trial_link_scanner`) *(all versions)*

Automatically scans every direct message collected during a scrape for OnlyFans trial/free-trial links (`https://onlyfans.com/<creator>/trial/<token>`), logs all matches to a daily log file, and optionally posts them to your Discord webhook — including any images attached to the message.

**Screenshots**

<img src="https://github.com/user-attachments/assets/f2e08ad4-a335-47ea-8275-13c34c64d01d" width="600" alt="Trial Link Scanner">

**How it works**

1. During scraping, every direct message collected for each model is passed to the plugin via the `on_posts_collected` hook
2. The plugin searches the raw HTML message text (not the stripped display text) for trial link URLs using a regex — this catches the full URL even when OnlyFans truncates it in the UI
3. Each unique link found is written to a daily log file (`logs/trial_links_YYYY-MM-DD.log`) inside the plugin directory
4. If Discord is enabled and a webhook URL is configured in OF-Scraper's Configuration → General, a notification is sent immediately (or held until the scrape ends in summary mode)
5. Images attached to the message are downloaded from OnlyFans' CDN locally (using the IP-restricted signed URL) and uploaded directly to Discord as file attachments, so they display permanently in Discord without relying on OnlyFans' CDN

**Setup**

1. Copy the `trial_link_scanner` folder to your plugin directory:
   - **Windows:** `C:\Users\<YourUser>\.config\ofscraper\plugins\trial_link_scanner\`
   - **Linux/macOS:** `~/.config/ofscraper/plugins/trial_link_scanner/`
2. Open `main.py` and set `plugin_enabled = 1` at the top (or leave it at `1` if already set)
3. Restart the GUI — a **Trial Links** button will appear in the sidebar
4. Click **Trial Links** in the sidebar and click **Enable** to activate the plugin
5. Configure your preferred Mode, Timing, and Discord setting
6. Ensure a Discord webhook URL is set in **Configuration → General**

**Plugin settings**

| Setting | Options | Description |
| :--- | :--- | :--- |
| Mode | `link` / `full` | **link** — send only the trial URL · **full** — send the trial URL plus the full message text |
| Timing | `immediate` / `summary` | **immediate** — one Discord message per link as it is found · **summary** — one combined message at the end of the scrape |
| Discord | `enabled` / `disabled` | Whether to send matches to your Discord webhook. Links are always written to the log file regardless |

**Recent Finds log**

The **Trial Links** sidebar page shows all trial links found today (from the current day's log file). The log displays:

- The date and time the link was found
- The model username who sent the message
- The trial link URL
- The full message text (in `full` mode)

Log files are stored at `<plugin_dir>/logs/trial_links_YYYY-MM-DD.log` and accumulate across scrape sessions for the same day.

**Discord notification format**

Each Discord message includes:

- **Header** — `Trial link found — modelname · YYYY-MM-DD HH:MM` (the original message date, not the scan time)
- **Trial link URL** — clickable link to the trial page
- **Message text** (in `full` mode) — the message body with HTML stripped and entities decoded
- **Attached images** — up to 4 thumbnail images from the message, uploaded directly to Discord

**Notes**

- The plugin reads raw message data directly — it does not depend on the **Include Post Text** scrape setting
- Trial links are deduplicated per session: the same link from the same model is only reported once per scrape run, even if it appears in multiple messages
- OnlyFans CDN image URLs are IP-restricted signed URLs. The plugin downloads images locally first (from your machine's authorized IP) and uploads them directly to Discord, so they remain visible permanently without requiring OF CDN access
- Discord error details (HTTP status codes, response bodies) are logged to `logs/discord_errors.log` if anything goes wrong

---

## Docker

A Docker setup is included for running the GUI in a headless environment, accessible from any browser or VNC client — no display required on the host machine.

> **Notes**
> - DRM key generation is **not supported in Docker** — generate keys on a desktop host and mount them (see below).
> - Embedded browser login is limited in Docker; prefer Import Cookies / System Browser on a desktop, or paste credentials.
> - FFmpeg is installed **inside the image**. Do **not** bind-mount a host `/usr/bin/ffmpeg` — host binaries often fail against container libraries and leave DRM downloads stuck as `.part` files.

### Running the GUI in Docker

```bash
# Build the image
docker compose build ofscraper-gui

# Start the container
docker compose up ofscraper-gui
```

Once running, open **[http://localhost:6699/](http://localhost:6699/)** (or `http://<host>:6699/`) in your browser for noVNC. You can also connect with any VNC client on port `5900`.

<!-- Screenshot placeholder: noVNC browser view showing the OF-Scraper GUI -->

The `GUI_PATCH_VERSION` build argument and `GUI_ARGS` environment variable in `docker-compose.yml` control which version is used and whether a scrape starts automatically:

```yaml
# docker-compose.yml (key sections)
build:
  args:
    GUI_PATCH_VERSION: "3.14.7"   # which patch to apply at build time
environment:
  - GUI_ARGS=                     # leave blank to just open the GUI
  - NOVNC_PORT=6699               # noVNC (websockify) listen port
```

### Auto-starting a scrape on container startup

Set `GUI_ARGS` to pass any `ofscraper --gui` arguments. The container will open the GUI and immediately begin scraping with those options — no manual interaction required:

```yaml
environment:
  - GUI_ARGS=--daemon 120 --username ALL --sub-status active --posts all --discord low
```

This is equivalent to running `ofscraper --gui --daemon 120 --username ALL ...` on the command line. The GUI wizard pages are skipped and the scrape starts automatically. *(3.14.7)* Unattended auto-start also skips scrape-confirm / disk / remote-key dialogs.

### Volumes, CDM keys, and crash logs

Map host config and media so settings, auth, databases, crash logs, and downloads persist:

```yaml
volumes:
  # Config, auth.json, SQLite DBs, gui_crash_logs/, device/ (CDM keys)
  - /home/you/.config/ofscraper:/root/.config/ofscraper
  - /home/you/Photos/OnlyFans:/home/you/Photos/OnlyFans
  # Prefer the image FFmpeg — do not bind-mount host ffmpeg
```

| Path under config | Purpose |
|---|---|
| `gui_crash_logs/` | Breadcrumbs + faulthandler dumps (same as desktop) |
| `device/` | Typical location for `client_id.bin` / `private_key.pem` after desktop keygen |

### Selecting the patch version at build time

Change `GUI_PATCH_VERSION` in `docker-compose.yml` (or pass it as a build arg) to build a container for a different supported version:

```bash
docker compose build --build-arg GUI_PATCH_VERSION=3.14.3 ofscraper-gui
```

Available versions match the patch scripts: `3.12.9`, `3.14.3`, `3.14.5`, `3.14.7`.

---

## Supported versions

| Patch script | OF-Scraper version |
|---|---|
| `patch_ofscraper_3.12.9_gui.py` | 3.12.9 |
| `patch_ofscraper_3.14.3_gui.py` | 3.14.3 |
| `patch_ofscraper_3.14.5_gui.py` | 3.14.5 |
| `patch_ofscraper_3.14.7_gui.py` | 3.14.7 |

### Feature availability by version

| Feature | 3.12.9 | 3.14.3 | 3.14.5 | 3.14.7 |
|---|:---:|:---:|:---:|:---:|
| Core scraper workflow (download, like/unlike) | ✅ | ✅ | ✅ | ✅ |
| Authentication, Configuration, Profiles, Merge DBs | ✅ | ✅ | ✅ | ✅ |
| Daemon mode | ✅ | ✅ | ✅ | ✅ |
| Discord webhook toggle | ✅ | ✅ | ✅ | ✅ |
| DRM Key Creation | ✅ | ✅ | ✅ | ✅ |
| Table page (filters, sort, cart, avatars) | ✅ | ✅ | ✅ | ✅ |
| CLI auto-start (`--username`, `-a`, `-o`) | ✅ | ✅ | ✅ | ✅ |
| Check modes (Post / Message / Paid / Story Check) | ❌ | ✅ | ✅ | ✅ |
| Include Post Text | ❌ | ✅ | ✅ | ✅ |
| User Lists (`--ul`) + Reload Models | ❌ | ❌ | ✅ | ✅ |
| Discord notification level selector (LOW / NORMAL) | ❌ | ❌ | ✅ | ✅ |
| Per-run Discord scrape summary | ❌ | ❌ | ✅ | ✅ |
| Scrape by URL / Post ID | ❌ | ❌ | ✅ | ✅ |
| CLI auto-start with `--ul` | ❌ | ❌ | ✅ | ✅ |
| Video quality selector (`-q` / `--quality`) | ❌ | ❌ | ❌ | ✅ |
| Login in Browser (embedded auth) | ❌ | ❌ | ❌ | ✅ |
| Confirm scrape (pre-start review + ETA) | ❌ | ❌ | ❌ | ✅ |
| Privacy / demo mode | ❌ | ❌ | ❌ | ✅ |
| Status strip + Auth/Config/Key health chips | ❌ | ❌ | ❌ | ✅ |
| Plugins page (Load / Unload now) | ❌ | ❌ | ❌ | ✅ |
| History / filter presets / sticky columns / CSV | ❌ | ❌ | ❌ | ✅ |
| Allow duplicates + Messages/Purchased keep-both | ❌ | ❌ | ❌ | ✅ |
| Windows path backslashes in Config | ❌ | ❌ | ❌ | ✅ |
| Scripts tab + preferred file extensions | ❌ | ❌ | ❌ | ✅ |
| Crash diagnostics (`gui_crash_logs/`) | ❌ | ❌ | ❌ | ✅ |
| About dialog (sidebar `v…`) + global text size | ❌ | ❌ | ❌ | ✅ |
| Duplicate column in content table | ❌ | ❌ | ❌ | ✅ |
| Save/Reset Settings confirmation dialogs | ❌ | ❌ | ❌ | ✅ |
| TUI-style scrape summary with global totals | ❌ | ❌ | ❌ | ✅ |
| Collapsible filter sidebar | ❌ | ❌ | ❌ | ✅ |
| Non-blocking startup dependency popup | ✅ | ✅ | ✅ | ✅ |
| Plugin system (JoyCaption, LLM, Live Monitor, Trial Links) | ✅ | ✅ | ✅ | ✅ |

## How it detects your installation

The script automatically detects how OF-Scraper was installed by checking (in order):

1. **uv tool directories** — looks for ofscraper in `~/.local/share/uv/tools/` (Linux) or `%USERPROFILE%\AppData\Local\uv\tools\` (Windows)
2. **pipx virtual environments** — checks `~/.local/share/pipx/venvs/ofscraper/` (Linux) or `~\pipx\venvs\ofscraper\` (Windows), including the `$PIPX_HOME` environment variable
3. **Executable path** — runs `which ofscraper` / `where ofscraper` and infers the method from the path
4. **Python import** — attempts `import ofscraper` and locates the package via `__path__` (standard pip/venv installs)

### Broken installation detection

The patch script also checks for broken ofscraper installations before patching, for example when a previous pip install was interrupted mid-way and left behind a corrupt `~fscraper` artifact in site-packages. When a broken installation is detected, the script automatically runs `pip install ofscraper==<version> --force-reinstall` to repair it before applying the GUI patch.

## If OF-Scraper is not detected

If the script cannot find an existing installation, it presents an interactive menu:

```
ofscraper was not detected on this system.

Choose an option:
  1) Install ofscraper with pip
  2) Install ofscraper with pipx
  3) Install ofscraper with uv
  4) Specify install path manually (ofscraper is already installed)
  5) Exit

Enter choice (1-5):
```

- **Options 1-3** install OF-Scraper using your chosen package manager, then continue with patching
- **Option 4** lets you provide the path to your ofscraper package directory manually (e.g. `/path/to/site-packages/ofscraper`). The script validates the path contains `__main__.py` before proceeding
- You can also use `--target /path/to/ofscraper` to skip detection entirely

## OF-Scraper Tools

A standalone maintenance and removal tool (`ofscraper_tools.py`) is included. It detects your install method automatically (uv / pipx / pip) and presents two groups of options.

**Run it with:**

```bash
python ofscraper_tools.py
```

### Uninstall options

1. **Just uninstall ofscraper** — removes the package only; config and downloaded content are kept
2. **Just remove the GUI patch** — uninstalls the patched version and reinstalls stock ofscraper from PyPI; your config is kept
3. **Remove ofscraper + all config files** — uninstalls ofscraper and deletes `~/.config/ofscraper/` (includes settings, auth, logs, and databases — everything ofscraper stores outside your download folder)
4. **Purge everything** — uninstalls ofscraper, deletes config, and deletes your downloaded content. The download path is read from `file_options.save_location` in `config.json` **before** the config is deleted, so the correct path is always used regardless of where you saved content

### Data management options *(ofscraper stays installed)*

5. **Delete model DB(s) only** — lists every individual model database found across all profiles, showing the creator's username (read directly from the DB) and their numeric ID. You can delete one, several (comma-separated), or all. Only the selected model's `.data/<id>/` folder is removed, leaving all other models and your downloaded files untouched. Resetting a model's DB causes ofscraper to treat all of that creator's content as new on the next run
6. **Delete downloaded content only** — lists every model folder found inside your download root (`file_options.save_location` in `config.json`), along with each folder's total size on disk. You can delete one, several (comma-separated), or all. Only the selected folders are removed; config and model DBs are not affected. Requires two confirmations. Prompts for the download path if it cannot be read from `config.json`
7. **Delete SQL cache only** — deletes the `cache_sql/` folder(s) under each profile (`~/.config/ofscraper/<profile>/cache_sql/`). The cache holds API responses that speed up repeated runs; clearing it forces ofscraper to re-fetch everything from the API on the next run. Config, model DBs, and downloaded files are not affected

All destructive options require explicit confirmation before proceeding. Options 4, 5, and 6 require two confirmations.

> **Note:** `uninstall_ofscraper.py` (the previous name for this script) is superseded by `ofscraper_tools.py`.

---

## Notes

- A backup of all modified files is saved to your system temp directory before patching
- The `--restore` flag can undo the patch using any previous backup
- PyQt6 is installed automatically via the same package manager used for OF-Scraper (pip/pipx inject/uv)
- This was created with the help of AI and has been tested to the best of my ability. I take no responsibility for any damage or loss of data. Backups are recommended.

## Disclaimer

1. This tool is not affiliated, associated, or partnered with OnlyFans in any way. We are not authorized, endorsed, or sponsored by OnlyFans. All OnlyFans trademarks remain the property of Fenix International Limited.
2. This is a theoretical program only and is for educational purposes. If you choose to use it then it may or may not work. You solely accept full responsibility and indemnify the creator, hosts, contributors and all other involved persons from any and all responsibility.

