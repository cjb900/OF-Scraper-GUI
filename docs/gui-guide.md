[🏠 README](../README.md) · [Install](install.md) · [GUI guide](gui-guide.md) · [Docker](docker.md) · [Plugins](plugins.md) · [Versions](versions.md) · [Troubleshooting](troubleshooting.md)

---

# GUI guide

This guide describes the **3.14.7** patch. Older patches have fewer features; see [Versions](versions.md) for what each one includes.

Every **?** button in the app opens the matching part of the built-in **Help / README** page, which has the full field-by-field reference.

## Getting around

### Application icon
- The GUI displays its own icon in the **title bar**, **taskbar**, and **system tray** instead of the generic Python icon
- On Windows, the correct AppUserModelID is registered so the taskbar groups and identifies the app as OF-Scraper rather than Python

### Theme
- Toggle between **Dark** and **Light** mode using the button at the bottom of the left sidebar
- Theme preference is saved to `gui_settings.json` in your ofscraper config directory
- Left-nav pages use **colored icons** next to each label (Scraper, Authentication, Configuration, …); plugin pages get their own sidebar entry when loaded
- While a model list is loading or a scrape is running, theme changes wait until that work finishes

### About & text size

Click the sidebar version button (e.g. **`v3.14.7`**) — or **Help / README → About** — to open **About OF-Scraper**. Opening it again focuses the same window (it does not stack duplicates).

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/ba6fbb2e-1638-481d-9d6e-6e2159ee1bde" width="600" alt="About">

</details>

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

### Privacy / demo mode

<details><summary>Screenshots</summary>

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

</details>

- Toggle **Privacy** in the bottom of the sidebar for safe screenshots / demos
- Masks auth fields, Save Location / webhook / FFmpeg / CDM paths, model names, and table usernames
- Extra redaction in the console log; preference saved in `gui_settings.json`

### Context-sensitive help
- Every section and option throughout the GUI has a small **?** button next to it
- Clicking a **?** button navigates directly to the matching section in the Help / README page
- Authentication options (Credentials, Import Cookies, System Browser, App Browser) each have dedicated Help sections

### Welcome to OF-Scraper GUI
- An initial start-up window welcoming you to OF-Scraper GUI with brief helpful information
- Shown **before** the Missing FFmpeg/CDM paths dialog so first-run messaging is not buried behind dependency prompts

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/5bc8e9d4-7619-4475-9873-be4f6c14546d" width="600" alt="Welcome to OF_Scraper GUI">

</details>

### Startup dependency check
- On launch (after Welcome when applicable), the GUI checks whether **FFmpeg** and **CDM key paths** are configured
- If either is missing, a notice appears from **Configuration** (and related entry points). On the Areas page, missing paths are shown as a status tip so you can keep configuring while models load
- **Open Config → Download (FFmpeg)** and **Open Config → CDM (Manual keys)** navigate the main window to the relevant config tab
- **Generate DRM Keys** closes the dialog and navigates to the DRM Key Creation page

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/3ad709d5-6bbd-429c-b772-1f75c2217172" width="600" alt="Missing Configuration Paths">

</details>

### Help / README

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/fd82cfcc-6ca4-4fba-9099-e9d1b0515b52" width="600" alt="Help / README">

</details>

Built-in documentation available at any time without leaving the app:

- **Table of contents** with clickable links — each entry scrolls directly to the matching section
- **Jump to…** dropdown for fast navigation to any section by name
- **About** and **Text size** — see [About & text size](#about--text-size); Help toolbar also has **A−** / **A+** / size dropdown / **Reset**
- **Show Welcome** — reopen the first-run welcome tip
- **Additional Help** button links to the project Discord if you need further assistance
- Every **?** button throughout the GUI links directly to the relevant section here
- It is the most detailed reference (every config field, placeholders, troubleshooting). This guide is the overview
- **Auth Issues** walks built-in capture methods first, then **manual DevTools copy** (Network → filter **`init`** → main timeline → refresh → Request Headers) if Import/Login fail, then a **Wrong user / sess–auth_id** section, then Dynamic Mode / SSL Verify and related tips

## Authentication

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/4213c577-1064-4f38-860a-43c6dbfc80bc" width="600" alt="Authentication">

</details>

Manage the credentials OF-Scraper uses to connect to OnlyFans. Each option has a **?** button that jumps to the matching Help section:

- **Credentials** — paste `sess` / `auth_id` / `auth_uid` / user-agent / `x-bc` manually from DevTools
- **Import Cookies** *(recommended when already logged in)* — read allowlisted cookies from the selected browser profile on disk (Zen/Firefox on Windows; any listed browser on Linux). Chrome-family **Import Cookies** is Linux-only on Windows builds
  - **User-Agent** — filled to match the selected browser: live `navigator.userAgent` when the browser is available via remote debugging, otherwise the install / profile Gecko user agent

<details><summary>Screenshots</summary>

<img src="https://github.com/user-attachments/assets/90cb1eec-4f76-46f8-8737-693a3e7836f4" width="600" alt="Import Cookies Dropdown">
<img src="https://github.com/user-attachments/assets/3a825b47-7e8d-4bed-a945-ef132ca01491" width="600" alt="Import Cookies loading">
<img src="https://github.com/user-attachments/assets/2a2cce6a-dea1-443f-9efd-56a50cc9f669" width="600" alt="Imported Cookies">

</details>

- **Login in System Browser…** — opens a temporary copy of any browser from the dropdown (including Chrome on Windows) and captures credentials after you log in

<details><summary>Screenshots</summary>

<img src="https://github.com/user-attachments/assets/b18b70c4-c349-435e-be52-0cb398e980a6" width="600" alt="Login System Browser">
<img src="https://github.com/user-attachments/assets/1c324b6a-e00d-459b-b85a-29dd183a4963" width="600" alt="Login System Browser Credentials captured">
<img src="https://github.com/user-attachments/assets/80ab1b74-a12c-402e-9a5a-4ba085b4e971" width="600" alt="Login System Browser Credentials imported">

</details>

- **Login in App Browser…** — embedded Chromium window inside the app (`PyQt6-WebEngine`)
- Cookie allowlist + restrictive `auth.json` file permissions — only auth cookies/headers are kept; unrelated browser cookies are dropped
- Cancel support for Import Cookies and browser login, plus an optional hard login timeout

If scraping fails with an auth error, the GUI will offer a direct link to jump to this page. Footer **Auth / Config / Key** health chips also surface auth problems at a glance.

### Login in Browser

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/f2d615cc-5064-4caf-afd7-dca6dcbdb574" width="600" alt="Login in App Browser">

</details>

Two ways to capture credentials by logging in (plus Import Cookies / manual paste):

**Login in App Browser…**
- Opens an embedded Chromium window inside the app
- Log in to OnlyFans normally — the GUI watches for session cookies in the background
- All credential fields start blank (`—`); values are revealed only after `auth_id` is confirmed
- **"Use These Credentials"** is only enabled after a valid `auth_id` is confirmed
- `x-bc` is captured automatically; if missing, use DevTools Network tab
- Requires `PyQt6-WebEngine` — `pip install PyQt6-WebEngine` or `pipx inject ofscraper PyQt6-WebEngine`
- **Cancel Login** aborts without importing; optional hard timeout (default 10 minutes)
- The window's **DevTools ↗** button is **off by default**: it needs Chromium remote debugging, and while that is on any program on your computer can control the login window. To use it, start the GUI with `OFSCRAPER_GUI_WEBENGINE_DEBUG=1` (Linux/macOS: `OFSCRAPER_GUI_WEBENGINE_DEBUG=1 ofscraper --gui`; Windows Command Prompt: `set OFSCRAPER_GUI_WEBENGINE_DEBUG=1` first). Turn it off again when you're done, or copy `x-bc` from your normal browser's DevTools instead

**Login in System Browser…**
- Opens a **temporary** copy of whichever browser is selected under **Select Browser** (including Chrome / Edge / Brave on Windows)
- Fresh empty profile — you must log in again; this is not your everyday session
- The Import Cookies “Linux only” limit does **not** apply here
- Prefer Import Cookies when you are already logged in on Zen/Firefox (Windows) or any browser (Linux)

> **KDE Plasma note:** On KDE Plasma / KDE neon the embedded App Browser view may briefly appear blank while the page loads. This is cosmetic — the page loads correctly regardless.

> **Window flashing:** on Windows and Linux the GUI turns on Qt's newer widget renderer (`QT_WIDGETS_RHI=1`) so opening the App Browser doesn't make the whole window flash. If you see drawing problems, start the GUI with `QT_WIDGETS_RHI=0` to turn it off. Docker is not affected.

### Auth failure handling
- When the model list cannot be loaded (auth error), a dialog appears offering:
  - **Retry** — re-fetch models without leaving the page
  - **Go to Authentication** — jump directly to the auth page
  - **Dynamic Mode (Config)** — jump directly to Configuration → Advanced → Dynamic Mode field
  - **SSL Verify (Config)** — jump to Configuration → Advanced → SSL Verify (try **`false`** if credentials are correct but TLS/proxy issues persist; less secure)
  - **Help / README** — navigate to the Auth Issues section of the built-in help
- A **Retry** button also appears inline in the navigation bar
- Dialog text also suggests trying Dynamic Mode and/or SSL Verify → `false` when auth looks correct but model load still fails

## Configuration

Edit all OF-Scraper settings without touching `config.json` directly. Settings are organized into tabs. Each tab’s **?** button jumps to the matching section in the built-in Help page (full field reference, placeholders, and examples).

**Save** and scrape start both validate key settings (Save Location, File Format uniqueness, Directory Format under Save Location, length bounds, FFmpeg path, empty download filters). **Errors block** save/start; **warnings** ask whether to continue.

- **General** — profile name, metadata path, Discord webhook
  - **Main Profile** / **Metadata Path** — default profile and where model DB/metadata files live (supports placeholders)
  - **Discord Webhook URL** — optional; [Discord webhook setup](https://support.discord.com/hc/en-us/articles/228383668-Intro-to-Webhooks). Enable sending from **Select Content Areas → Additional Options** after pasting the URL

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/99b30f74-3a1e-4ee8-94bc-6b523cd3ed81" width="600" alt="Configuration">

</details>

- **File Options** — where files are saved, folder and filename format, date format, text length. *(On Windows, filesystem paths display and save with backslashes; `config.json` stores them as escaped `\\`. Directory/File Format templates still use `/`.)*
  - **Save Location** — root download directory
  - **Directory Format** — folder template under Save Location (must stay **relative**; no absolute paths or `..`). Invalid templates are blocked on Save / scrape start
  - **File Format** — must include a uniqueness token: `{filename}`, `{media_id}`, or `{original_filename}`
  - **Date Format** — Arrow/Moment-style tokens (e.g. `YYYY-MM-DD`); avoid Windows-illegal characters like `:`
  - **Text Length / Space Replacer / Truncation** — caption length in names, space substitution, OS path truncation
  - Full placeholder list: in-app **Help → Configuration → File Options**

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/0c83a457-b49a-4ffb-95b6-7fdc6f90aa07" width="600" alt="File Options">

</details>

- **Download** — free space minimum, auto-resume, post count limit, media type filter (Images / Audios / Videos / Text); **DRM Duration Match %**, Verify All Integrity, FFmpeg path
  - **DRM Duration Match %** (default **98**) — after remux, rejects truncated/empty files vs expected duration (higher = stricter). DRM merges always use this gate; enable **Verify All Integrity** to apply it to non-DRM media too
  - **FFmpeg Path** — required to merge DRM audio/video and for duration checks. FFmpeg **6 or newer** works (including 8). If you run into issues with a version above **7.1.1**, use **7.1.1**
  - Automatic resilience: stall timeout/retry, stricter `.part` finalize, media/DRM host allowlist (`onlyfans.com` / `cloudfront.net` + **Media Host Suffixes**), paths confined under Save Location

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/f9ff5b18-f616-44f2-8014-fcc940c56b93" width="600" alt="Downloads">

</details>

- **Scripts** — optional external scripts under `script_options` in `config.json` (leave paths empty/`null` to disable):
  - **After Action Script** — runs after an action for each model has completed
  - **Post Script** — runs after all actions for all models have completed
  - **Naming Script** — can rewrite the final filename/path before download (disabled by default)
  - **Preferred file extensions** — optional per-type remaps (each type off by default). Check **Images**, **Videos**, and/or **Audios** to replace only that type’s `{ext}` in the saved filename (**no convert/remux**). Settings live under `file_options` (`override_*_extension` + `image_extension` / `video_extension` / `audio_extension`)
  - **After Download Script** — runs after each individual media download completes
  - **Skip Download Script** — runs before a download; return `"False"` or empty stdout to skip that file
  - Older builds used typo key `scripts_options`; current **Save** migrates values into `script_options`

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/ca9e90a8-1429-4089-adbf-2c87a5f665ae" width="600" alt="Scripts">

</details>

- **Performance** — concurrent downloads, thread count, speed limit
  - **Thread Count**, **Download Semaphores** (downloader concurrency), **Download Speed Limit** (KB/s; `0` = unlimited)

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/4575261f-3377-497a-baad-a6d4105e2335" width="600" alt="Performance">

</details>

- **Content** — file size limits, duration limits, ad blocking
  - **Block Ads**; min/max file size (e.g. `500MB`, `2GB`, or `0` for no limit); min/max length in **seconds**

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/71b71f09-e35f-4390-9753-1ff80f6f6ce1" width="600" alt="Content">

</details>

- **CDM** — DRM key mode and key file paths (needed for protected content); new installs default to **manual**; remote modes warn and never send session cookies
  - Prefer **manual** + local `client_id.bin` / `private_key.pem` (use **DRM Key Creation**). Remote modes (`cdrm` / `cdrm2` / `keydb`) are opt-in and may fail on OnlyFans licenses
  - **KeyDB** is currently not working — avoid for now
  - In **manual** mode, if `client-id` or `private-key` is blank or the file is missing, the log shows **one** error saying so and DRM videos are skipped right away (no download, no retries). Videos whose key was saved by an earlier run still download. See [Troubleshooting](troubleshooting.md#drm-videos-are-skipped-or-fail)
  - Existing configs keep their saved key mode (new-install default does not rewrite `config.json`)

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/1745e364-f032-4760-9a1a-c6a0e3b40c3b" width="600" alt="CDM">

</details>

- **Advanced** — dynamic mode, cache mode, download bars, logging options, and more. **OnlyFans API resilience** settings:
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

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/e6d7c171-79e9-404d-8ae6-2cc7ce81d4e2" width="600" alt="Advanced">

</details>

- **Response Type** — customize how content type folders are named
  - Rename aliases for posts / messages / paid / archived / etc. These pair with `{responsetype}` / `{response_type}` in Directory Format

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/277d208c-cfe4-432a-850c-2a4e51841f54" width="600" alt="Response Type">

</details>

- **Overwrites** *(3.12.9 only)* — per-media-type overrides for file format, size limits, and more

Deep field docs, placeholders, and DRM Match % details: in-app **Help / README → Configuration**. Background: [OF-Scraper GitBook](https://of-scraper.gitbook.io/of-scraper).

## DRM keys, profiles and databases

### DRM Key Creation

<details><summary>Screenshots</summary>

<img src="https://github.com/user-attachments/assets/cedb95a7-0aa7-4f1b-97cb-17e71cc3175b" width="600" alt="DRM Key Creation">
<img src="https://github.com/user-attachments/assets/71750dba-0777-4c4a-b5c6-3228caea5bdf" width="600" alt="DRM Key Created">
<img src="https://github.com/user-attachments/assets/f862e757-df08-444a-95de-65010bfe6def" width="600" alt="DRM Key Creation Clean up">

</details>

A built-in tool for generating the DRM decryption keys required to download protected (DRM-locked) content. You need these keys if you want to download videos that are encrypted with Widevine DRM.

> **Note:** DRM key generation is **not supported in Docker**. Use the GUI on a normal host system (Windows/Linux desktop) instead of a container when generating `client_id.bin` and `private_key.pem`.

- **Fully automated** — downloads the Android SDK, sets up an emulator, and extracts the keys without any manual steps
- **Streams output** directly into the app so you can follow progress in real time — the Generate Keys button and live console are at the top of the page; Requirements & Information sits below the console
- **Auto-configures** — once keys are generated, the CDM key paths in your config are updated automatically. No need to edit `config.json` manually
- **Virtualization checks** — checks that CPU virtualization / Hyper-V is available before running the Android emulator used for key extraction
- Accessible from the sidebar or via the quick link in the startup notice if CDM keys are not yet configured

> The key extraction process can take 10–90 minutes depending on your hardware. A progress log is shown throughout.

### Profile Manager

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/003fe840-0604-4c58-b16d-05c496639718" width="600" alt="Profile Manager">

</details>

Profiles let you maintain completely separate configurations and credentials — useful if you manage multiple accounts or want different download settings for different use cases.

- **Create** a new profile with a custom name
- **Rename** or **delete** existing profiles
- **Switch** between profiles — the active profile is shown in the navigation bar
- Each profile has its own `auth.json` and data directory

### Merge Databases

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/c7916662-5dc8-4f7d-a81a-47a136f93643" width="600" alt="Merge Database">

</details>

Merge data from one OF-Scraper database into another. This is useful if you have downloaded content across multiple profiles or machines and want to consolidate your records.

- Select a **source database** (the one to merge from)
- Select a **target database** (the one to merge into)
- Duplicate records are handled automatically — only new entries are added

## Running a scrape

The usual flow is **Select Action → Select Content Areas & Filters → Select Models → Scraping page → Start Scraping >>** (with an optional **Confirm scrape** review).

- Models load from the API in the background while you set options on the Areas page; an inline progress indicator shows loading state
- Filters set on the Areas page carry over to the Scraping page sidebar when models are confirmed
- The **Username filter** on the Areas page pre-narrows the model list

### Select Action

<details><summary>Screenshots</summary>

<img src="https://github.com/user-attachments/assets/e7c590a6-3b05-4e93-9d8c-f35eb673aa46" width="600" alt="Main Window — Select Action">
<img src="https://github.com/user-attachments/assets/98ef9690-5594-4ff8-b5e0-222e7fe53525" width="600" alt="Main Window — User List">

</details>

The starting point of every scrape. Choose what you want OF-Scraper to do:

- **Download** — download media files from your subscribed creators
  - **User Lists** — enter one or more OnlyFans list names (comma-separated) to load only the models on those lists. Leave blank to load all subscribed models. Equivalent to `--ul` / `--userlist` (also works for [CLI auto-start](#cli-auto-start))
- **Like/Unlike** — automate liking or unliking posts
- **Update metadata** — bring your database up to date without downloading; see [below](#update-metadata-no-downloads)
- **Download all purchased content (all creators)** — everything you've bought, from every creator; see [below](#download-all-purchased-content-all-creators)
- **Check modes** (Post Check, Message Check, Paid Check, Story Check) — browse all content for a creator in a table and pick what to download; see [Check Mode](#check-mode)
- **Scrape individual posts by URL or Post ID** — paste post URLs or IDs, skipping model and area selection; see [below](#scrape-individual-posts-by-url-or-post-id)

After selecting an action, click **Next** to move on. After models load, a **Reload Models** button in the navigation bar re-fetches them without going back to the start.

#### Update metadata (no downloads)

Updates the database for the chosen models and areas **without downloading anything**. Use it after moving or restoring your download folder, or when files you already have show as not downloaded. Equivalent to `ofscraper metadata`.

- **Mode**
  - **Update** (recommended, `-md update`) — files already on disk are marked as downloaded (with their current filenames), then post info is refreshed from the API
  - **Check** (`-md check`) — only refreshes post info; download status and filenames are not changed
  - **Complete** (`-md complete`) — marks **everything** in the chosen areas as downloaded, even media not on disk, so later downloads skip it (asks you to confirm)
- **Mark unmatched media as locked** (`--mark-stray-locked`) — media the API no longer returns for the chosen areas is marked as locked
- **Check file hashes this run** — reads every matching file and stores its hash, for this run only. Slower on large folders

Pick areas and models as usual. The run happens once (no daemon); when it finishes, the table reloads so the Downloaded column shows the new status.

#### Download all purchased content (all creators)

Downloads everything you have bought (PPV messages and paid posts) from **every** creator, including expired subscriptions and deleted accounts that can't be picked on the Models page.

- **Exclude creators** — usernames to skip, comma-separated (`--excluded-username`). **Pick…** lists the creators OF-Scraper knows about
- **Media types** — Images / Videos / Audios

The Areas and Models pages are skipped; the run starts when you click **Next** (after the usual confirmations). If one creator can't be prepared, the log shows a **WARNING** with that creator's name and the reason, and the others still run. The older **Scrape entire paid page** checkbox on the Areas page is different: it only covers the models you select.

#### Scrape individual posts by URL or Post ID

<details><summary>Screenshots</summary>

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

</details>

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

### Select Content Areas & Filters

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/bd4c6ed1-7b4a-44f9-a81e-7b14168d64c4" width="600" alt="Select Content Areas & Filters">

</details>

Choose which types of posts to scrape and apply filters before the scrape begins:

- **Content areas** — Profile, Timeline, Pinned, Archived, Highlights, Stories, Messages, Purchased, Streams, Labels
- **Post Date Range** — filter content by post date using independent **After** and **Before** controls; each side can be enabled or disabled independently:
  - **Fixed date** — pick a specific calendar date with the date picker
  - **Relative** — enter a number + unit (e.g. *7 days ago*); the date is computed fresh at each scrape run so saved relative settings always mean the last N days
  - Equivalent to the `--after` / `--before` CLI flags
- **Media type filter** — limit the scrape to Images, Videos, and/or Audios
- **Post count limit** — cap the number of posts fetched per creator
- **Rescrape everything** — force a full history scan, ignoring the "start after last seen" cache; use this after changing filters or to do a complete rebuild
- **Include Post Text** — when enabled, the text body of each post is included alongside the downloaded media
- **Video quality** — choose **Default**, **240**, **720**, or **source**; equivalent to the `-q` / `--quality` CLI flag
- **Daemon Mode** — set a repeat interval (1–1440 minutes) so the scraper runs automatically on a schedule; optional system notification, sound alert, and **@here Discord ping when new content is found**
- **Allow duplicates** — when enabled, keep multiple copies of the same `media_id` across posts/areas. Optional sub-option: **Also keep Messages + Purchased copies of the same media** (default off) — collapses Messages↔Purchased/Paid to Messages only while still keeping other area reposts
- **Username filter** — pre-filter the model list to only show specific creators

Once you're happy with your selections, click **Next** to load and choose your models.

Settings on this page are **not saved automatically**. Use the buttons in the lower-right of the navigation bar to manage persistence:
- **Save Settings** — saves the current selections to `gui_settings.json` so they are restored on the next launch (shows a confirmation dialog before saving)
- **Reset Settings** — clears all saved area settings and restores every option to its default state (shows a confirmation dialog before resetting — defaults to No to prevent accidental clears)

### Select Models

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/2cec0d50-a4a8-4180-8202-bde316003406" width="600" alt="Select Models">

</details>

A searchable, filterable table of all creators you are subscribed to. From here you can:

- **Search** by username, display name, or any column
- **Right-click** any cell to instantly filter the table by that value
- **Sort** by clicking any column header
- **Select** individual creators or use Select All / Select None
- **Click a username** — toggles that model's checkbox (avatar click still opens OnlyFans without changing selection)
- **Show Avatars** — toggle to display each creator's profile picture alongside their name in the table. Clicking an avatar opens that creator's OnlyFans page in your browser
- The footer shows how many rows are displayed vs the total (e.g. `42 / 1200 rows (filtered)`)
- **Reload Models** — a **Reload Models** button appears in the navigation bar after models load, letting you re-fetch the model list without going back to the Select Action page

Click **Next >>** when you have selected the creators you want to process. That opens the **Scraping page** (media table), where you review filters and start the job.

### Scraping page

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/0d04b396-9ae2-40db-a29e-c40bf6f55f7a" width="600" alt="Scraping page — media table">

</details>

The main scrape workspace after models are selected. Until you press **Start Scraping >>**, the table may show **Ready to scrape** with guidance to begin fetching media for your selected models and areas.

**Toolbar**
- **Filters** — show/hide the left filter sidebar (collapsible; remembers width)
- **Reset** / **Apply Filters** — clear or apply table filters
- **Start Scraping >>** — begin the scrape for the selected models/areas (may open **Confirm scrape** first — see below)
- **New Scrape** — return to the start of the wizard (asks to cancel first if a run is active)
- **Open Downloads Folder** — opens your configured Save Location in the file manager
- **History** — recent scrape / check runs (Details, Re-run, delete)
- **Export CSV** — export visible (or selected) rows; respects Privacy mode usernames
- Check-mode-only cart actions (**Select All**, **Add Selected**, **>> Send Downloads**) appear only in check modes

**While a scrape runs**
- **Log panel** — streams OF-Scraper output in real time
- **Progress bar** (footer) — overall download progress and a running total of bytes downloaded. The byte count only ever goes up during a run and resets when a new scrape starts
- **Cart counter** (toolbar) — items queued for download (especially useful in check mode)
- **Cancel** — cooperative stop (API pagination, mid-file chunks, and between models); shows **Cancelling…** until the worker exits
- **Per-model badge bar** — live status chips above the table
- **Scrape summary** — at the end of each run, a TUI-style summary in the log: per-model action line plus **GLOBAL RUN TOTALS** (items, data transferred, videos/audios/images, skipped, failed)

**Table**
- **Filter sidebar** — text search, media type, response type, downloaded/unlocked status, post date range, duration, price, IDs, and more. Click **◀ Filters** to hide it and give the table the full width; **▶ Filters** brings it back at the same width
- **Filter presets** — save / save as / rename / delete named filter sets; last-used restored on startup
- **Sort** by clicking a column header; **right-click** a cell to filter by that value
- **Column layout** — remembered width / order / visibility; **sticky columns** keep Number / Download Cart (and optionally UserName) visible while scrolling sideways
- **Click Post ID / Media ID** — opens the OnlyFans post in your browser
- **Duplicate column** (between **Downloaded** and **Unlocked**) — when the same `media_id` appears more than once (e.g. a post in both Timeline and Archived), every copy after the first shows **Duplicate** in orange; the download pipeline skips it. With **Allow duplicates** off (the default), those rows also show `Downloaded: False`
- The footer shows the row count, filtered vs total (e.g. `42 / 1200 rows (filtered)`)
- An empty-table overlay explains what to do when no rows are visible

<details><summary>Screenshots</summary>

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

</details>

#### Status strip and health chips

<details><summary>Screenshots (before, during and after a scan)</summary>

**Before scan**

<img src="https://github.com/user-attachments/assets/3f7e2241-1dbc-45f1-93ab-ea735e9a76c5" width="100%" alt="Status Strip Before Scan">

**During scan**

<img src="https://github.com/user-attachments/assets/53770370-5d6c-4830-9e35-cf25294ff74b" width="100%" alt="Status Strip During Scan">

**Scan finished**

<img src="https://github.com/user-attachments/assets/acc32487-ef11-4796-b06a-1d973f9eeb3b" width="100%" alt="Status Strip Scan Finished">

</details>

- Unified footer: phase badge (Ready / Running / Cancelling / Daemon / Complete), status text, progress, row count
- Live **elapsed timer** while a scrape is running
- Clickable **Auth**, **Config**, and **Key** health chips (green / orange / red) — hover for detail; click to open the matching settings page
- Live **per-model badge bar** above the table during scrapes
- After a run, a **Download failures** dialog lists failed items (filter table / add to cart in check mode)
- Console panel **height is remembered** across relaunch / returning to the scrape page

### Confirm scrape (pre-start review)

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/e66b13cf-45a1-491f-a91c-52cf3a2d3283" width="600" alt="Confirm scrape — Review this scrape before starting">

</details>

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

Related prompts on the same page: **disk space** check against Save Location before start, and **Confirm downloads** when a check-mode cart has 25+ items (see [Safer cancel and confirms](#safer-cancel-and-confirms)).

#### Safer cancel and confirms

- **Cancel** shows a Cancelling… state and cooperatively stops API pagination, mid-file chunk downloads, and between models — not only between queued media items
- **Confirm downloads** when the check-mode cart has 25+ items
- **Disk space check** before scrape / Send Downloads against Save Location
- **Config validation** on Save and before scrape (File Format uniqueness tokens, Directory Format under Save Location, FFmpeg path, etc.)

### Check Mode

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/9f50a722-4f76-40cb-8367-ab5f2dbe1b1d" width="600" alt="Check Mode table">

</details>

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

## Automation and notifications

### Daemon mode (auto-repeat scraping)
- Enable from **Select Content Areas & Filters → Daemon Mode**
- Sets an interval (1–1440 minutes) for repeated scraping runs
- While waiting between runs, a **countdown timer** is shown in the table toolbar with wall-clock ETA
- **Last-run chip** between cycles shows downloads / fails / size from the previous cycle
- Optional **system tray notification** when each run starts (all platforms)
- Optional **sound alert** when each run starts (Windows)
- Optional **@here Discord mention** — when enabled, the Discord scrape summary is prefixed with `@here` only when new content was downloaded in that run. No ping is sent for runs that find nothing new. Requires a Discord webhook to be configured
- A **Stop Daemon** button appears in the toolbar; clicking it gracefully stops the loop after the current run

### Stopping or waking from outside (Linux / macOS)
- `kill <pid>` (SIGTERM) on the GUI cancels the current scrape and quits cleanly; `docker stop` does the same in Docker
- The command-line daemon (`ofscraper --daemon <minutes> …`) also stops cleanly on SIGTERM, the same way as Ctrl+C
- `kill -USR1 <pid>` on the command-line daemon starts the next run right away when it is waiting between runs (ignored while a run is in progress). In Docker: `docker kill --signal=USR1 ofscraper-gui`
- Windows has no equivalent signals; use **Stop Daemon** or Ctrl+C

### CLI auto-start
- If launched with `ofscraper --gui` together with action, area, and username flags, the GUI wizard is skipped and scraping begins automatically — matching the TUI behavior for scripted/automated workflows
- `--ul` user list auto-start: `ofscraper --gui --ul testing -a download -o all`
- Unattended CLI / Docker `GUI_ARGS` auto-start skips interactive scrape-confirm / disk / remote-key dialogs so a container can start without a click
- This is also how the Docker container starts a scrape automatically via the `GUI_ARGS` environment variable (see [Docker](docker.md))

### Discord webhook integration

The GUI includes a Discord webhook toggle that controls whether scraping activity is posted to your configured Discord channel.

**Discord toggle (GUI)**
- A Discord enable/disable toggle is available on the scrape settings pages (all versions)
- When enabled and a webhook URL is set in Configuration → General, notifications are sent during the scrape
- When the `--discord` flag is also passed on the command line, the CLI value takes precedence

**Notification level selector**
- Choose **LOW** (warnings, errors, and run summary only) or **NORMAL** (all events). Defaults to **LOW**
- On first enable, a one-time prompt asks if you want to save `LOW` as the permanent default in `gui_settings.json`
- In 3.14.3 and 3.12.9, Discord always fires at the `NORMAL` level with no selector

**Per-run scrape summary**

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

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/85312a79-061b-4ee6-8520-1439ebd39cc6" width="600" alt="Discord @here">

</details>

## Download integrity and security

- **DRM Duration Match %** (default 98%) — reject empty/tiny muxes and files whose playback duration is too short vs expected; failed checks delete the bad file for retry
- Download stall watchdog and stricter `.part` finalize (Content-Range aware resume)
- Media / DRM / license URLs must use allowlisted hosts (`onlyfans.com`, `cloudfront.net`; extend via Configuration → Advanced → **Media Host Suffixes** or `OFSC_MEDIA_HOST_SUFFIXES`)
- Download paths confined under Save Location (and temp root for `.part` files)
- Remote Key Mode (`cdrm` / `cdrm2` / `keydb`) warnings; new installs default to **manual** CDM; remote helpers never send session cookies
- About / sidebar version check against PyPI; first-run welcome for `--gui` and plugins
- **API resilience** (Configuration → Advanced) — **API Path**, **Manual Dynamic Rules**, **Dynamic Rules URL**, **API Endpoint Overrides**, and **Media Host Suffixes** so many OnlyFans signing/path/CDN breaks can be handled from config without a code patch (see [Configuration](#configuration))
