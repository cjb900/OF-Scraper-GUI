# OF-Scraper GUI Patch

A self-contained Python script that patches an installed (non-binary) copy of [OF-Scraper](https://github.com/datawhores/OF-Scraper) to add a full **PyQt6 GUI** accessible via the `--gui` flag.

**Supported versions:** `3.12.9` and `3.14.3`

## Table of Contents

- [Usage](#usage)
- [After patching](#after-patching)
- [Pages](#pages)
  - [Scraper — Select Action](#scraper--select-action)
  - [Select Content Areas & Filters](#select-content-areas--filters)
  - [Select Models](#select-models)
  - [Scraper Running](#scraper-running)
  - [Authentication](#authentication)
  - [Configuration](#configuration)
  - [DRM Key Creation](#drm-key-creation)
  - [Profile Manager](#profile-manager)
  - [Merge Databases](#merge-databases)
  - [Help / README](#help--readme)
- [GUI features](#gui-features)
  - [Theme](#theme)
  - [Verbose Log](#verbose-log)
  - [Context-sensitive help](#context-sensitive-help)
  - [Startup dependency check](#startup-dependency-check)
  - [Auth failure handling](#auth-failure-handling)
  - [Scraper workflow](#scraper-workflow)
  - [Daemon mode](#daemon-mode-auto-repeat-scraping)
  - [Table page](#table-page)
  - [Progress bar](#progress-bar)
  - [CLI auto-start](#cli-auto-start)
- [Supported versions](#supported-versions)
- [Supported platforms and install methods](#supported-platforms-and-install-methods)
  - [Platform notes](#platform-notes)
  - [Python version](#python-version)
- [How it detects your installation](#how-it-detects-your-installation)
  - [Broken installation detection](#broken-installation-detection)
- [If OF-Scraper is not detected](#if-of-scraper-is-not-detected)
- [Notes](#notes)
- [Disclaimer](#disclaimer)

## Usage

```bash
# Basic usage — auto-detect and patch (replace with 3.14.3 for the newer version)
python patch_ofscraper_3.12.9_gui.py

# Skip confirmation prompt
python patch_ofscraper_3.12.9_gui.py -y

# Dry run — see what would happen without making changes
python patch_ofscraper_3.12.9_gui.py --dry-run

# Specify install path manually
python patch_ofscraper_3.12.9_gui.py --target /path/to/site-packages/ofscraper

# Skip PyQt6 installation (if already installed)
python patch_ofscraper_3.12.9_gui.py --skip-pyqt6

# Restore original files from backup
python patch_ofscraper_3.12.9_gui.py --restore /path/to/backup
```

The same flags apply to `patch_ofscraper_3.14.3_gui.py`.

## After patching

Launch the GUI with:

```bash
ofscraper --gui
```

The patch script will also offer to launch the GUI for you immediately after a successful patch.

> **Note:** If you run the patch script from inside the `OF-Scraper-3.12.9/` or `OF-Scraper-3.14.3/` source directory, use `python -m ofscraper --gui` from a different directory (e.g. your home directory) to ensure the installed version is used rather than the local source files.

---

## Pages

A visual walkthrough of each page in the GUI.

---

### Scraper — Select Action

<img src="https://github.com/cjb900/OF-Scraper-GUI/blob/main/.github/Screenshots/OF-Scraper-GUI%20Select%20Action.jpg" width="600" alt="Main Window — Select Action">

The starting point of every scrape. Choose what you want OF-Scraper to do:

- **Download** — download media files from your subscribed creators
- **Like/Unlike** — automate liking or unliking posts
- **Metadata** — update your local database without downloading files

After selecting an action, click **Next** to move on to selecting content areas and filters.

---

### Select Content Areas & Filters

<img src="https://github.com/cjb900/OF-Scraper-GUI/blob/main/.github/Screenshots/OF-Scraper-GUI%20-%20Select%20Content%20Areas%20and%20Filters.jpg" width="600" alt="Select Content Areas & Filters">

Choose which types of posts to scrape and apply filters before the scrape begins:

- **Content areas** — Timeline, Messages, Archived, Paid, Stories, Highlights, Pinned, Streams
- **Filters** — narrow by date range, limit post count, skip already-downloaded content, and more
- **Daemon Mode** — set a repeat interval (1–1440 minutes) so the scraper runs automatically on a schedule
- **Username filter** — pre-filter the model list to only show specific creators

Once you're happy with your selections, click **Next** to load and choose your models.

---

### Select Models

<img src="https://github.com/cjb900/OF-Scraper-GUI/blob/main/.github/Screenshots/OF-Scraper-GUI%20-%20Select%20Models.jpg" width="600" alt="Select Models">

A searchable, filterable table of all creators you are subscribed to. From here you can:

- **Search** by username, display name, or any column
- **Right-click** any cell to instantly filter the table by that value
- **Sort** by clicking any column header
- **Select** individual creators or use Select All / Select None
- **Show Avatars** — toggle to display each creator's profile picture alongside their name in the table. Clicking an avatar opens that creator's OnlyFans page in your browser
- The footer shows how many rows are displayed vs the total (e.g. `42 / 1200 rows (filtered)`)

Click **Start Scrape** when you have selected the creators you want to download from.

---

### Scraper Running

<img src="https://github.com/cjb900/OF-Scraper-GUI/blob/main/.github/Screenshots/OF-Scraper-GUI%20-%20Scraper%20Running.jpg" width="600" alt="Scraper Running">

Shows live output from the scraper while it runs:

- **Log panel** — streams all output from OF-Scraper in real time so you can see what is happening
- **Progress bar** (footer) — shows overall download progress and a running total of bytes downloaded. The bytes counter only ever increases — it never drops back down mid-scrape
- **Cart counter** (toolbar) — shows how many items are queued for download
- **Open Downloads Folder** button — opens your configured download folder directly in File Explorer
- **Stop / New Scrape** buttons — stop the current run or start fresh

---

### Authentication

<img src="https://github.com/cjb900/OF-Scraper-GUI/blob/main/.github/Screenshots/OF-Scraper-GUI%20-%20Authentication.jpg" width="600" alt="Authentication">

Manage the credentials OF-Scraper uses to connect to OnlyFans:

- **Import cookies** directly from your browser (Chrome, Firefox, Edge, Brave, and more) — no manual copying needed
- **Auto-detect User Agent** — automatically fills in the correct user agent string for your browser
- **Edit credentials manually** if you prefer to paste them in yourself
- All credentials are saved to your `auth.json` file

If scraping fails with an auth error, the GUI will offer a direct link to jump to this page.

---

### Configuration

<img src="https://github.com/cjb900/OF-Scraper-GUI/blob/main/.github/Screenshots/OF-Scraper-GUI%20-%20Configuration.jpg" width="600" alt="Configuration">

Edit all OF-Scraper settings without touching `config.json` directly. Settings are organized into tabs:

- **General** — profile name, metadata path, Discord webhook
- **File Options** — where files are saved, folder and filename format, date format, text length
- **Download** — free space minimum, auto-resume, post count limit, media type filter (Images / Audios / Videos / Text)
- **Performance** — concurrent downloads, thread count, speed limit
- **Content** — file size limits, duration limits, ad blocking
- **CDM** — DRM key mode and key file paths (needed for protected content)
- **Advanced** — dynamic mode, cache mode, download bars, logging options, and more
- **Response Type** — customize how content type folders are named
- **Overwrites** *(3.12.9 only)* — per-media-type overrides for file format, size limits, and more

Each tab has a **?** button that jumps to the matching section in the built-in Help page. Click **Save** to write changes back to `config.json`.

---

### DRM Key Creation

<img src="https://github.com/cjb900/OF-Scraper-GUI/blob/main/.github/Screenshots/OF-Scraper-GUI%20-%20DRM.jpg" width="600" alt="DRM Key Creation">

A built-in tool for generating the DRM decryption keys required to download protected (DRM-locked) content. You need these keys if you want to download videos that are encrypted with Widevine DRM.

- **Fully automated** — downloads the Android SDK, sets up an emulator, and extracts the keys without any manual steps
- **Streams output** directly into the app so you can follow progress in real time
- **Auto-configures** — once keys are generated, the CDM key paths in your config are updated automatically. No need to edit `config.json` manually
- Accessible from the sidebar or via the quick link in the startup notice if CDM keys are not yet configured

> The key extraction process can take 10–90 minutes depending on your hardware. A progress log is shown throughout.

---

### Profile Manager

<img src="https://github.com/cjb900/OF-Scraper-GUI/blob/main/.github/Screenshots/OF-Scraper-GUI%20-%20Profile.jpg" width="600" alt="Profile Manager">

Profiles let you maintain completely separate configurations and credentials — useful if you manage multiple accounts or want different download settings for different use cases.

- **Create** a new profile with a custom name
- **Rename** or **delete** existing profiles
- **Switch** between profiles — the active profile is shown in the navigation bar
- Each profile has its own `auth.json` and data directory

---

### Merge Databases

<img src="https://github.com/cjb900/OF-Scraper-GUI/blob/main/.github/Screenshots/OF-Scraper-GUI%20-%20Merge%20Databases.jpg" width="600" alt="Merge Databases">

Merge data from one OF-Scraper database into another. This is useful if you have downloaded content across multiple profiles or machines and want to consolidate your records.

- Select a **source database** (the one to merge from)
- Select a **target database** (the one to merge into)
- Duplicate records are handled automatically — only new entries are added

---

### Help / README

<img src="https://github.com/cjb900/OF-Scraper-GUI/blob/main/.github/Screenshots/OF-Scraper-GUI%20-%20Help.jpg" width="600" alt="Help / README">

Built-in documentation available at any time without leaving the app:

- **Table of contents** with clickable links — each entry scrolls directly to the matching section
- **Jump to…** dropdown for fast navigation to any section by name
- **Additional Help** button links to the project Discord if you need further assistance
- Every **?** button throughout the GUI links directly to the relevant section here

---

## GUI features

### Theme
- Toggle between **Dark** and **Light** mode using the button in the bottom-left navigation bar
- Theme preference is saved to `gui_settings.json` in your ofscraper config directory

### Verbose Log
- Toggle **Verbose Log** mode using the button in the bottom-left navigation bar (below the Theme button)
- When enabled, all log levels are shown in the in-app log panel and a dedicated verbose log file is written to your ofscraper config directory (e.g. `ofscraper_gui_verbose_<profile>_<timestamp>.log`)
- Verbose logging is disabled by default and the preference is saved to `gui_settings.json`

### Context-sensitive help
- Every section and option throughout the GUI has a small **?** button next to it
- Clicking a **?** button navigates directly to the matching section in the Help / README page

### Startup dependency check
- On launch, the GUI checks whether **FFmpeg** and **CDM key paths** are configured
- If either is missing, a notice pops up with quick links to jump directly to the relevant config fields or to the DRM Key Creation page

### Auth failure handling
- When the model list cannot be loaded (auth error), a dialog appears offering:
  - **Retry** — re-fetch models without leaving the page
  - **Go to Authentication** — jump directly to the auth page
  - **Dynamic Mode (Config)** — jump directly to Configuration → Advanced → Dynamic Mode field
  - **Help / README** — navigate to the Auth Issues section of the built-in help
- A **Retry** button also appears inline in the navigation bar

### Scraper workflow
- **Area Selector page**: models are loaded from the API in the background while you configure options; an inline progress indicator shows loading state
- Filters configured on the Area Selector page are automatically carried over to the Table page sidebar when models are confirmed
- **Username filter** on the Area Selector page pre-narrows the Model Selector list

### Daemon mode (auto-repeat scraping)
- Enable from **Select Content Areas & Filters → Daemon Mode**
- Sets an interval (1–1440 minutes) for repeated scraping runs
- While waiting between runs, a **countdown timer** is shown in the table toolbar
- Optional **system tray notification** when each run starts (all platforms)
- Optional **sound alert** when each run starts (Windows)
- A **Stop Daemon** button appears in the toolbar; clicking it gracefully stops the loop after the current run

### Table page
- **Right-click** any cell to instantly filter the table by that cell's value
- Click any **column header** to sort by that column
- The footer shows the current row count and filtered vs total count (e.g. `42 / 1200 rows (filtered)`)
- The toolbar shows a live **Cart: N items** counter as you select rows for download
- **Open Downloads Folder** button in the toolbar — opens the configured `save_location` from your config directly in your file manager
- **New Scrape** button: if scraping is active, confirms cancellation first; optionally resets all options and model selections back to defaults before returning to the start

### Progress bar
- A compact progress bar in the footer shows overall download progress and a running total of bytes downloaded
- The bytes counter is **monotonically increasing** — it only ever goes up during a session and never drops back down mid-scrape
- Resets automatically when a new scrape is started

### CLI auto-start
- If launched with `ofscraper --gui` together with action, area, and username flags, the GUI wizard is skipped and scraping begins automatically — matching the TUI behavior for scripted/automated workflows

## Supported versions

| Patch script | OF-Scraper version |
|---|---|
| `patch_ofscraper_3.12.9_gui.py` | 3.12.9 |
| `patch_ofscraper_3.14.3_gui.py` | 3.14.3 |

Both patch scripts include identical GUI features.

## Supported platforms and install methods

| Platform | pip | pipx | uv |
|----------|:---:|:----:|:--:|
| Windows  | ✅  | ✅   | ✅ |
| Linux (Debian-based) | ❌  | ✅   | ✅ |
| Mac OS   | ❌ | ❌  | ❌ |
| Docker   | ❌ | ❌  | ❌ |
* ❌ not tested

### Platform notes

- **Windows**: Tested on **Windows 11** but should work on Windows 10 and other versions
- **Linux**: Only **Debian-based** distributions are supported (Ubuntu, Debian, Linux Mint, KDE Neon, Pop!_OS, etc.). Other distributions (Arch, Fedora, etc.) have not been tested and may require additional setup
- **Mac**: Mac OS has not been tested with this GUI patch
- **Docker**: Not tested

### Python version

- **Supported**: Python **3.11.x** and **3.12.x**
- **Recommended**: Python **3.11.6** ([download here](https://www.python.org/downloads/release/python-3116/))
- Python versions below 3.11 or 3.13+ are **not supported** and may cause issues with OF-Scraper or this patch
- The patch script will warn you if an unsupported Python version is detected

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

## Notes

- A backup of all modified files is saved to your system temp directory before patching
- The `--restore` flag can undo the patch using any previous backup
- PyQt6 is installed automatically via the same package manager used for OF-Scraper (pip/pipx inject/uv)
- This was created with the help of AI and has been tested to the best of my ability. I take no responsibility for any damage or loss of data. Backups are recommended.

## Disclaimer

1. This tool is not affiliated, associated, or partnered with OnlyFans in any way. We are not authorized, endorsed, or sponsored by OnlyFans. All OnlyFans trademarks remain the property of Fenix International Limited.
2. This is a theoretical program only and is for educational purposes. If you choose to use it then it may or may not work. You solely accept full responsibility and indemnify the creator, hosts, contributors and all other involved persons from any and all responsibility.
