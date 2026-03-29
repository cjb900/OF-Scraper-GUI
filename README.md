# OF-Scraper GUI Patch

A self-contained Python script that patches an installed (non-binary) copy of [OF-Scraper](https://github.com/datawhores/OF-Scraper) to add a full **PyQt6 GUI** accessible via the `--gui` flag.

**Supported versions:** `3.12.9`, `3.14.3`, and `3.14.5`

> **Python version requirement**
> Python **3.11.x** or **3.12.x** is required. Python 3.13+ and versions below 3.11 are **not supported** and may cause issues with OF-Scraper or this patch.
> Recommended: [Python 3.11.6](https://www.python.org/downloads/release/python-3116/)

## Table of Contents

- [Usage](#usage)
- [After patching](#after-patching)
- [Pages](#pages)
  - [Scraper — Select Action](#scraper--select-action)
  - [Select Content Areas & Filters](#select-content-areas--filters)
  - [Select Models](#select-models)
  - [Scraper Running](#scraper-running)
  - [Check Mode](#check-mode)
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
  - [Check mode](#check-mode-1)
  - [Progress bar](#progress-bar)
  - [CLI auto-start](#cli-auto-start)
  - [Scrape individual posts by URL or Post ID](#scrape-individual-posts-by-url-or-post-id-3145)
  - [Discord webhook integration](#discord-webhook-integration)
- [Plugin system](#plugin-system)
  - [Included plugins](#included-plugins)
- [Docker](#docker)
  - [Running the GUI in Docker](#running-the-gui-in-docker)
  - [Auto-starting a scrape on container startup](#auto-starting-a-scrape-on-container-startup)
  - [Selecting the patch version at build time](#selecting-the-patch-version-at-build-time)
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
# Basic usage — auto-detect and patch (replace version number as needed)
python patch_ofscraper_3.14.5_gui.py

# Skip confirmation prompt
python patch_ofscraper_3.14.5_gui.py -y

# Dry run — see what would happen without making changes
python patch_ofscraper_3.14.5_gui.py --dry-run

# Specify install path manually
python patch_ofscraper_3.14.5_gui.py --target /path/to/site-packages/ofscraper

# Skip PyQt6 installation (if already installed)
python patch_ofscraper_3.14.5_gui.py --skip-pyqt6

# Restore original files from backup
python patch_ofscraper_3.14.5_gui.py --restore /path/to/backup
```

The same flags apply to `patch_ofscraper_3.14.3_gui.py` and `patch_ofscraper_3.12.9_gui.py`.

## After patching

Launch the GUI with:

```bash
ofscraper --gui
```

The patch script will also offer to launch the GUI for you immediately after a successful patch.

> **Note:** If you run the patch script from inside a source directory (e.g. `OF-Scraper-3.14.5/`), use `python -m ofscraper --gui` from a different directory (e.g. your home directory) to ensure the installed version is used rather than the local source files.

---

## Pages

A visual walkthrough of each page in the GUI.

---

### Scraper — Select Action

<img src="https://github.com/user-attachments/assets/e8fdf3d6-5cb0-4b1b-b968-78ab0070a937" width="600" alt="Main Window — Select Action">

The starting point of every scrape. Choose what you want OF-Scraper to do:

- **Download** — download media files from your subscribed creators
- **Like/Unlike** — automate liking or unliking posts
- **Metadata** — update your local database without downloading files
- **Check modes** (Post Check, Message Check, Paid Check, Story Check) — browse all content for a creator in a table view and selectively download individual items
- **Scrape individual posts by URL or Post ID** *(3.14.5 only)* — download specific posts by pasting OnlyFans post URLs or post IDs directly, bypassing model and area selection entirely

After selecting an action, click **Next** to move on.

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

### Check Mode

<img src="https://github.com/cjb900/OF-Scraper-GUI/blob/main/.github/Screenshots/OF-Scraper-GUI%20-%20Check%20Mode.jpg" width="600" alt="Check Mode table">

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

### Check mode
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
- This is also how the Docker container starts a scrape automatically via the `GUI_ARGS` environment variable (see [Docker](#docker))

---

### Scrape individual posts by URL or Post ID *(3.14.5)*

<!-- Screenshot placeholder: Action page showing "Scrape individual posts by URL or Post ID" selected -->
<!-- Screenshot placeholder: URL input page showing the text box with example URLs/IDs -->

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
- A Discord enable/disable toggle is available on the scrape settings pages
- When enabled and a webhook URL is set in Configuration → General, Discord notifications fire at the `NORMAL` level for all standard log messages during the scrape
- When the `--discord` flag is also passed on the command line, the CLI value takes precedence

**Per-run scrape summary** *(3.14.5)*

<!-- Screenshot placeholder: Discord message showing the "--- Scrape Results ---" summary -->

After each completed scrape run, a summary is automatically posted to your Discord webhook showing only what was downloaded in **that run** (not cumulative totals from the database):

```
--- Scrape Results ---
[creator_username] 12 new downloads [8 videos, 0 audios, 4 photos] | 3 skipped
```

- Shows each creator's name, total new files downloaded, breakdown by type, and skipped count
- Counts reset to zero at the start of each run — if nothing new was downloaded, the summary shows `0 new downloads`
- Works with any Discord level (`--discord low` or higher)
- Requires a webhook URL configured in Configuration → General

---

## Plugin system

OF-Scraper GUI includes an extensible plugin system. Plugins are placed in your ofscraper config directory and are loaded automatically on startup — in both GUI and headless CLI mode.

**Plugin directory:**
- **Windows:** `C:\Users\<YourUser>\.config\ofscraper\plugins\`
- **Linux/macOS:** `/home/<YourUser>/.config/ofscraper/plugins/`

Each plugin is a subfolder containing at minimum a `main.py` with a `Plugin` class that inherits from `BasePlugin`. Plugins can hook into the following events:

| Hook | When it fires |
| :--- | :--- |
| `on_load()` | When the plugin is first loaded at startup |
| `on_ui_setup(main_window)` | After the GUI window is built *(GUI mode only)* |
| `on_item_downloaded(item_data, file_path)` | Every time a file is saved to disk |

Plugins that declare a `requirements.txt` will trigger a one-click dependency install dialog if their packages are missing.

For full documentation on writing plugins see [`ofscraper/plugins/PLUGIN_DEVELOPMENT.md`](OF-Scraper-3.14.5/ofscraper/plugins/PLUGIN_DEVELOPMENT.md).

### Included plugins

Three ready-to-use plugins are included. All are **disabled by default** — enable them by setting `plugin_enabled = 1` in their `main.py`.

#### Intelligent AI Tagger (`ai_tagger`)

<!-- Screenshot placeholder: Smart Gallery sidebar page showing tagged images with tag chips -->

Automatically tags every downloaded image using a local computer-vision model — no cloud API or internet connection required at inference time.

- **Supported models:** WD14 (Danbooru tags), OpenCLIP ViT-B-32 (zero-shot label matching), Florence-2 (generative captions), custom `.safetensors` checkpoints
- **Smart Gallery** sidebar page — browse tagged images, search by tag, and run semantic similarity search
- **Smart Folders** — automatically copy images into subfolders named after their top predicted tag
- Auto-tags images as they are downloaded; can also batch-scan existing folders
- Dependencies: `torch`, `open_clip_torch`, `transformers`, `peewee`, `Pillow` (prompted automatically on first enable)

#### JoyCaption Tagger (`joycaption_tagger`)

<!-- Screenshot placeholder: JoyCaption settings panel showing caption type/length options -->

Sends downloaded images to a [JoyCaption](https://github.com/fpgaminer/joycaption) node running inside ComfyUI (local or Docker) and stores the captions in a local database.

- Configure caption style (Descriptive, Danbooru tag list, Stable Diffusion Prompt, etc.) and length in the plugin settings panel
- Requires a running ComfyUI server with JoyCaption custom nodes — see `docker/comfyui-joycaption/` for a ready-made Docker setup
- No additional Python packages required beyond the base ofscraper environment

#### LLM Assistant (`llm_assistant`)

<!-- Screenshot placeholder: AI Assistant chat panel showing a natural-language command being interpreted -->

Adds a **🤖 AI Assistant** chat panel to the sidebar. Type plain English commands — the assistant translates them into GUI actions such as setting usernames, selecting content areas, and starting downloads.

- Runs a GGUF model locally via `llama-cpp-python` — no Ollama, no cloud API, no internet required at runtime
- Also injects a compact command bar directly into the Action and Area Selector pages
- First launch walks you through model selection and automatic download
- Dependency: `llama-cpp-python` (prompted automatically on first enable)

---

## Docker

A Docker setup is included for running the GUI in a headless environment, accessible from any browser or VNC client — no display required on the host machine.

### Running the GUI in Docker

```bash
# Build the image
docker compose build ofscraper-gui

# Start the container
docker compose up ofscraper-gui
```

Once running, open **[http://localhost:6969/?autoconnect=true&resize=scale](http://localhost:6969/?autoconnect=true&resize=scale)** in your browser to access the GUI via noVNC. You can also connect with any VNC client on port `5900`.

<!-- Screenshot placeholder: noVNC browser view showing the OF-Scraper GUI -->

The `GUI_PATCH_VERSION` build argument and `GUI_ARGS` environment variable in `docker-compose.yml` control which version is used and whether a scrape starts automatically:

```yaml
# docker-compose.yml (key sections)
build:
  args:
    GUI_PATCH_VERSION: "3.14.5"   # which patch to apply at build time
environment:
  - GUI_ARGS=                     # leave blank to just open the GUI
```

### Auto-starting a scrape on container startup

Set `GUI_ARGS` to pass any `ofscraper --gui` arguments. The container will open the GUI and immediately begin scraping with those options — no manual interaction required:

```yaml
environment:
  - GUI_ARGS=--daemon 120 --username ALL --sub-status active --posts all --discord low
```

This is equivalent to running `ofscraper --gui --daemon 120 --username ALL ...` on the command line. The GUI wizard pages are skipped and the scrape starts automatically.

Volumes in `docker-compose.yml` map your host config and download directories into the container so all settings, auth tokens, and downloaded files are stored on the host:

```yaml
volumes:
  - /home/cjb900/.config/ofscraper:/root/.config/ofscraper
  - /home/cjb900/Photos/OnlyFans:/home/cjb900/Photos/OnlyFans
  - /usr/bin/ffmpeg:/usr/bin/ffmpeg:ro
```

### Selecting the patch version at build time

Change `GUI_PATCH_VERSION` in `docker-compose.yml` (or pass it as a build arg) to build a container for a different supported version:

```bash
docker compose build --build-arg GUI_PATCH_VERSION=3.14.3 ofscraper-gui
```

Available versions match the patch scripts: `3.12.9`, `3.14.3`, `3.14.5`.

---

## Supported versions

| Patch script | OF-Scraper version | Notes |
|---|---|---|
| `patch_ofscraper_3.12.9_gui.py` | 3.12.9 | |
| `patch_ofscraper_3.14.3_gui.py` | 3.14.3 | |
| `patch_ofscraper_3.14.5_gui.py` | 3.14.5 | Adds scrape-by-URL, Discord summary, plugin system improvements |

All patch scripts include the same core GUI features. Version-specific additions are noted throughout this document.

## Supported platforms and install methods

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
