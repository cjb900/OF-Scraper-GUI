# OF-Scraper GUI Help / README

This is an in-app guide to what each GUI page/section does and how to use it.

Tip: the small **(?)** buttons next to sections will jump you to the matching section in this README.

---

## Table of contents

- [Getting started](#getting-started)
  - [Launching the GUI (`--gui`)](#getting-started-launch)
  - [First-time checklist](#getting-started-checklist)
  - [GUI patch](#getting-started-patch)
- [GUI patch highlights](#gui-patch-highlights)
- [Plugins](#plugins-root)
- [Left navigation](#nav-left)
  - [About & text size](#about-text-size)
- [Scraper workflow](#scraper-workflow)
  - [Select Action](#action-select)
    - [User Lists](#action-user-lists)
- [Select Content Areas & Filters](#sca-root)
  - [Content Areas](#sca-content-areas)
  - [Media Types to Download](#sca-media-types)
  - [Additional Options](#sca-additional-options)
    - [Scrape entire paid page](#sca-scrape-paid)
    - [Scrape labels](#sca-scrape-labels)
    - [Include Post Text](#sca-include-post-text)
    - [Name text files from post text](#sca-name-text-from-post)
    - [Send updates to Discord](#sca-discord-updates)
    - [Discord notification level](#sca-discord-level)
  - [Advanced Scrape Options](#sca-advanced-options)
    - [Allow duplicates](#sca-allow-dupes)
    - [Also keep Messages + Purchased copies](#sca-keep-msg-purchased-dupes)
    - [Rescrape everything](#sca-rescrape-all)
    - [Delete model DB](#sca-delete-db)
    - [Delete downloaded files](#sca-delete-downloads)
    - [Video quality](#sca-quality)
  - [Daemon Mode](#sca-daemon-mode)
    - [Enable daemon mode](#sca-daemon-enable)
    - [Interval](#sca-daemon-interval)
    - [System notification when scraping starts](#sca-daemon-notify)
    - [Sound alert when scraping starts](#sca-daemon-sound)
    - [@here Discord mention when new content is found](#sca-daemon-discord-ping)
  - [Filters (embedded)](#sca-filters)
  - [Settings persistence](#sca-settings-persistence)
    - [Save Settings](#sca-save-settings)
    - [Reset Settings](#sca-reset-settings)
- [Select Models](#models-root)
  - [Reload Models](#models-reload)
  - [Model Filters (right sidebar)](#models-filters-root)
    - [Subscription Type](#models-filters-subscription)
    - [Flags](#models-filters-flags)
    - [Price Range](#models-filters-price)
    - [Sort](#models-filters-sort)
- [Configuration (config.json)](#config-root)
  - [General](#config-general)
  - [File Options](#config-file-options)
  - [Download](#config-download)
  - [Scripts](#config-scripts)
  - [Performance](#config-performance)
  - [Content](#config-content)
  - [CDM](#config-cdm)
  - [Advanced](#config-advanced)
  - [Response Type Overrides](#config-response-type)
- [Table / Scraping page](#table-root)
  - [Toolbar buttons](#table-toolbar)
  - [Progress + logs](#table-progress)
- [Check Mode](#check-mode-root)
  - [Which mode to use](#check-mode-which)
  - [Message filter (Message Check only)](#check-mode-msg-filter)
  - [The check table](#check-mode-table)
  - [Locked content](#check-mode-locked)
  - [Downloading from check mode](#check-mode-download)
- [Filters (Table page + embedded)](#filters-root)
  - [Text Search](#filters-text-search)
  - [Media Type](#filters-media-type)
  - [Response Type](#filters-response-type)
  - [Status (Downloaded / Unlocked)](#filters-status)
  - [Post Date Range](#filters-date-range)
  - [Duration (Length)](#filters-duration)
  - [Price Range](#filters-price)
  - [ID Filters](#filters-id)
  - [Username](#filters-username)
- [Table columns](#table-columns)
- [Scraping by Post URL / ID](#manual-url-scrape)
- [DRM Key Creation](#drm-key-creation)
- [Merge DBs](#merge-dbs)
- [Troubleshooting notes](#troubleshooting)
  - [GUI crash / hang diagnostics](#troubleshooting-crash)
  - [Docker notes](#troubleshooting-docker)
- [Authentication](#auth-root)
  - [Credentials (manual entry)](#auth-credentials)
  - [Import Cookies](#auth-import-cookies)
  - [Login in Browser (overview)](#auth-login-browser)
  - [Login in System Browser](#auth-login-system-browser)
  - [Login in App Browser](#auth-login-app-browser)
- [Auth Issues](#auth-issues)

---

<a id="getting-started"></a>
## Getting started

Quick onboarding for the graphical UI. The same app still has a terminal UI; this section is about the window you are reading Help in.

<a id="getting-started-launch"></a>
### Launching the GUI (`--gui`)

From a terminal where `ofscraper` is installed:

```
ofscraper --gui
```

Notes:

- Without `--gui`, OF-Scraper starts the **terminal** (TUI) prompts instead of this window.
- You can still pass normal scrape flags with `--gui` (action, usernames, areas, daemon, etc.). When enough args are present, the GUI can **auto-start** the scrape without clicking through the wizard. Unattended CLI / Docker `GUI_ARGS` also skip interactive confirm dialogs.
- Click the sidebar version (`v…`) any time for **About** (app version, GUI patch id, FFmpeg, update check, and **Text size**).
- The first-run **Welcome** tip can be reopened anytime with **Help / README → Show Welcome** (toolbar button next to About).
- Hard crashes write diagnostics under your config home → `gui_crash_logs/` (see [Troubleshooting](#troubleshooting-crash)).

<a id="getting-started-checklist"></a>
### First-time checklist

1. **Authentication** — add cookies / use **Login in App Browser…** or **Login in System Browser…**, then **Save**.
2. **Configuration** — set **Save Location**, **FFmpeg**, and **manual** CDM key paths (default Key Mode is `manual`; use DRM Key Creation if you need keys).
3. **Scraper** — Select Action → Content Areas → Models → **Start Scraping**.
4. Use **?** buttons and this Help page when a control is unclear.
5. Optional: install **plugins** (next section) for extra sidebar pages / automation.
6. Optional: open **About** (`v…` in the sidebar) and raise **Text size** if the UI feels small on a high-DPI display.

<a id="getting-started-patch"></a>
### GUI patch

This GUI is shipped as a **patch** applied into your OF-Scraper install (for example `patch_ofscraper_3.14.7_gui.py`). After applying a new patch and restarting:

- About → **GUI patch** shows the current patch id (e.g. `…_v365`).
- Help / README text and new UI features come from that patch.

If the window does not appear, confirm you launched with `--gui` and that the patch was applied to the same environment you are running.

---

<a id="gui-patch-highlights"></a>
## GUI patch highlights

Quick scan of what this GUI patch adds on top of stock OF-Scraper. Details live in the linked sections.

**About & display**
- Sidebar **`v…`** → [About](#about-text-size) (versions, FFmpeg, PyPI update check)
- Global **Text size** (**A−** / **A+** / 12–20 px / **Reset**) — scales the whole GUI; also on this Help toolbar — [About & text size](#about-text-size)

**Safety & auth**
- Cookie allowlist + hardened `auth.json` permissions — [Authentication](#auth-login-browser)
- Remote Key Mode warnings; default **manual** CDM for new installs — [CDM](#config-cdm)
- Privacy / demo mode for screenshots — [Left navigation](#nav-left)
- Config validation on Save and before scrape (errors block) — [Configuration](#config-root)
- Clearer **Wrong user** / Test Credentials messaging — [Auth Issues](#auth-issues)

**Scrape UX**
- Confirm scrape / cart / disk-space prompts — [Toolbar buttons](#table-toolbar)
- Cooperative cancel (pagination, mid-file, between models) — [Toolbar buttons](#table-toolbar)
- Scrape History with Details / Re-run — [Toolbar buttons](#table-toolbar)
- Daemon last-run + next-run countdown — [Daemon Mode](#sca-daemon-mode) / [Progress + logs](#table-progress)
- Click username to select models — [Select Models](#models-root)

**Table & check mode**
- Filter presets (save / rename / last-used) — [Filters](#filters-root)
- Sticky columns, CSV export, empty-table guidance — [Table / Scraping page](#table-root)
- Multi-select cart (check mode only) — [Check Mode](#check-mode-root)
- Click **Post ID** / **Media ID** to open the OnlyFans post — [Table columns](#table-columns)
- Post-run failure summary dialog — [Downloading from check mode](#check-mode-download)

**Download integrity**
- DRM duration match % + empty-mux rejection — [Download](#config-download)
- Stall timeout, stricter `.part` finalize, Content-Range resume — [Download](#config-download)
- Media host allowlist + Save Location path confinement — [Download](#config-download)

**API resilience** (Configuration → [Advanced](#config-advanced))
- **API Path** — rewrite default `/api2/v2` prefix (`OFSC_API_PATH`)
- **Manual Dynamic Rules** — local signing JSON for Dynamic Mode `manual`
- **Dynamic Rules URL** — custom remote rules URL for Dynamic Mode `generic`
- **API Endpoint Overrides** — per-key URL templates (e.g. `meEP`); `OFSC_API_*` env still wins
- **Media Host Suffixes** — extra CDN hosts for media/DRM/license downloads

**Status strip**
- Auth / Config / Key health chips (hover + click to fix) — [Progress + logs](#table-progress)
- Per-model live success/fail badges — [Progress + logs](#table-progress)

**Plugins**
- Load / unload without restart — [Plugins](#plugins-root)

---

<a id="plugins-root"></a>
## Plugins

Plugins extend OF-Scraper without editing core code (extra sidebar pages, post-download hooks, monitors, etc.).

Use the left-nav **Plugins** page to:
- See installed plugins (name, version, Loaded / Disabled / Not loaded)
- **Load now** — import an enabled-but-unloaded plugin into the current session (runs `on_ui_setup`)
- **Unload now** — deactivate a loaded plugin, run `on_ui_teardown` / `on_unload`, and remove its sidebar page without restarting
- **Enable** / **Disable** a plugin (writes `plugin_enabled` in its `main.py`). After Disable, you can Unload now; after Enable, you can Load now
- **Open plugins folder** or the selected plugin’s folder
- **Refresh** the list after copying a new plugin in

### Where plugins live

Plugins load from a `plugins` folder next to your config home:

- **Windows:** `%USERPROFILE%\.config\ofscraper\plugins\`
- **Linux / macOS:** `~/.config/ofscraper/plugins/`

The folder is created automatically on first launch if it does not exist.

### Installing a plugin

1. Copy the plugin’s folder into `plugins/` (folder name = plugin id).
2. Each plugin needs at least `main.py` (optional `metadata.json`, `requirements.txt`).
3. Restart the GUI (`ofscraper --gui`).
4. If dependencies are missing, OF-Scraper can prompt to install them into the plugin’s local `deps/` folder.

Plugins load in **GUI and CLI** modes. The `on_ui_setup` hook is **GUI-only** (adds pages/buttons).

### Example

Optional plugins (for example **Live Stream Monitor**) ship separately under `example_plugins/` in the project source — they are **not** part of the GUI install patch. To use one, copy its folder into your user `plugins/` directory (`~/.config/ofscraper/plugins/` on Linux) and restart (or Enable + **Load now** on the Plugins page).

**Streams (Areas) vs Live Stream Monitor:** the Areas checkbox **Streams** downloads OnlyFans stream/VOD media into your normal scrape folders. The **Live Stream Monitor** plugin separately captures live broadcasts into `{username}/Live_Streams/` via Playwright. They do not replace each other.

When Live Stream Monitor is loaded, a **Live Monitor** entry appears in the left sidebar (with its own icon). Auto-capture polling uses your normal Authentication cookies; Playwright Chromium only opens when a creator goes live and a capture starts. If a saved browser profile or injected `sess` / `auth_id` / `auth_uid*` already works, you may not need to log in again in Chromium.

**Capture controls (v1.3+):** **Capture selected** starts Playwright for the table selection. **Stop selected** / **Stop all** / the per-row **Stop** button end captures or probes without turning off Auto-Capture. Table columns are resizable; a short cooldown after stop/fail avoids immediate re-spawn.

**Diagnostics (v1.2+, hidden by default in v1.3.1):** check **Show diagnostics** to reveal probe / API-dump tools. *Diagnostics probe only* (with Auto-Capture) or **Probe selected…** joins the live page for ~45 seconds, records interesting network/API traffic and player diagnostics (secrets redacted), and writes `live_probe_reports/probe_<user>_<timestamp>.json` inside the plugin folder (**Open reports…**). **Fetch live API dump…** saves a redacted `/streams/active` + `/streams/active/url` summary under `live_api_dumps/`. Playwright MediaRecorder is the supported capture path on Windows and Linux; native Agora Server SDK joins are not supported against OnlyFans.

For authors, see `ofscraper/plugins/PLUGIN_DEVELOPMENT.md` in the project source (hooks, metadata, logging).

---

<a id="nav-left"></a>
## Left navigation

Each main page has a colored icon next to its label in the sidebar (for example ⚡ Scraper, 🔑 Authentication, ⚙️ Configuration, 🔒 DRM Key Creation, 👥 Profiles, 🔀 Merge DBs, 🧩 Plugins, 📖 Help / README). Plugin pages (such as **Live Monitor** or **AI Assistant**) appear below the built-in items when that plugin is loaded.

- **Scraper**: Main workflow for scraping/downloading/liking.
- **Authentication**: Enter cookies/headers (stored in your profile `auth.json`). Includes **Login in Browser** — an embedded browser that captures credentials automatically on login.
- **Configuration**: Edit `config.json` settings (save location, formats, performance, CDM, etc.).
- **Profiles**: Manage profiles (each profile has separate auth + `.data`).
- **DRM Key Creation**: Automated Widevine L3 key extraction using an Android emulator. Required for scraping DRM-protected content with **Key Mode: manual**.
- **Merge DBs**: Merge `user_data.db` files into a single database.
- **Plugins**: List installed plugins, enable/disable, open the plugins folder. **Load now** / **Unload now** apply without restarting the app.
- **Help / README**: This page (one shared page — `?` buttons jump here instead of opening extra windows). Toolbar: **Jump to…**, **Text size** (**A−** / size / **A+** / **Reset**), **About**, **Show Welcome**, **Additional Help**.

Bottom of the sidebar:

- **Light Mode / Dark Mode**: Theme toggle (saved in `gui_settings.json`). Button chrome matches Verbose / Privacy / version controls.
- **Verbose Log**: DEBUG logging to a dedicated GUI verbose log file.
- **Privacy**: Privacy / demo mode for safe screenshots. When **On**:
  - Auth credential fields are masked (password dots); reveal eye is disabled
  - Save Location, Discord webhook, FFmpeg / CDM paths show `[Hidden for Privacy]`
  - **Select Models** list shows `[Hidden for Privacy]` instead of creator names/prices (search still works)
  - Table **UserName** column shows `[Hidden for Privacy]`
  - **Download failures** dialog Model column and status lines like `Processing …` are masked
  - Console lines get extra cookie/path/webhook/username redaction
  - Avatars on the model list are suppressed while Privacy is on
  - Preference is stored in `gui_settings.json` (`privacy_mode`)
- **Version (`v…`)**: Click to open **About** — see [About & text size](#about-text-size).

<a id="about-text-size"></a>
### About & text size

Click the sidebar version button (e.g. **`v3.14.7`**) or **Help → About** to open **About OF-Scraper**. Opening again focuses the same About window — it does not stack duplicates.

**About shows**

- **App version** — installed OF-Scraper version
- **GUI patch** — applied patch id (include this when reporting issues)
- **Operating system**, **FFmpeg**, and **FFprobe**
- **Updates** — status after **Check for updates** (PyPI, same source as the CLI), plus **Open PyPI** when a newer release is available
- On startup the GUI quietly checks PyPI; if a newer release exists you get a one-time prompt (Open PyPI / Dismiss this version / Later)

**Text size (global GUI scaling)**

Controls are in **About** and on this Help toolbar: **A−**, size dropdown, **A+**, and **Reset**.

| Size | Notes |
|------|--------|
| 12 px | Smaller |
| **13 px** | Default |
| 14 / 16 / 18 / 20 px | Larger |

- Scales the whole app (theme, pages, dialogs, this Help page). Saved as `gui_font_size` in `gui_settings.json` (legacy `help_font_size` migrates automatically).
- **Reset** restores **13** px.
- The sidebar ASCII logo stays at a fixed size and is **not** scaled with text size.
- Like the theme toggle, size changes wait if a model list is loading or a scrape is running.

---

<a id="scraper-workflow"></a>
## Scraper workflow (Scraper →)

<a id="action-select"></a>
### 1) Select Action

- **Download content from a user**: Scrape content and build the table.
- **Like / Unlike**: Perform like/unlike actions (limited to supported areas).
- **Download + Like / Unlike**: Do both.

<a id="action-user-lists"></a>
#### User Lists (sub-option under Download)

When **Download content from a user** is selected, a **User Lists** field appears below it.

- Enter one or more OnlyFans list name(s), comma-separated (e.g. `testing, vip`).
- Only models who are members of those lists will be loaded — the full subscription list is not fetched.
- Leave blank to load all subscribed models (default behavior).
- Equivalent to the `--ul` / `--userlist` CLI flag.
- Reserved internal names (`main`, `ofscraper.main`) are automatically ignored even if entered.

After models load, a **Reload Models** button appears in the navigation bar — use it to re-fetch models without going all the way back to the Select Action page.

---

<a id="sca-root"></a>
## Select Content Areas & Filters

This page decides **what to scan** and (optionally) provides **filters** that affect what you see/queue later.

<a id="sca-content-areas"></a>
### Content Areas

These are the sources to scan (depending on action):

- **Profile**: Profile/media feed.
- **Timeline**: Standard posts.
- **Pinned**: Posts pinned on the profile.
- **Archived**: Archived posts.
- **Highlights**: Highlight stories.
- **Stories**: Stories feed.
- **Messages**: Message media (this is where many PPV-related entries appear).
- **Purchased**: Explicit “purchased content” area (when applicable).
- **Streams**: Streams/live-related media (API VODs / stream posts — not the same as the Live Stream Monitor plugin’s `{user}/Live_Streams/` captures).
- **Labels**: Content gathered via labels.

Example:
- If you only care about messages, uncheck everything except **Messages** to speed up scraping.

> **Note:** Not all areas are available for every action:
> - **Download** supports all 10 areas.
> - **Like / Unlike** supports only: Timeline, Pinned, Archived, Streams, Labels.
> - **Check modes** (Post Check, Message Check, etc.) each scan specific areas — see [Check Mode](#check-mode-root) for details.
> Profile, Highlights, Stories, Messages, and Purchased are not available for Like/Unlike.

<a id="sca-media-types"></a>
### Media Types to Download

Control which file types are included in this scrape session:

- **Images**: Photos and image files
- **Videos**: Video files
- **Audios**: Audio files

These checkboxes default to your current config filter settings (`Download → Media Type Filter`) but can be overridden per-session without saving changes to your configuration.

Example:
- Uncheck **Videos** to download images and audio only for this run, without changing your saved config.

<a id="sca-additional-options"></a>
### Additional Options

<a id="sca-scrape-paid"></a>
#### Scrape entire paid page (slower but more comprehensive)
Attempts to enumerate paid items more thoroughly. This can be slower.

When to use:
- If you suspect paid/PPV items aren’t being discovered.

<a id="sca-scrape-labels"></a>
#### Scrape labels
Pulls content via labels when available.

When to use:
- If you organize creators by labels and want label-based coverage.

<a id="sca-include-post-text"></a>
#### Include Post Text
When enabled, the text body of each post is included alongside the downloaded media.

When to use:
- If you want to keep the post's caption or description alongside the downloaded files.

<a id="sca-name-text-from-post"></a>
#### Name text files from post text (instead of post ID)
Only available when **Include Post Text** is enabled.

- **Off (default):** `.txt` filenames follow **Configuration → File Options → File Format** (for example `{media_id}.{ext}` becomes `{post_id}.txt` for text files).
- **On:** `.txt` filenames are built from the truncated/sanitized post caption (using **Text Length** / **Text Type**). Empty captions fall back to the post ID.

Filename length warning:
- Windows NTFS and typical Linux filesystems allow about **255 characters/bytes** per filename component.
- Keep **Text Length** under **~250** so `name + ".txt"` stays within that limit.
- A warning appears under this checkbox when it is checked.

<a id="sca-discord-updates"></a>
#### Send updates to Discord (requires webhook URL in Config → General)
If enabled, the GUI will post log updates to Discord using your configured webhook.

Important:
- This only works if **Config → General → Discord Webhook URL** is set.

<a id="sca-discord-level"></a>
#### Discord notification level
When Discord updates are enabled, choose how verbose the notifications are:

- **LOW**: Only important messages — warnings, errors, and run completion summary. Reduces Discord noise.
- **NORMAL**: Standard progress messages during the scrape (more verbose).

Default: **LOW**. On first enable, a one-time prompt asks whether to save LOW as the permanent default. This option is disabled until Discord updates are enabled.

<a id="sca-advanced-options"></a>
### Advanced Scrape Options

<a id="sca-allow-dupes"></a>
#### Allow duplicates (do NOT skip duplicates; treat reposts as new items)
Disables duplicate-skipping logic. Useful if reposts should be treated as separate items.

Example:
- A creator reposts the same media across Timeline and Pinned and you want both.

Also applies to **Check modes**: when enabled, the results table keeps multi-area / repost rows instead of collapsing them to one unique media item.

<a id="sca-keep-msg-purchased-dupes"></a>
#### Also keep Messages + Purchased copies of the same media
Only available when **Allow duplicates** is on.

- **Unchecked (default):** If the same post/media is returned from both Messages and Purchased, download it once (usually under Messages). Other true reposts (same media on different posts) are still kept.
- **Checked:** Keep separate Messages and Purchased copies when both areas return the item.

Note: Allow duplicates used to queue the same Messages post twice when Purchased was also selected (same post id in both APIs), which created look-alike files in `Messages\` — that multi-area double-queue is fixed when this box is unchecked.

<a id="sca-rescrape-all"></a>
#### Rescrape everything (ignore cache / scan from the beginning)
Forces a full history scan and disables “start after last seen” behavior.

When to use:
- After changing filters/config and you want a complete rebuild.
- When you suspect cached state is hiding items.

<a id="sca-delete-db"></a>
#### Delete model DB before scraping (resets downloaded/unlocked history)
Deletes the model DB folder so the run starts “fresh”.

Important:
- The DB will be recreated during scraping.

<a id="sca-delete-downloads"></a>
#### Also delete existing downloaded files for selected models
Deletes already-downloaded files under your save location for the selected model(s).

Tip:
- If you enable file deletion, the GUI also enables DB deletion to avoid stale state.

<a id="sca-quality"></a>
#### Video quality
Select the preferred quality for video downloads. Equivalent to the `-q` / `--quality` CLI flag.

| Option | Behaviour |
|---|---|
| **Default** | Defaults to source/highest quality available on OnlyFans — identical to selecting **source** |
| **240** | Request the 240p rendition; falls back to 720p, then source if unavailable |
| **720** | Request the 720p rendition; falls back to source if unavailable |
| **source** | Request the original/highest-quality source file |

Notes:
- Only applies to **Videos**. Images and audios are unaffected.
- **Default** and **source** behave identically — both download the highest quality stream available.
- This setting is per-session — it is not saved to `config.json`.

<a id="sca-examples"></a>
### Example setups

- **Fast “new items only”**:
  - Leave **Rescrape everything** unchecked.
  - Choose only the areas you want (e.g., Timeline + Messages).

- **Full reset / rebuild**:
  - Enable **Rescrape everything**
  - Enable **Delete model DB**
  - Optionally enable **Delete downloaded files** (careful!)

<a id="sca-daemon-mode"></a>
### Daemon Mode (Auto-Repeat Scraping)

Between cycles the table footer shows a **Last run** chip (downloads / fails / size) and a **Next run** countdown with wall-clock ETA. The phase badge stays **Daemon** while waiting and flips to **Running** on the next cycle. **Stop Daemon** clears those chips. Each cycle is also recorded in **History**.

<a id="sca-daemon-enable"></a>
#### Enable daemon mode
Automatically re-runs scraping on a schedule.

<a id="sca-daemon-interval"></a>
#### Interval
Minutes between runs.

<a id="sca-daemon-notify"></a>
#### System notification when scraping starts
Shows a desktop notification at the start of each daemon run.

<a id="sca-daemon-sound"></a>
#### Sound alert when scraping starts
Plays a short beep at the start of each daemon run (best-effort on Windows).

<a id="sca-daemon-discord-ping"></a>
#### @here Discord mention when new content is found
When enabled, prepends `@here` to the Discord scrape summary message so your server gets a notification — but **only** when new content was actually downloaded in that run. If a daemon run finds nothing new, the summary is posted quietly with no mention.

Requirements:
- Daemon mode must be enabled (this checkbox is disabled otherwise)
- A Discord webhook URL must be configured in **Config → General**

The preference is saved to `gui_settings.json` and persists across sessions.

<a id="sca-filters"></a>
### Filters (on this page)

This page contains an embedded version of the same filter panel used on the Table page.
See the **Filters** section below for full details.

<a id="sca-settings-persistence"></a>
### Settings persistence

Settings on this page are **not saved automatically**. Use the two buttons in the lower-right corner of the navigation bar to manage persistence.

<a id="sca-save-settings"></a>
#### Save Settings
Saves the current state of all selections on this page to `gui_settings.json`. The saved state is then restored the next time the GUI starts.

Saved settings include: content areas, media types, additional options, advanced scrape options, daemon settings (enabled, interval, notifications, sound), and the post date range filter.

<a id="sca-reset-settings"></a>
#### Reset Settings
Clears all saved area settings from `gui_settings.json` and restores every control on this page to its default state:

- All content area checkboxes restored to defaults
- Media types reset to match your `config.json` filter settings
- All additional and advanced options unchecked
- Video quality set to **Default**
- Date filter disabled (After defaults to January 1, 2000; Before defaults to today)
- Daemon mode disabled

> **Note:** Settings not controlled by these buttons — theme, verbose log, Discord updates (on/off), and the @here daemon ping — continue to save automatically as before.

---

<a id="models-root"></a>
## Select Models

Select which creators/models to process. The list is populated from the API.

Tips:
- Search supports comma-separated terms (e.g. `alice, bob, charlie`).
- Click a model's **username** (or the row text) to select/deselect that model; the checkbox works the same way.
- Rows show aligned columns: **username**, **subscribed date**, and **current_price** (monospace), with or without **Show Avatars**.
- With **Show Avatars** on, click the avatar to open the creator's OnlyFans page (does not toggle selection).
- Use **Select All / Deselect All / Toggle** for bulk selection.

<a id="models-reload"></a>
### Reload Models

After the model list loads, a **Reload Models** button appears in the navigation bar. Click it to re-fetch the model list from the API without going back to the Select Action page. The button is hidden while loading is in progress and reappears once the list is ready.

<a id="models-filters-root"></a>
### Model Filters (right sidebar)

<a id="models-filters-subscription"></a>
#### Subscription Type
- **Renewal**: Filter by renewal on/off.
- **Status**: Filter active vs expired.

<a id="models-filters-flags"></a>
#### Flags
- **Promo**: Whether the model has claimable promos.
- **Free Trial**: Filter models that have free trials.
- **Last Seen**: Visible/Hidden state.

<a id="models-filters-price"></a>
#### Price Range
Filter models by price (min/max).

<a id="models-filters-sort"></a>
#### Sort
Controls how models are ordered (Name, Last Seen, Price, etc.) and Descending.

---

<a id="config-root"></a>
## Configuration (config.json)

This page edits `config.json` through a set of tabs. Changes are written to disk when you click **Save**. Each tab’s **?** button jumps to the matching section below.

**Validation:** **Save** and scrape start both run a config check (Save Location, File Format uniqueness tokens, Directory Format under Save Location, length bounds, FFmpeg path, empty download filters). **Errors block** save/start with a clear dialog; **warnings** ask whether to continue. The same path/uniqueness rules are described under File Options below.

**Windows paths:** filesystem path fields (Save Location, FFmpeg, CDM keys, temp dir, script paths) **display and save with backslashes** in the GUI; `config.json` stores them as escaped `\\`. **Directory Format** and **File Format** templates still use `/` between placeholders on all platforms.

Screenshot walkthrough of these tabs: the public **OF-Scraper-GUI README** Configuration section. Deeper background: [OF-Scraper GitBook](https://of-scraper.gitbook.io/of-scraper).

<a id="config-general"></a>
### General

- **Main Profile (`main_profile`)**: The default profile to use when no profile is specified.
- **Metadata Path (`metadata`)**: Where model metadata/DB files live (supports placeholders).
- **Discord Webhook URL (`discord`)**: Optional webhook for notifications.
  - To send updates to Discord using webhooks, follow the setup guide at `https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks`.
  - You’ll need to add the URL provided in the setup into the config under **General**.
  - After adding it, you can enable Discord updates from **Select Content Areas & Filters → Additional Options**.

Example:
- `main_profile`: `main_profile`
- `metadata`: `{configpath}/{profile}/.data/{model_id}`

<a id="config-file-options"></a>
### File Options

Controls where downloaded content is saved and how folders/files are named.

- **Save Location (`file_options.save_location`)**: Root download directory.
  - Example (Windows): `E:\Downloads\OnlyFans` in the GUI; `config.json` stores `E:\\Downloads\\OnlyFans`
  - Example (Linux): `/home/user/Downloads/OnlyFans`
  - See also the **Windows paths** note under [Configuration](#config-root).
- **Directory Format (`file_options.dir_format`)**: Folder structure under the save location.
  - Example: `{model_username}/{responsetype}/{mediatype}/`
  - Uses `/` between placeholders on all platforms (naming template, not an OS path).
  - Must stay **relative** to Save Location (no absolute paths or `..` segments). Invalid templates are blocked on config save and before scrape start.
- **File Format (`file_options.file_format`)**: Filename template.
  - Example: `{filename}.{ext}`
  - Must include a **uniqueness token**: `{filename}`, `{media_id}`, or `{original_filename}` (avoids collisions when a post has multiple media).
- **Text Length (`file_options.textlength`)**: How much “Text” to keep in filenames / caption-based `.txt` names. Keep under ~250 when naming text files from post text (OS filename limit is typically 255).
- **Space Replacer (`file_options.space_replacer`)**: Replace spaces in filenames.
- **Date Format (`file_options.date`)**: Date formatting string used in some templates.
  - This uses the **Arrow** date formatting syntax (`arrow.get(...).format(...)`), which is Moment-style tokens (case-sensitive).
  - There is **no whitelist** in the codebase — whatever string you enter is passed straight through to `arrow.format()`.
  - If you use unknown tokens, they generally appear literally in the output.
  - Avoid characters that are invalid in Windows filenames (e.g. `:`, `/`, `\\`, `*`, `?`, `"`).
  - **Examples**:
    - `MM-DD-YYYY` (default in this repo)
    - `YYYY-MM-DD`
    - `YYYY-MM-DD_HH-mm-ss`
    - `YYYY.MM.DD`
    - `ddd_YYYY-MM-DD` (weekday + date)
    - `MMMM-DD-YYYY` (month name + day + year)
    - `YYYY-[W]WW` (ISO week)
  - **Common tokens** (partial list):
    - Year: `YYYY`, `YY`
    - Month: `MM`, `M`, `MMM`, `MMMM`
    - Day: `DD`, `D`, `ddd`, `dddd`
    - Time: `HH`, `H`, `hh`, `h`, `mm`, `m`, `ss`, `s`
    - Timezone: `ZZ`, `Z`
- **Text Type (`file_options.text_type_default`)**: Whether text-length is measured by letters or words.
- **Enable Truncation (`file_options.truncation_default`)**: Whether long names are truncated to fit OS path/name limits (Windows/Linux filename components max ~255).

#### File path / directory format placeholders

These placeholders can be used in **Directory Format** and **File Format**.

- `{response_type}`: Posts, Messages, Paid, etc.
- `{post_id}`: ID of post.
- `{media_id}`: ID of media.

- `{file_name}`: The filename; videos will include the quality (e.g., `source`, `720`).
- `{only_file_name}`: The filename; videos will not include quality.
- `{original_filename}`: Filename as sent by OnlyFans (may or may not include `source`).

- `{media_type}`: Images, Audios, Videos.
- `{quality}`: Quality of the media; non-videos will always be `source`.

- `{value}`: The content's value: whether it's categorized as Paid or Free.

- `{model_id}`: Unique identification number for model.
- `{first_letter}`: First letter of model's username.

- `{site_name}`: OnlyFans.
- `{text}`: The text within the media. Truncation of file names has been tested to fit within OS limits; still it's advisable to establish a text length limit.
- `{date}`: The date of the post, output in the config date format.

- `{model_username}`: The model's username.
- `{username}`: The model's username.
- `{profile}`: The currently active profile.
- `{my_username}`: The authorized account's username.
- `{my_id}`: The identification number for the authorized account.
- `{label}`: The label assigned to the post, if available.
- `{download_type}`: Indication of whether it's protected or normal, determined by the necessity for decryption.

- `{current_price}`: Free if current price is 0 dollars else paid.
- `{regular_price}`: Free if regular price is 0 dollars else paid.
- `{promo_price}`: Free if promo price is 0 dollars else paid.
- `{renewal_price}`: Free if renewal price is 0 dollars else paid.

- `{args}`: The passed arguments namespace; keys can be access with the dot (`.`) syntax.
- `{config}`: The config arguments dictionary; keys can be access with the `[]` syntax.
- `{modelObj}`: Model data class via `class` folder; properties can be access via the dot (`.`) syntax.
- `{configPath}`: Path to current config directory.

<a id="config-download"></a>
### Download

- **Min Free Space (MB) (`download_options.system_free_min`)**: Don’t download if disk space is below this.
- **Auto Resume (`download_options.auto_resume`)**: Resume partial downloads when possible.
- **Max Post Count (`download_options.max_post_count`)**: Limit posts to scan (0 = unlimited).
- **Media type filter**: checkboxes for **Images** / **Audios** / **Videos** / **Text** (empty selection is blocked on Save / scrape start).
- **Verify All Integrity (`download_options.verify_all_integrity`)**: Also integrity-check non-DRM video/audio (DRM merges are always checked).
- **DRM Duration Match % (`download_options.drm_duration_match_threshold`)**: Post-download quality gate for remuxed media (see below). Default **98**.

#### DRM Duration Match % (what it does)

After FFmpeg merges DRM audio + video (and for non-DRM media when **Verify All Integrity** is on), OF-Scraper asks ffprobe how long the finished file really is, then compares that to the length OnlyFans / the MPD said the media should be.

- **Keep the file** if either:
  - `actual duration ≥ (Match % ÷ 100) × expected duration`, **or**
  - the file is at most **1.0 second** shorter than expected (OnlyFans often reports whole seconds; remux/ffprobe can be a few tenths short — e.g. expected 12s, actual 11.71s).
- **Also rejects** empty or tiny junk files (&lt; ~1 KB or ~0 seconds long), even before the percent check matters.
- **On failure**: the bad file is deleted and the download is marked **failed** so it can be retried (see the post-run failure summary).

| Match % | Effect |
|--------|--------|
| **Higher** (99–100) | Stricter — short/truncated merges fail more often; more retries, fewer silent half-videos |
| **98** (default) | Practical sweet spot for normal DRM remuxes |
| **Lower** (90–95) | Looser — more files kept even if a bit short; fewer retries, higher risk of incomplete media |

**Save** writes the percent as a 0–1 ratio in config (e.g. `98` → `download_options.drm_duration_match_threshold: 0.98`).

**Why it helps:** A DRM merge can “succeed” and still produce a truncated or empty file. Without this check you may think you have a full video when you don’t. DRM remuxes always use this gate; turn on **Verify All Integrity** if you also want the same duration check on non-DRM downloads.

Download resilience (automatic):
- Stalled transfers (no data for `OFSC_CHUNK_TIMEOUT_SEC`, default **30s**) abort the attempt and retry.
- `.part` finalize rejects empty or truncated files; expected size uses `Content-Range` when resuming so partial downloads are not wiped or accepted incomplete.
- Size slack is `OFSC_PART_SIZE_TOLERANCE` (default **64** bytes).
- Media / DRM / license URLs must resolve to allowlisted hosts (`onlyfans.com`, `cloudfront.net`, plus optional extras via Configuration → Advanced → **Media Host Suffixes** or `OFSC_MEDIA_HOST_SUFFIXES`).
- Resolved download paths (and naming-script overrides) must stay under **Save Location** (or the configured temp root for `.part` files).

#### FFmpeg (important)
- **FFmpeg Path (`binary_options.ffmpeg`)**: Needed to merge some DRM-protected audio/video streams after decryption, and for ffprobe duration checks.
  - Recommended: **FFmpeg 7.1.1 or lower** from `https://www.gyan.dev/ffmpeg/builds`

<a id="config-scripts"></a>
### Scripts

Optional external scripts under `script_options` in `config.json`. Leave paths empty/`null` to disable (default).

- **After Action Script (`script_options.after_action_script`)**: Runs after an action for each model has completed.
- **Post Script (`script_options.post_script`)**: Runs after all actions for all models have completed.
- **Naming Script (`script_options.naming_script`)**: Can rewrite the final filename/path before download. **Disabled by default** (empty path).
- **Preferred file extensions** (stored under `file_options`, shown on this Scripts tab):
  - Each media type has its own checkbox (**Images** / **Videos** / **Audios**) — off by default. Enable only the types you want to remap.
  - When a type is checked, only that type’s `{ext}` changes (`file_options.image_extension` / `video_extension` / `audio_extension`).
  - Does **not** convert or remux — bytes stay as downloaded; the rest of the filename is unchanged.
  - Keys: `override_image_extension`, `override_video_extension`, `override_audio_extension` (legacy single `override_file_extensions` still loads as “all three on” until you Save).
  - Dropdowns (editable; used only when that type’s checkbox is on):
    - **Images** → `file_options.image_extension` (default `jpg`; also `jpeg`, `png`, `webp`, …)
    - **Videos** → `file_options.video_extension` (default `mp4`; also `mov`, `m4v`, …)
    - **Audios** → `file_options.audio_extension` (default `mp3`; also `m4a`, `wav`, …)
- **After Download Script (`script_options.after_download_script`)**: Runs after each individual media download completes.
- **Skip Download Script (`script_options.skip_download_script`)**: Runs before a download; return `"False"` or empty stdout to skip that file.

Note: older GUI builds incorrectly wrote `scripts_options` (typo). Saving from the current GUI migrates values into `script_options` and removes the typo key.

<a id="config-performance"></a>
### Performance

- **Thread Count (`performance_options.thread_count`)**: Download threads.
- **Download Semaphores (`performance_options.download_sems`)**: Limits concurrency inside the downloader.
- **Download Speed Limit (KB/s) (`performance_options.download_limit`)**: 0 = unlimited.

<a id="config-content"></a>
### Content

Content filtering settings:
- **Block Ads (`content_filter_options.block_ads`)**
- **Max/Min File Size (`content_filter_options.file_size_max` / `file_size_min`)**
  - Examples: `500MB`, `2GB`, or `0` for no limit
- **Max/Min Length (seconds) (`content_filter_options.length_max` / `length_min`)**

<a id="config-cdm"></a>
### CDM

These settings impact DRM-protected content.

- **Key Mode (`cdm_options.key-mode-default`)**:
  - `manual`, `cdrm`, `cdrm2`, or `keydb`
  - **Default for new installs: `manual`** — local CDM files; most reliable for OnlyFans DRM.
  - Existing configs keep whatever you already saved (this change does not rewrite `config.json`).
  - **`cdrm` / `cdrm2` / `keydb`** are remote helpers (opt-in). The GUI warns in this tab, on save, and before scrape.
  - Remote helpers send **only pssh + license URL** — never session cookies, sign, or x-bc headers.
  - Because OnlyFans license requests usually need those cookies, remote modes may fail; use **manual** + local CDM / DRM Key Creation.
  - Override the built-in default with env `OFSC_KEY_DEFAULT` if needed.
- **KeyDB (`cdm_options.keydb_api`)**:
  - **Status**: **currently not working** (no info on when/if it will become available again).
  - The KeyDB API key field remains in the config for compatibility, but **KeyDB mode should be avoided** for now.
- **Client ID File (`cdm_options.client-id`)** and **Private Key File (`cdm_options.private-key`)**:
  - Required for **manual** CDM keys (DRM scraping)
  - Use the built-in **[DRM Key Creation](#drm-key-creation)** page to generate keys automatically, or see the manual guide: `https://github.com/FoxRefire/wvg/wiki/How-to-dump-CDM-key-pair-from-AVD`

<a id="config-advanced"></a>
### Advanced

Power-user settings. These options mostly affect **network/signing**, **cache behavior**, and **CLI/automation** flows.

- **Dynamic Mode (`advanced_options.dynamic-mode-default`)**: Controls which source provides the **request-signing rules** used to talk to OnlyFans.
  - If the OnlyFans API changes (auth/signature errors, 401/403 loops), switching this is one of the first things to try.
  - **Valid values** (from code): `datawhores`, `digitalcriminals` (aliases: `dc`, `digital`, `digitals`), `xagler`, `rafa`, `generic`, `manual`
  - **Default fallback**: if an unknown value is set, the app falls back to the default rule source.
  - **Notes**:
    - `manual` uses **Manual Dynamic Rules** (below) or env `OFSC_DYNAMIC_RULE_MANUAL`.
    - `generic` uses **Dynamic Rules URL** (below) or env `OF_DYNAMIC_GENERIC_URL` / `OFSC_DYNAMIC_GENERIC_URL`.

- **SSL Verify (`advanced_options.ssl_verify`)**: Controls SSL/TLS certificate verification for API requests.
  - **`custom`**: use OF-Scraper’s built-in certificate bundle (typical default).
  - **`true`**: use system certificates (strict).
  - **`false`**: disable SSL verification.
  - If model load / auth fails with correct credentials — especially behind corporate proxies, TLS-inspecting antivirus, or broken system CA stores — try setting this to **`false`**, Save, then **Retry**. This has helped some users; it is **less secure** (man-in-the-middle risk), so only use it when needed and prefer fixing certificates when you can.
  - The **Unable to Load Models** dialog links here via **SSL Verify (Config)**.

- **API Path (`advanced_options.api_path`)**: OnlyFans HTTP API path prefix (default `/api2/v2`).
  - If OnlyFans renames the API path (e.g. `/api2/v3`), set this so default endpoints rewrite without a code patch.
  - Env override: `OFSC_API_PATH` (takes precedence over `config.json`).
  - Leave at the default unless the stock path stops working. Restart or re-open after changing if requests still use the old path.

- **Manual Dynamic Rules (`advanced_options.dynamic_rules_manual`)**: Paste or **Load JSON…** for local signing rules when Dynamic Mode is `manual`.
  - Required fields: `static_param`, `checksum_indexes`, `checksum_constant`, plus either `format` **or** both `prefix` and `suffix` (optional `app_token` / `app-token`).
  - Env override: `OFSC_DYNAMIC_RULE_MANUAL` (takes precedence over `config.json`).
  - If mode is `manual` but rules are empty/invalid, OF-Scraper falls back to remote providers (same as before).
  - Save validates JSON when Dynamic Mode is `manual` and the field is non-empty.

- **Dynamic Rules URL (`advanced_options.dynamic_rules_url`)**: Remote signing-rules JSON URL when Dynamic Mode is `generic`.
  - Must be `http://` or `https://`.
  - Env overrides: `OF_DYNAMIC_GENERIC_URL` or `OFSC_DYNAMIC_GENERIC_URL` (take precedence over `config.json`).
  - Empty URL + mode `generic` falls back to other remote providers.

- **API Endpoint Overrides (`advanced_options.api_endpoint_overrides`)**: JSON object mapping endpoint keys to full URL templates.
  - Example: `{"meEP":"https://onlyfans.com/api2/v2/users/me"}`
  - Known keys include `meEP`, `timelineEP`, `timelineNextEP`, `LICENCE_URL`, `messagesEP`, `profileEP`, `subscriptionsActiveEP`, and other keys from the API URL table (see tooltip / Load JSON).
  - Dedicated `OFSC_API_*` env vars still win when set for that endpoint.
  - Leave `{}` to use built-in defaults. Global **API Path** still rewrites `/api2/v2` in overridden URLs when applicable.

- **Media Host Suffixes (`advanced_options.media_host_suffixes`)**: Extra allowed media/DRM CDN host suffixes (comma-separated).
  - Built-in allowlist always includes `onlyfans.com` and `cloudfront.net`.
  - Add hosts here if OnlyFans moves media to a new CDN and downloads fail with a blocked-host error.
  - Env `OFSC_MEDIA_HOST_SUFFIXES` is merged with this field.

- **Backend (`advanced_options.backend`)**: HTTP client library used for network requests.
  - `aio`: aiohttp (async-only)
  - `httpx`: httpx (async + sync in some codepaths)
  - If you see odd connection/proxy/TLS issues, switching backends can help.

- **Cache Mode (`advanced_options.cache-mode`)**: Storage backend for the local cache.
  - **Valid values** (from code): `sqlite`, `json`, `disabled`
  - `sqlite` is generally the best choice for larger caches.
  - `disabled` attempts to turn caching off (useful for troubleshooting), but can reduce performance and may increase API calls.
  - Tip: for “fresh scrape” behavior, the GUI’s “ignore cache / rescrape” options are usually a better fit than disabling the cache globally.

- **Code Execution (`advanced_options.code-execution`)**: Enables `eval()` for certain placeholder “custom values”.
  - **Security warning**: do not enable this if you paste untrusted placeholder content.

- **Download Bars (`advanced_options.downloadbars`)**: Shows per-download progress bars in console output.
  - Can reduce performance at higher thread counts; turn off if the UI/console feels sluggish.

- **Append Log (`advanced_options.appendlog`)**: If enabled, logs append into a single daily file (per profile).
  - If disabled, OF-Scraper writes per-run log files.

- **Sanitize Text (`advanced_options.sanitize_text`)**: Cleans post/message text before inserting it into the database.
  - Helps avoid DB issues caused by unusual characters.
  - This affects what is stored as “text” metadata (and can affect text-based filtering/searching).

- **Remove Hash Match (`advanced_options.remove_hash_match`)**: Controls optional file hashing + duplicate cleanup.
  - `None`: do not hash files (fastest)
  - `False`: hash files, but **do not delete** duplicates
  - `True`: hash files and **remove duplicate files** (deletes extra copies of identical content)
  - Warning: deletion is permanent; use carefully.

- **Enable Auto After (`advanced_options.enable_auto_after`)**: Speeds up future scrapes by automatically setting an “after” cutoff based on previous scans.
  - Requires caching/DB information; turning this off forces more full-history scans.
  - If you feel you’re missing older content, disable it temporarily and run a full scan.

- **Temp Directory (`advanced_options.temp_dir`)**: Optional directory to store temporary download files.
  - Leave empty to use the default temp/save location behavior.

- **Infinite Loop (Action Mode) (`advanced_options.infinite_loop_action_mode`)**: When enabled, “action mode” runs can loop and prompt to continue.
  - Mostly affects CLI automation flows (running actions repeatedly without restarting the program).

- **Default User List / Black List (`advanced_options.default_user_list` / `default_black_list`)**: Default model lists to include/exclude when retrieving creators.
  - Format: comma-separated list names (case-insensitive)
  - Built-ins: `main`, `active`, `expired` (also supports `ofscraper.main`, etc.)

<a id="config-response-type"></a>
### Response Type

Maps internal response types to **folder / display aliases** used with `{responsetype}` / `{response_type}` in Directory Format and File Format.

Typical keys in the GUI include timeline/posts, archived, pinned, streams, messages, paid, stories, highlights, and profile (exact labels follow the form fields). Changing a value renames the folder segment for that content type without changing how OF-Scraper classifies the media.

---

<a id="table-root"></a>
## Table / Scraping page

This is where scraped rows appear, filters are applied, and downloads are queued.

<a id="table-toolbar"></a>
### Toolbar buttons
- **Filters**: Show/hide the left filter sidebar.
- **Reset**: Reset filters.
- **Apply Filters**: Apply the current filter state.
- **Start Scraping >>**: Begin scraping the selected areas/models.
  - For larger or high-impact jobs (multiple models, many areas, rescrape, delete DB/files, daemon, etc.) a **Confirm scrape** dialog summarizes the job and a rough ETA before anything starts.
  - Destructive options (delete DB / delete downloads) always confirm, even if you chose “don’t ask again.”
  - Preference `skip_scrape_confirm` in `gui_settings.json` skips typical confirms after you opt out.
  - Before start, the GUI also checks **free disk space** on Save Location vs a rough size estimate (and a low-space floor). Critical low space always prompts; other warnings can be suppressed via `skip_disk_space_check`.
- **Cancel**: Appears while a scrape is running. Requests a cooperative stop, shows a **Cancelling…** state (Start stays disabled) until the scraper thread exits, and only force-stops if cancel does not complete within a few seconds.
  - Cooperative cancel now also stops **API pagination** (between pages), **mid-file chunk downloads**, and **between model/actions** — not only between queued media items.
  - **Import Cookies** Cancel is checked during Chrome cookie DB decrypt walks as well.
- **New Scrape**: Return to the beginning.
  - If scraping is active, you’ll be asked if you want to cancel first; navigation waits until cancel finishes.
- **History**: Opens a browser of recent scrape / check runs (when, status, models, downloads, size, duration). Times use your system local clock. Filter by status or model search; open **Details**, **Re-run this** (restores models/areas when still available; never auto-enables delete options), delete one entry, or clear all.
- **Export CSV**: Saves visible (filtered) table rows to a CSV file. If rows are selected, you can export only the selection or all visible rows. Respects privacy mode for usernames.
- **Stop Daemon**: Stops daemon mode if enabled.
- **Select All / Deselect All**: Check mode only — controls the download cart for all visible rows.
- **Add Selected / Remove Selected**: Check mode only — act on highlighted table rows (**Ctrl/Shift-click** to multi-select; **Space** toggles cart). Right-click also offers add/remove/toggle in check mode.
- **>> Send Downloads**: Check mode only — queues cart rows for downloading.
  - If the cart has **25+** items, a **Confirm downloads** dialog shows count by type/model and a rough ETA before queueing.
  - Preference `skip_cart_confirm` in `gui_settings.json` skips that prompt after you opt out.
  - Also runs the same **disk space** check against Save Location before queueing.

On narrow windows the toolbar **wraps** onto extra rows (flow layout) so buttons stay usable; cart actions still only appear in check mode.

When the media grid is empty, a short **guidance overlay** explains what to do next (start scrape, wait for rows, loosen filters, or no media found).

Column headers remember **width**, **order** (drag to reorder), and **visibility**. Right-click a header to hide a column, show hidden ones, set **Sticky columns** (keeps Number / Download Cart — and optionally UserName — visible while scrolling horizontally), or **Reset column layout**.

<a id="table-progress"></a>
### Progress + logs
- The footer is a **unified status strip**:
  - **Phase badge** — Ready / Running / Cancelling / Daemon / Complete
  - **Elapsed timer** — live `m:ss` (or `h:mm:ss`) while Running / Cancelling; final value stays on Complete
  - **Health chips** — **Auth**, **Config**, and **Key** (green OK / orange warning / red error). Hover for details; click to open Authentication, Configuration, or DRM Key Creation.
  - **Status text** — latest host status message (full text on hover)
  - **Overall progress** — downloads completed / total and bytes
  - **Last-run chip** during daemon mode — downloads / fails / size from the previous cycle
  - **Next-run countdown** with wall-clock ETA (e.g. `Next run in 12:34 (≈ 9:52 PM)`)
  - **Row count** for the current table filter
- Above the table, a **per-model badge bar** updates live during the scrape:
  - Summary: `Models done/total  ✓ok  ✗failed`
  - One chip per selected model (○ waiting → ● running → ✓ ok / ✗ fail)
  - Hover a chip for status / error detail (names respect Privacy mode)
- Progress updates are **throttled/batched** so large scrapes stay responsive (bar + bytes + table cells).
- The console area shows detailed logs and trace output.
- Drag the **horizontal bar** between the table and console to resize the log panel (height is remembered in `gui_settings.json`).
- **Double-click** that bar to reset the console to the default height (~180 px).
- Under the hood, scrape status/progress/cancel go through a small `ScrapeHostCallbacks` host contract (GUI implementation emits Qt signals), including `on_item_started` / `on_item_result` for badges.

<a id="check-mode-root"></a>
## Check Mode

Check modes let you browse all media for a creator in a table view and selectively download individual items, rather than queueing everything at once. This is useful when you want to preview what is available — including locked/paywalled content — before deciding what to save.

<a id="check-mode-which"></a>
### Which mode to use

Select a check mode from the **Select Action** step:

| Mode | What it scans |
|---|---|
| **Post Check** | Timeline, pinned, archived, streams, and label posts |
| **Message Check** | Direct messages and PPV messages |
| **Paid Check** | Explicitly purchased/paid content |
| **Story Check** | Stories and highlights |

> If you are looking for PPV messages (pay-per-view content sent via DMs), use **Message Check** — these do not appear in Post Check.

<a id="check-mode-msg-filter"></a>
### Message filter (Message Check only)

When **Message Check** is selected on the Action page, a message filter option appears:

- **Paid / PPV only** *(default)*: Show only paid and PPV messages — hides free messages. Locked (unpurchased) items are always shown.
- **Free messages only**: Show only free messages — hides paid and PPV content.
- **All messages**: Show all messages, both free and paid/PPV.

<a id="check-mode-table"></a>
### The check table

After models are selected and the check runs, a full media table is populated with every item found — including content you have not purchased. The table supports the same filters, sorting, and column layout as the main scraping table.

<a id="check-mode-locked"></a>
### Locked content

Items that are behind a paywall (no download URL available) are shown with a **Locked** label in the Download Cart column:

- The cell has a grey background and cannot be clicked or toggled
- These items cannot be downloaded without purchasing them on OnlyFans first
- Use the **Status → Downloaded/Unlocked** filter and select **Locked** to isolate all paywalled rows

<a id="check-mode-download"></a>
### Downloading from check mode

1. Click the **Download Cart** cell of any unlocked row to toggle it to `[added]` (with a multi-row selection, the click applies to all selected rows)
2. Or **Ctrl/Shift-click** rows → **Add Selected** (or right-click → Add selected to cart); **Space** toggles the selection
3. Use **Select All** in the toolbar to queue everything unlocked at once
4. Click **>> Send Downloads** to begin downloading all queued items
5. Each row updates in real time: `[downloading]` → `[downloaded]`, `[skipped]`, or `[failed]`
6. When the scrape finishes, if any downloads **failed**, a **Download failures** dialog lists model, media ID, type, and reason (model names respect Privacy mode). You can **Filter table to failures**. In check mode you can also **Add failures to cart** and use **>> Send Downloads** to retry.
7. The footer progress bar tracks individual item completion — e.g. `3 / 10` as each file finishes

---

<a id="filters-root"></a>
## Filters (Table page + embedded on Areas page)

On the **Table** page, the Filters sidebar includes **named presets**:
- Choose a preset from the dropdown to load and apply it (also remembered as **last used**)
- **Save** overwrites the selected preset with the current filter controls
- **Save as…** stores current filters under a new name (`filter_presets.json`)
- **Rename** renames the selected preset without changing its filters
- **Delete** removes the selected preset
- On startup, the last-used preset is restored and applied automatically

Presets are separate from Area page **Save Settings** (which remembers scrape areas / options).

<a id="filters-text-search"></a>
### Text Search
- **Search text content…**: Filters rows based on the “Text” column.
- **Full string match**: Uses a full-match (regex-style) match instead of substring search.

Example:
- Search `promo` to show only rows whose text contains “promo”.

<a id="filters-media-type"></a>
### Media Type
Filter rows by media type: **Audios**, **Images**, **Videos**.

<a id="filters-response-type"></a>
### Response Type
Filter rows by where they came from: **Pinned**, **Archived**, **Timeline**, **Stories**, **Highlights**, **Streams**.

<a id="filters-status"></a>
### Status (Downloaded / Unlocked)

#### Downloaded
- **True**: File is downloaded.
- **False**: Not downloaded.
- **No (Paid)**: Not downloadable as-is (often paywalled).

<a id="unlocked-meanings"></a>
#### Unlocked (important)
The **Unlocked** column is not a direct 1:1 match with “purchased”.

- **Locked**: Not viewable (paywalled).
- **Preview**: Viewable teaser/preview media for a priced item.
- **Included**: Viewable media inside a priced message **without purchasing** (e.g., teaser media that OnlyFans still marks as viewable even though the message is priced).
- **True**: Treated as fully unlocked/accessible (typically purchased / opened content).
- **False**: Known to be not-unlocked in the data source/DB.

<a id="filters-date-range"></a>
### Post Date Range

Filter content by post date using independent **After** and **Before** controls. Each side can be enabled or disabled on its own — you can use just After, just Before, or both together as a range.

Each row has two modes selected via the dropdown:

| Mode | Behaviour |
|---|---|
| **Fixed date** | Pick a specific calendar date using the date picker |
| **Relative** | Enter a number + unit (e.g. *7 days ago*). The date is computed fresh at the start of each scrape run, so a saved setting of "7 days ago" will always mean the last 7 days regardless of when you saved it |

#### After
Only show/scrape content posted **on or after** this date. Equivalent to the `--after` CLI flag.

#### Before
Only show/scrape content posted **on or before** this date. Equivalent to the `--before` CLI flag.

Relative units available: **hours ago**, **days ago**, **weeks ago**, **months ago**.

#### Examples

**Scrape a specific single day (e.g. August 15, 2025)**

Set both After and Before to the same date:
1. After → Fixed date → pick **August 15, 2025** → check **Enable**
2. Before → Fixed date → pick **August 15, 2025** → check **Enable**

ofscraper will fetch posts whose date falls on or after August 15 *and* on or before August 15, which is exactly that one day.

**Scrape a date range (e.g. July 1 – August 31, 2025)**

1. After → Fixed date → pick **July 1, 2025** → check **Enable**
2. Before → Fixed date → pick **August 31, 2025** → check **Enable**

**Scrape only content from the last 7 days (rolling)**

1. After → Relative → **7** → **days ago** → check **Enable**
2. Leave Before unchecked

Because Relative dates are computed at scrape start, this will always mean "the past 7 days" no matter when you run it — no need to update the date manually.

**Scrape only the last 24 hours**

1. After → Relative → **1** → **days ago** → check **Enable**
2. Leave Before unchecked

Tips:
- Picking a date or changing a relative value automatically enables that side.
- Both sides can be saved by clicking **Save Settings** on the Select Content Areas & Filters page — they are then restored on next launch.
- You can mix modes — e.g. After → Relative (rolling start) and Before → Fixed date (hard cutoff).

<a id="filters-duration"></a>
### Duration (Length)
Enable and choose min/max to filter by video length.

<a id="filters-price"></a>
### Price Range
Filter by min/max price. “Free” items typically show as `Free`.

<a id="filters-id"></a>
### ID Filters
Exact-match filters for:
- **Media ID**
- **Post ID**
- **Post Media Count**
- **Other Posts w/ Media**

<a id="filters-username"></a>
### Username
Filter rows by model username.

Tips:
- Search supports comma-separated terms (e.g. `alice, bob, charlie`).

---

<a id="table-columns"></a>
## Table columns (what each one means)

The table is a flattened view of scraped media rows.

<a id="table-col-number"></a>
### Number
Row index.

<a id="table-col-download-cart"></a>
### Download Cart
State of the row in the download queue/cart.

<a id="download-cart-meanings"></a>
Possible values:
- `[]`: not selected
- `[added]`: queued for download
- `[downloading]`: currently downloading
- `[downloaded]`: finished
- `[skipped]`: skipped (already downloaded or filtered out)
- `[failed]`: download failed
- `Locked`: paywalled — item cannot be downloaded (check mode only)

Tip:
- Click the **Download Cart** cell to toggle selection (applies to all highlighted rows when multi-selected).
- **Ctrl/Shift-click** rows, then **Add Selected** / **Remove Selected**, or press **Space** to toggle.
- `Locked` cells cannot be toggled — purchase the content on OnlyFans first.

<a id="table-col-username"></a>
### UserName
The creator/model username.

<a id="table-col-downloaded"></a>
### Downloaded
Whether the file is already downloaded (`True`/`False`) or not applicable (`N/A`).

<a id="table-col-duplicate"></a>
### Duplicate
Shows `Duplicate` (highlighted in orange) when this row shares the same `media_id` as an earlier row in the table. Duplicate rows are skipped by the download pipeline unless **Allow duplicates** is enabled in Advanced Scrape Options.

<a id="table-col-unlocked"></a>
### Unlocked
See **Unlocked (important)** above for label meanings.

<a id="table-col-other-posts"></a>
### other posts with media
Count/indicator related to other posts that also contain this media.

<a id="table-col-length"></a>
### Length
Media duration (videos), otherwise `N/A`.

<a id="table-col-mediatype"></a>
### Mediatype
`videos`, `images`, or `audios`.

<a id="table-col-post-date"></a>
### Post Date
Date/time for the post/message entry.

<a id="table-col-post-media-count"></a>
### Post Media Count
How many media items are attached to that post/message.

<a id="table-col-responsetype"></a>
### Responsetype
Source type (e.g., `timeline`, `message`, `pinned`, etc.).

<a id="table-col-price"></a>
### Price
Price of the post/message (often `Free` or a number).

<a id="table-col-post-id"></a>
### Post ID
ID of the post/message container. **Click** a Post ID (blue link style) to open that post on OnlyFans (`https://onlyfans.com/{post_id}/{username}`). Useful for inspecting content that failed to download.

<a id="table-col-media-id"></a>
### Media ID
ID of the specific media item. **Click** a Media ID to open the same OnlyFans post page for that row (uses the row’s Post ID + username).

<a id="table-col-text"></a>
### Text
Text/description associated with the post/message (may be truncated).

---

<a id="drm-key-creation"></a>
## DRM Key Creation

This page automates Widevine L3 key extraction using an Android emulator running on your local machine. The resulting keys (`client_id.bin` and `private_key.pem`) are needed when **Key Mode** is set to `manual` in [Configuration → CDM](#config-cdm).

### System requirements

- **CPU**: x86-64 processor (hardware virtualisation strongly recommended: VT-x on Intel, AMD-V on AMD)
- **RAM**: 8 GB minimum, 16 GB recommended
- **Disk**: 8 GB free space (SDK + emulator image + APKs)
- **Internet**: Required — downloads ~3 GB of tools on first run

### First run

The script automatically downloads the following on first run (~3 GB total):

- Portable JDK 17 (Adoptium Temurin)
- Android SDK cmdline-tools, emulator, and platform-tools
- Android system image (android-29, google_apis, x86_64)
- Frida server binary
- Kaltura Device Info APK

Subsequent runs reuse the cached files and complete much faster.

### Hardware virtualisation

| Acceleration | Typical time | Notes |
|---|---|---|
| KVM / VT-x (hardware) | 10–20 min | Requires CPU with `vmx` or `svm` flag exposed to the guest |
| Software emulation (TCG) | 45–90 min | Automatic fallback when KVM is unavailable |

The script automatically detects whether hardware virtualisation is available and falls back to software emulation if needed. No manual configuration is required.

**Windows note:** If extraction fails with “CPU does not support VT-x/AMD-V” but BIOS virtualization is enabled, check the log for `can't find the emulator-check executable`. That means the Android Emulator package under `~/widevine-sdk/emulator` is incomplete (often antivirus quarantine), not that your CPU lacks virtualization. Restore `emulator-check.exe` from quarantine or re-run Generate Keys after applying the latest GUI patch (it auto-repairs the package).

### Output

| File | Contents |
|---|---|
| `client_id.bin` | Widevine client identification blob |
| `private_key.pem` | Widevine device private key |

Saved to `~/.config/ofscraper/device/` by default (or the **Output Folder** you specify). After a successful extraction you will be offered the option to update `config.json` and set Key Mode to `manual` automatically.

### Options

- **Extraction Script**: Path to `drm_keydive.py`. Uses the bundled copy by default; point this at a custom script only if you have a specific reason to do so.
- **Output Folder**: Where the key files are saved. Leave blank to use the default location.

---

<a id="merge-dbs"></a>
## Merge DBs

1. Pick a **Source Folder** containing one or more `user_data.db` files.
2. Pick a **Destination** folder for the merged output.
3. Click **Start Merge** (back up first).

---

<a id="troubleshooting"></a>
## Troubleshooting notes

- If you purge files/DB and immediately start a download scrape, folders/databases may be recreated right away.
- For some message/PPV entries, “viewable/unlocked” may not map 1:1 to “purchased”.
- **Health chips** (footer **Auth** / **Config** / **Key**) orange or red: hover for the reason; click to open Authentication, Configuration, or DRM Key Creation.
- **“Blocked … host”** on download: media/DRM URLs must be on the allowlist (`onlyfans.com`, `cloudfront.net`, or extras via Configuration → Advanced → **Media Host Suffixes** / `OFSC_MEDIA_HOST_SUFFIXES`).
- **Path escapes Save Location**: Directory Format / naming-script paths cannot use absolute paths or `..` that leave the save (or temp) root — fix under Configuration → File Options.
- **DRM integrity / empty mux / duration match failed**: file was rejected after merge (tiny/empty or shorter than **DRM Duration Match %**). Check FFmpeg, keys, and the failure summary; failed items can be retried.
- **Stall / truncated `.part`**: inactive transfers abort after `OFSC_CHUNK_TIMEOUT_SEC` (default 30s) and retry; incomplete `.part` files are not promoted. With **Auto Resume** on, restart can continue using Content-Range.
- **Remote Key Mode** (`cdrm` / `cdrm2` / `keydb`) warnings or license failures: prefer **manual** CDM + [DRM Key Creation](#drm-key-creation). Remote helpers never send session cookies.
- Config Save or Start Scraping blocked by validation: read the dialog and fix File Format uniqueness / Directory Format / FFmpeg / Save Location as indicated.

<a id="troubleshooting-crash"></a>
### GUI crash / hang diagnostics

If the window disappears or freezes (especially during model load while changing pages, or mid-scrape under heavy downloads):

1. Check **`~/.config/ofscraper/gui_crash_logs/`** (Windows: `%USERPROFILE%\.config\ofscraper\gui_crash_logs\`):
   - `model_fetch_breadcrumbs.log` — last stage markers before a hang/crash (look for `scrape=1` / `activity_scrape` during a scrape)
   - `faulthandler.log` — native / fatal dumps when available (access violations often involve Rich/console logging from worker threads)
2. Turn on **Verbose Log** (sidebar) for a fuller session transcript next time.
3. When reporting a crash, include the last ~30 lines of the breadcrumb file and your GUI patch id (sidebar version → About).

In **Docker**, the same folder is on the mounted config volume. The entrypoint also appends GUI stdout/stderr to `logging/gui-docker.log` and **restarts** the GUI after exit (`GUI_RESTART_DELAY`). Open noVNC at port **6699**.

<a id="troubleshooting-docker"></a>
### Docker notes

- noVNC: `http://<host>:6699/` (not 6969).
- DRM **Key Creation** is not supported in the container — generate keys on a desktop host and mount them (`device/` under config, or your host `.config/ofscraper` path).
- Prefer local **manual** CDM keys; do not bind-mount a host `ffmpeg` binary (use the image’s FFmpeg).
- Unattended `GUI_ARGS` auto-start skips scrape-confirm / disk / remote-key dialogs so the container can start without clicks.

---

<a id="manual-url-scrape"></a>
## Scraping by Post URL / ID

Use **Scrape individual posts by URL or Post ID** (on the Action page) to download
specific posts without selecting a creator.

**How it works:**
1. Choose **Scrape individual posts by URL or Post ID** on the Action page and click **Next**
2. On the URL input page, enter one or more post URLs or post IDs — one per line, or comma-separated
3. Click **▶ Start Scraping**

**Accepted formats:**
- Full post URL: `https://onlyfans.com/123456789/username`
- Post ID only: `123456789`
- Profile URL: `https://onlyfans.com/username` (scrapes all accessible posts for that creator)

**Notes:**
- This is equivalent to the TUI command `ofscraper manual --url <url>`
- Model selection and area selection are skipped entirely
- Multiple URLs/IDs can be entered at once — separate them with newlines or commas
- Lines starting with `#` are treated as comments and ignored
- When the run finishes, the **results table** shows the media from those URLs/IDs and the usual **Final Stats Summary** appears in the log

---

<a id="auth-root"></a>
## Authentication

The **Authentication** page stores OnlyFans session values in your profile `auth.json`. You can fill them in four ways (each has a **(?)** button on the page):

| Option | Best when… |
|---|---|
| [Credentials](#auth-credentials) | You already copied values from DevTools |
| [Import Cookies](#auth-import-cookies) | You are already logged in (Zen/Firefox on Windows; any browser on Linux) |
| [Login in System Browser](#auth-login-system-browser) | You want a real browser window (any browser in the dropdown, including Chrome on Windows) |
| [Login in App Browser](#auth-login-app-browser) | You want an embedded window inside the app |

After any method succeeds, click **Save**, then optionally **Test Credentials**.

**Select Browser** (under Import Cookies) is shared: it chooses which browser **Import Cookies** reads from disk, and which browser **Login in System Browser** launches. On Windows, Chrome-family items may be labeled **Import: Linux only** — that limit applies only to **Import Cookies**, not to System Browser login.

<a id="auth-credentials"></a>
### Credentials (manual entry)

Type or paste values into the form fields, then **Save**.

| Field | What it is | Where to find it |
|---|---|---|
| **Session Cookie (sess)** | Main OnlyFans session cookie | DevTools → **Network** (filter `init`, refresh on the **main timeline**) → request → Headers → Cookie → `sess` — or Application → Cookies → `sess` |
| **Auth ID Cookie** | Account id cookie | Same Cookie header / Cookies panel → `auth_id` |
| **Auth UID Cookie** | Optional 2FA cookie (`auth_uid…`) | Same panel; leave empty if unused |
| **User Agent** | Browser user-agent string | Network → Request Headers → `user-agent` (prefer over Console `navigator.userAgent`) |
| **X-BC Header** | Request signing header | Network → Request Headers → `x-bc` |

Tips:
- Use the eye icon on **sess** to show/hide the value.
- Privacy mode masks credential fields for screenshots.
- Prefer Import Cookies or a Login button when possible — fewer transcription mistakes.
- Step-by-step Network / `init` / refresh flow: [Auth Issues → manual copy](#auth-issues).

<a id="auth-import-cookies"></a>
### Import Cookies

**Import Cookies** reads allowlisted auth values from the browser profile selected under **Select Browser**: `sess`, `auth_id`, optional `auth_uid*` (2FA), plus `x-bc` / user-agent when available. Unrelated browser cookies (CSRF, tracking, etc.) are dropped. Cookie hosts must be `onlyfans.com` or a real subdomain (lookalike domains are rejected).

For **Firefox / Zen**, Import Cookies prefers a **live** `navigator.userAgent` from remote debugging when the browser was started with `--remote-debugging-port`. Otherwise it uses the profile / Gecko install milestone (e.g. `Firefox/154.0`). It does **not** assume Fingerprinting Protection always spoofs to Firefox/115 — that often does not match DevTools Network headers on Zen.

If you use a **User-Agent Switcher** extension that is **enabled** (especially random mode), paste the exact DevTools Network value when prompted. Disabled switcher addons are ignored.

**When to use:** you are already logged into OnlyFans in that browser and want a one-click fill.

**Platform notes:**
- **Windows:** disk import works for **Zen Browser** and **Firefox**. Chrome / Chromium / Edge / Brave / Opera **Import Cookies** is **Linux-only** on this build (App-Bound Encryption / DevTools limits). For Chrome on Windows use [System Browser](#auth-login-system-browser), [App Browser](#auth-login-app-browser), or paste from DevTools.
- **Linux:** any listed browser; apt / Flatpak / Snap / deb is detected automatically from the running process.

**While import runs:**
- A progress dialog appears with **Cancel**
- The button shows **Importing…** and is disabled
- Cancel aborts; late results are discarded
- During Chromium decrypt, Cancel is polled between profile walks

**Save** writes the allowlisted keys to `auth.json` and best-effort hardens file permissions (owner-only on Unix; restricted ACL on Windows).

<a id="auth-login-browser"></a>
### Login in Browser (overview)

Both login buttons open a browser, wait for you to sign in, and capture `sess`, `auth_id`, `user-agent`, and `x-bc` automatically. Use **(?)** next to each button for that method’s details.

Shared behavior:
- **Cancel Login** aborts capture, stops polling, and closes the temporary/embedded browser without importing
- Login buttons stay disabled while a login dialog is open (no second session)
- Hard timeout defaults to **10 minutes** (`gui_settings.json` → `auth_login_timeout_min`; `0` disables)

<a id="auth-login-system-browser"></a>
### Login in System Browser

Opens a **temporary copy** of the browser chosen in **Select Browser** (not your everyday profile — you must log in again).

- Works with **any** browser in the dropdown, including Chrome / Edge / Brave on Windows
- The Import Cookies “Linux only” label does **not** apply here
- Credentials are captured from the live session after you log in
- Prefer [Import Cookies](#auth-import-cookies) when you are already logged in on Zen/Firefox (Windows) or any browser (Linux)

**How to use:**
1. Pick a browser in **Select Browser**
2. Click **Login in System Browser…**
3. Log in to OnlyFans in the temporary window
4. When fields show captured, click **Use These Credentials**
5. **Save** on the Authentication page

<a id="auth-login-app-browser"></a>
### Login in App Browser

Opens an **embedded** OnlyFans window inside OF-Scraper (requires `PyQt6-WebEngine`).

```
pip install PyQt6-WebEngine
```

**How to use:**
1. Click **Login in App Browser…**
2. Log in inside the embedded window
3. Watch the footer status chips for each field
4. Click **Use These Credentials**, then **Save**

**Status indicators** in the browser footer:
- **⚠ Not logged in** / **✅ Logged in** — overall state (valid after `auth_id` appears)
- Individual fields (`sess`, `auth_id`, `x-bc`, `user-agent`) show `—` until captured

**If x-bc is missing:**
1. Click **DevTools ↗** in the footer
2. Select the OnlyFans page (not “Service Worker”)
3. Network tab → any `/api2/` request → Request Headers → copy `x-bc`
4. Paste into the manual **x-bc** field at the bottom of the login window

**Linux note:** On KDE Plasma and some compositors the embedded view may look transparent while loading — cosmetic only.

---

<a id="auth-issues"></a>
## Auth Issues

Authentication can be filled several ways ([Authentication](#auth-root)). Work through the steps below in order.

### 1. Prefer a built-in capture method

Try these first (fewer transcription mistakes):

1. **[Import Cookies](#auth-import-cookies)** — if you are already logged into OnlyFans in a supported browser (Zen/Firefox on Windows; any listed browser on Linux).
2. **[Login in System Browser](#auth-login-system-browser)** — temporary real browser window (works with Chrome / Edge / Brave on Windows too).
3. **[Login in App Browser](#auth-login-app-browser)** — embedded window (needs `PyQt6-WebEngine`).

After any successful capture: **Use These Credentials** (if shown) → **Save** → optional **Test Credentials**.

### 2. If built-in options are not working — copy auth manually from your browser

Use this when Import Cookies / System Browser / App Browser fail, hang, leave fields blank, capture the wrong User-Agent, or you hit Windows Chrome Import limits.

1. Open OnlyFans in a normal browser on **this computer**, log in, and go to the **main timeline / home feed** (not a creator page).
2. Open DevTools (**F12** or right-click → Inspect).
3. Open the **Network** tab (not Console / Application alone).
4. In the Network filter box, type **`init`** so only matching requests are shown.
5. **Refresh the page** (F5) while still on the main timeline so new requests appear. Pick a request that hit OnlyFans (for example a `posts?…` / feed call under the `init` filter).
6. Open that request → **Headers** → **Request Headers**, then copy values into **Authentication → [Credentials](#auth-credentials)**:
   - **sess** / **auth_id** / **auth_uid…** — from the **Cookie** header (or Application → Cookies → `onlyfans.com` if easier). Leave `auth_uid*` empty if unused (2FA).
   - **User Agent** — Request Headers → `user-agent` (prefer this over Console `navigator.userAgent` if they differ).
   - **x-bc** — Request Headers → `x-bc`.
7. Click **Save**, then **Test Credentials**.
8. Prefer the same browser/IP you will scrape from (important on a VPS).

Tip: if the Network list is empty after opening DevTools, refresh again with Network open and the **`init`** filter applied.

### 3. “Wrong user” / Test Credentials fails / cryptic Python errors

OnlyFans **Wrong user** (API error **code 301**) means the API does not accept this
`sess` + `auth_id` pair. Typical causes:

- **`sess` and `auth_id` mixed from different logins** (or an old `auth_id` left in the form after re-importing `sess`)
- Session already **invalidated** (including after an earlier Wrong user — OF may clear/replace `sess`)
- **2FA**: `auth_uid*` required but missing, or copied from another account/session
- Less often: User-Agent / `x-bc` not from the same browser request as the cookies

**What you may see in the GUI**

- **Test Credentials** / **Credentials Invalid** explaining Wrong user (code 301), or (older patches) a cryptic line like `'NoneType' object is not subscriptable` when the profile response was empty
- **Unable to Load Models** after **Next** on the scraper flow, with a detailed log line containing `Wrong user` or `400` on `/api2/v2/users/me`

**How to fix**

1. Stay logged into OnlyFans in one browser on this computer.
2. Prefer **Import Cookies** or **Login in System/App Browser**, then **Save**.
3. Or follow **§2** above and copy **`sess` + `auth_id` (+ `auth_uid*` if present) + User-Agent + `x-bc` from the same Network request** after filtering **`init`** and refreshing the main timeline.
4. Click **Save**, then **Test Credentials** again before loading models.
5. Do not keep retrying the same cookies after Wrong user — obtain a fresh set.
6. If credentials test OK but models still fail, continue with **§4** (Dynamic Mode / SSL Verify).

### 4. Credentials look correct but models still will not load

- Try changing **Dynamic Mode** under **Configuration → Advanced** (signing-rules source).
- Try setting **SSL Verify** under **Configuration → Advanced** to **`false`**, then Save and **Retry** loading models. This has helped some users with TLS / certificate / proxy issues. Prefer `custom` or `true` when possible — `false` disables certificate checks and is less secure.
- If you use a VPN, try disabling it or switching endpoints.
- On a VPS, obtain auth from the **same IP** the VPS uses.
- Try a browser you have not used with OnlyFans before (e.g. Firefox or Zen instead of Chrome).
- On Windows Chrome: prefer System/App Browser login or Zen/Firefox Import Cookies instead of Chrome **Import Cookies**.

The **Unable to Load Models** dialog offers shortcuts to Authentication, Dynamic Mode, SSL Verify, and this section.

