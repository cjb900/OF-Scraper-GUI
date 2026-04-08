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
  - [Check Mode](#check-mode-3143-and-3145)
  - [Authentication](#authentication)
  - [Configuration](#configuration)
  - [DRM Key Creation](#drm-key-creation)
  - [Profile Manager](#profile-manager)
  - [Merge Databases](#merge-databases)
  - [Help / README](#help--readme)
- [GUI features](#gui-features)
  - [Application icon](#application-icon)
  - [Theme](#theme)
  - [Verbose Log](#verbose-log)
  - [Context-sensitive help](#context-sensitive-help)
  - [Startup dependency check](#startup-dependency-check)
  - [Auth failure handling](#auth-failure-handling)
  - [Scraper workflow](#scraper-workflow)
  - [Daemon mode](#daemon-mode-auto-repeat-scraping)
  - [Table page](#table-page)
  - [Check mode](#check-mode-3143-and-3145)
  - [Progress bar](#progress-bar)
  - [CLI auto-start](#cli-auto-start)
  - [Scrape individual posts by URL or Post ID](#scrape-individual-posts-by-url-or-post-id-3145)
  - [Discord webhook integration](#discord-webhook-integration)
  - [User Lists](#user-lists-3145-only)
- [Plugin system](#plugin-system-all-versions)
  - [JoyCaption Tagger](#joycaption-tagger-joycaption_tagger-all-versions)
  - [LLM Assistant](#llm-assistant-llm_assistant-all-versions)
  - [Trial Link Scanner](#trial-link-scanner-trial_link_scanner-all-versions)
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
- [Removal / Uninstall Tool](#removal--uninstall-tool)
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

<img src="https://github.com/user-attachments/assets/1c83ce37-e1b3-4e9f-bdc1-8dfedbbffc5d" width="600" alt="Main Window — Select Action">
<img src="https://github.com/user-attachments/assets/7633c9ce-70e6-41c4-9171-c0a81c55dbf4" width="600" alt="Main Window — User List">


The starting point of every scrape. Choose what you want OF-Scraper to do:

- **Download** — download media files from your subscribed creators
  - **User Lists** *(3.14.5 only)* — filter which models are loaded by entering one or more OnlyFans list names (comma-separated). Leave blank to load all subscribed models. Equivalent to `--ul` on the command line.

<!-- Screenshot placeholder: Select Action page showing the User Lists field under "Download content from a user" -->

- **Like/Unlike** — automate liking or unliking posts
- **Metadata** — update your local database without downloading files
- **Check modes** *(3.14.3 and 3.14.5)* (Post Check, Message Check, Paid Check, Story Check) — browse all content for a creator in a table view and selectively download individual items
- **Scrape individual posts by URL or Post ID** *(3.14.5 only)* — download specific posts by pasting OnlyFans post URLs or post IDs directly, bypassing model and area selection entirely

After selecting an action, click **Next** to move on.

---

### Select Content Areas & Filters

<img src="https://github.com/user-attachments/assets/fba80d4a-4e5b-40f1-86bc-73453a63c3bc" width="600" alt="Select Content Areas & Filters">

Choose which types of posts to scrape and apply filters before the scrape begins:

- **Content areas** — Timeline, Messages, Archived, Paid, Stories, Highlights, Pinned, Streams
- **Filters** — narrow by date range, limit post count, skip already-downloaded content, and more
- **Include Post Text** *(3.14.3 and 3.14.5)* — when enabled, the text body of each post is included alongside the downloaded media
- **Daemon Mode** — set a repeat interval (1–1440 minutes) so the scraper runs automatically on a schedule; optional system notification, sound alert, and **@here Discord ping when new content is found**
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
- **Reload Models** *(3.14.5 only)* — a **Reload Models** button appears in the navigation bar after models load, letting you re-fetch the model list without going back to the Select Action page

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

### Check Mode *(3.14.3 and 3.14.5)*

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

> **Note:** DRM key generation is **not supported in Docker**. Use the GUI on a normal host system (Windows/Linux desktop) instead of a container when generating `client_id.bin` and `private_key.pem`.

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

### Application icon
- The GUI displays its own icon in the **title bar**, **taskbar**, and **system tray** instead of the generic Python icon
- On Windows, the correct AppUserModelID is registered so the taskbar groups and identifies the app as OF-Scraper rather than Python

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

### User Lists *(3.14.5 only)*
- On the **Select Action** page, a **User Lists** field appears under "Download content from a user"
- Enter one or more OnlyFans list names (comma-separated) to load only models who are members of those lists
- Leave blank to load all subscribed models (default behavior)
- Equivalent to the `--ul` / `--userlist` CLI flag — also supported for CLI auto-start
- After models load, a **Reload Models** button appears in the navigation bar so you can re-fetch without going back to the start

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
- Optional **@here Discord mention** — when enabled, the Discord scrape summary is prefixed with `@here` only when new content was downloaded in that run. No ping is sent for runs that find nothing new. Requires a Discord webhook to be configured
- A **Stop Daemon** button appears in the toolbar; clicking it gracefully stops the loop after the current run

### Table page
- **Right-click** any cell to instantly filter the table by that cell's value
- Click any **column header** to sort by that column
- The footer shows the current row count and filtered vs total count (e.g. `42 / 1200 rows (filtered)`)
- The toolbar shows a live **Cart: N items** counter as you select rows for download
- **Open Downloads Folder** button in the toolbar — opens the configured `save_location` from your config directly in your file manager
- **New Scrape** button: if scraping is active, confirms cancellation first; optionally resets all options and model selections back to defaults before returning to the start

### Check mode *(3.14.3 and 3.14.5)*
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
- `--ul` user list auto-start *(3.14.5 only)*: `ofscraper --gui --ul testing -a download -o all`
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
- A Discord enable/disable toggle is available on the scrape settings pages (all versions)
- When enabled and a webhook URL is set in Configuration → General, notifications are sent during the scrape
- When the `--discord` flag is also passed on the command line, the CLI value takes precedence

**Notification level selector** *(3.14.5 only)*
- Choose **LOW** (warnings, errors, and run summary only) or **NORMAL** (all events). Defaults to **LOW**
- On first enable, a one-time prompt asks if you want to save `LOW` as the permanent default in `gui_settings.json`
- In 3.14.3 and 3.12.9, Discord always fires at the `NORMAL` level with no selector

**Per-run scrape summary** *(all versions)*

<!-- Screenshot placeholder: Discord message showing the "--- Scrape Results ---" summary -->

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

---

## Plugin system *(all versions)*

OF-Scraper GUI includes an extensible plugin system. Plugins are placed in your ofscraper config directory and are loaded automatically on startup.

**Plugin directory:**
- **Windows:** `C:\Users\<YourUser>\.config\ofscraper\plugins\`
- **Linux/macOS:** `/home/<YourUser>/.config/ofscraper/plugins/`

Each plugin is a subfolder containing at minimum a `main.py` with a `Plugin` class that inherits from `BasePlugin`. Plugins can hook into the following events:

| Hook | When it fires |
| :--- | :--- |
| `on_load()` | When the plugin is first loaded at startup |
| `on_ui_setup(main_window)` | After the GUI window is built *(GUI mode only)* |
| `on_item_downloaded(item_data, file_path)` | Every time a file is saved to disk |
| `on_scrape_start(config, models)` | When a new scrape begins |
| `on_posts_collected(posts, model_username)` | After each batch of posts/messages is collected for a model |
| `on_scrape_complete(stats)` | When the scrape finishes |

Plugins that declare a `requirements.txt` will trigger a one-click dependency install dialog if their packages are missing.

For full documentation on writing plugins see [`ofscraper/plugins/PLUGIN_DEVELOPMENT.md`](OF-Scraper-3.14.5/ofscraper/plugins/PLUGIN_DEVELOPMENT.md).

> **⚠️ Note:** The plugin system itself is stable, but the included plugins are experimental and a work in progress — they may not function perfectly in all environments.

### Available plugins

> **⚠️ Work in progress:** The included plugins are experimental and a work in progress. They may not work 100% reliably. Use them at your own risk and report any issues you encounter.

Two ready-to-use plugins are included. Both are **disabled by default** — enable them by setting `plugin_enabled = 1` in their `main.py`.

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

5. **Configure the plugin** by opening the JoyCaption Tagger settings in the OF-Scraper GUI and setting the ComfyUI URL to `http://localhost:8188` (or your server's IP if running remotely).

**Setup without Docker**

If you already have ComfyUI running locally, install the JoyCaption custom node via ComfyUI Manager, ensure the `llama-joycaption-alpha-two-hf-llava` model is in your ComfyUI `models/LLM/` folder, then point the plugin at your existing ComfyUI URL.

**Plugin settings**

| Setting | Description |
| :--- | :--- |
| ComfyUI URL | URL of your ComfyUI server (default: `http://localhost:8188`). Click **Test** to verify the connection. |
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

#### Trial Link Scanner (`trial_link_scanner`) *(all versions)*

Automatically scans every direct message collected during a scrape for OnlyFans trial/free-trial links (`https://onlyfans.com/<creator>/trial/<token>`), logs all matches to a daily log file, and optionally posts them to your Discord webhook — including any images attached to the message.

**Screenshots**

<table>
<tr>
<td align="center"><img src="https://github.com/user-attachments/assets/5b7e3bab-98aa-4f88-a6ae-1afd1e9dd331" width="600" alt="Help / README"><br><em>Trial Link Scanner plugin page</em></td>
</tr>
</table>

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

| Patch script | OF-Scraper version |
|---|---|
| `patch_ofscraper_3.12.9_gui.py` | 3.12.9 |
| `patch_ofscraper_3.14.3_gui.py` | 3.14.3 |
| `patch_ofscraper_3.14.5_gui.py` | 3.14.5 |

### Feature availability by version

| Feature | 3.12.9 | 3.14.3 | 3.14.5 |
|---|:---:|:---:|:---:|
| Core scraper workflow (download, like/unlike) | ✅ | ✅ | ✅ |
| Authentication, Configuration, Profiles, Merge DBs | ✅ | ✅ | ✅ |
| Daemon mode | ✅ | ✅ | ✅ |
| Discord webhook toggle | ✅ | ✅ | ✅ |
| DRM Key Creation | ✅ | ✅ | ✅ |
| Table page (filters, sort, cart, avatars) | ✅ | ✅ | ✅ |
| CLI auto-start (`--username`, `-a`, `-o`) | ✅ | ✅ | ✅ |
| Check modes (Post / Message / Paid / Story Check) | ❌ | ✅ | ✅ |
| Include Post Text | ❌ | ✅ | ✅ |
| User Lists (`--ul`) + Reload Models | ❌ | ❌ | ✅ |
| Discord notification level selector (LOW / NORMAL) | ❌ | ❌ | ✅ |
| Per-run Discord scrape summary | ❌ | ❌ | ✅ |
| Scrape by URL / Post ID | ❌ | ❌ | ✅ |
| CLI auto-start with `--ul` | ❌ | ❌ | ✅ |
| Plugin system (JoyCaption, LLM Assistant) | ✅ | ✅ | ✅ |

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

## Removal / Uninstall Tool

A standalone removal tool (`uninstall_ofscraper.py`) is included for cleanly removing ofscraper. It detects your install method automatically (uv / pipx / pip) and presents four options:

1. **Just uninstall ofscraper** — removes the package only; config and downloaded content are kept
2. **Just remove the GUI patch** — uninstalls the patched version and reinstalls stock ofscraper from PyPI; your config is kept
3. **Remove ofscraper + all config files** — uninstalls ofscraper and deletes `~/.config/ofscraper/` (includes settings, auth, logs, and databases — everything ofscraper stores outside your download folder)
4. **Purge everything** — uninstalls ofscraper, deletes config, and deletes your downloaded content. The download path is read from `file_options.save_location` in `config.json` **before** the config is deleted, so the correct path is always used regardless of where you saved content

**Run it with:**

```bash
python uninstall_ofscraper.py
```

All destructive options require explicit confirmation before proceeding. The purge option requires two confirmations.

---

## Notes

- A backup of all modified files is saved to your system temp directory before patching
- The `--restore` flag can undo the patch using any previous backup
- PyQt6 is installed automatically via the same package manager used for OF-Scraper (pip/pipx inject/uv)
- This was created with the help of AI and has been tested to the best of my ability. I take no responsibility for any damage or loss of data. Backups are recommended.

## Disclaimer

1. This tool is not affiliated, associated, or partnered with OnlyFans in any way. We are not authorized, endorsed, or sponsored by OnlyFans. All OnlyFans trademarks remain the property of Fenix International Limited.
2. This is a theoretical program only and is for educational purposes. If you choose to use it then it may or may not work. You solely accept full responsibility and indemnify the creator, hosts, contributors and all other involved persons from any and all responsibility.
