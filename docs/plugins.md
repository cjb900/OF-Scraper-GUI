[🏠 README](../README.md) · [Install](install.md) · [GUI guide](gui-guide.md) · [Docker](docker.md) · [Plugins](plugins.md) · [Versions](versions.md) · [Troubleshooting](troubleshooting.md)

---

# Plugins

> **⚠️ Experimental:** Plugins are experimental and a work in progress. They are **not guaranteed to work 100%** in every environment. Use them at your own risk and report issues you encounter. The Plugins page and host hooks are part of the GUI patch; optional plugin packages (e.g. Trial Link Scanner) are separate installs.

OF-Scraper GUI includes an extensible plugin system. Plugins are placed in your ofscraper config directory and are loaded automatically on startup.

**Plugin directory:**
- **Windows:** `C:\Users\<YourUser>\.config\ofscraper\plugins\`
- **Linux / macOS:** `~/.config/ofscraper/plugins/`

## Getting the plugins

The GUI patch adds the plugin **system** (the Plugins page and hooks) but does **not** install any plugins. The plugins live in this repository's [`Available Plugins/`](../Available%20Plugins) folder:

| Plugin | In `Available Plugins/` |
| :--- | :--- |
| JoyCaption Tagger | `joycaption_tagger.zip` |
| LLM Assistant | `llm_assistant.zip` |
| Live Stream Monitor | `live_stream_monitor/` (folder) |
| Trial Link Scanner | `trial_link_scanner.zip` |

To install one, unzip it (or copy the folder) into your plugin directory, so you end up with e.g. `~/.config/ofscraper/plugins/trial_link_scanner/main.py`. Then open the **Plugins** page and click **Refresh**.

## Plugins page

<details><summary>Screenshots</summary>

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

</details>

- Left-nav **Plugins** page lists installed plugins (name, version, Loaded / Disabled / Not loaded)
- **Enable / Disable** writes `plugin_enabled` in the plugin’s `main.py`
- **Load now** / **Unload now** — bring a plugin into (or out of) the current GUI session without restarting (runs `on_ui_setup` / `on_ui_teardown`)
- Open plugins folder / selected plugin folder; Refresh after copying a new plugin in

Each plugin is a subfolder containing at minimum a `main.py` with a `Plugin` class that inherits from `BasePlugin`. Plugins can hook into the following events:

| Hook | When it fires |
| :--- | :--- |
| `on_load()` | When the plugin is first loaded at startup |
| `on_ui_setup(main_window)` | After the GUI window is built *(GUI mode only)* |
| `on_ui_teardown(main_window)` | Before unload / **Unload now** — remove pages/nav |
| `on_item_downloaded(item_data, file_path)` | Every time a file is saved to disk |
| `on_scrape_start(config, models)` | When a new scrape begins |
| `on_posts_collected(posts, model_username)` | After each batch of posts/messages is collected for a model |
| `on_scrape_complete(stats)` | When the scrape finishes |
| `on_unload()` | When the plugin is unloaded |

Plugins that declare a `requirements.txt` will trigger a one-click dependency install dialog if their packages are missing.

For full documentation on writing plugins see [`PLUGIN_DEVELOPMENT.md`](../PLUGIN_DEVELOPMENT.md).

## Available plugins

The plugins below are in [`Available Plugins/`](#getting-the-plugins). They are typically **disabled by default** — enable via `plugin_enabled = 1` in each plugin’s `main.py`, or use the **Plugins** page.

### JoyCaption Tagger (`joycaption_tagger`)

Sends downloaded images to a [JoyCaption Alpha Two](https://huggingface.co/fancyfeast/llama-joycaption-alpha-two-hf-llava) node running inside ComfyUI (local or Docker) and stores the captions in a local database. JoyCaption Alpha Two natively supports adult/explicit content captioning, making it well-suited for OF-Scraper content. Caption style and length are configurable per the plugin settings panel. A built-in image gallery lets you browse and search tagged images by caption content, browse by model (click a model to see all their tagged images), and open any image in your system's external image viewer. The gallery has no cap on the number of images displayed, and all tagging activity is logged so you can see exactly what the plugin is doing during folder scans.

> **Performance note:** JoyCaption sends each image to ComfyUI for AI inference, which is compute-intensive. Captioning a single image can take anywhere from a few seconds to several minutes depending on your hardware (CPU vs. GPU, available RAM, etc.).
>
> When **Auto-tag images on download** is enabled, every downloaded image is sent to ComfyUI during the scrape — this can significantly slow down large scraping sessions. For better performance, consider leaving auto-tagging **disabled** and using the **Scan Folder** tool from the plugin page to tag images after your scrape finishes.

**Screenshots**

<details><summary>Screenshots</summary>

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
<td align="center"><img src="https://github.com/user-attachments/assets/18c7f8ee-ef12-45b0-8308-282177518162" width="380"><br><em>Settings dialog</em></td>
<td align="center"><img src="https://github.com/user-attachments/assets/cc174331-628e-4cf2-b697-91bfd7f9ecc8" width="380"><br><em>Full image view with caption/tags</em></td>
</tr>
</table>

</details>

**System requirements**

| | Minimum | Recommended |
| :--- | :--- | :--- |
| RAM | 8 GB | 16 GB+ |
| Disk | 20 GB free | 30 GB+ free |
| GPU | Not required | NVIDIA GPU with 8 GB+ VRAM for faster inference |
| OS | Any Docker host | Linux preferred |

> The JoyCaption model (`llama-joycaption-alpha-two-hf-llava`) is approximately **15 GB**. The included Docker setup runs in **CPU-only mode** — captioning will be noticeably slower than GPU inference but works on any machine with enough RAM.

**Install the plugin:** unzip `Available Plugins/joycaption_tagger.zip` into your plugin directory (see [Getting the plugins](#getting-the-plugins)). It also needs a ComfyUI server with the JoyCaption node, set up below.

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

### LLM Assistant (`llm_assistant`)

Adds a **🤖 AI Assistant** chat panel to the sidebar. Type plain English commands — the assistant translates them into GUI actions such as setting usernames, selecting content areas, and starting downloads.

 Compact **Ask AI** bars on Action / Areas / Table pages; Areas state mirror on the AI tab; if you Ask before the model is loaded, the plugin opens the AI page, starts Load Model, and queues your prompt.

**Screenshots**

<details><summary>Screenshots</summary>

<table>
<tr>
<td align="center"><img src="https://github.com/user-attachments/assets/f465046f-d6a8-4282-9839-9e459a2e8e1f" width="380"><br><em>AI model selection (first launch)</em></td>
<td align="center"><img src="https://github.com/user-attachments/assets/996a3d4d-be3a-478e-85fd-e61242f62409" width="380"><br><em>Dependency install dialog</em></td>
</tr>
<tr>
<td align="center" colspan="2"><img src="https://github.com/user-attachments/assets/0a9df78b-054e-4b6b-9e0b-61d6d3f4af5d" width="500"><br><em>AI Assistant chat panel</em></td>
</tr>
</table>

</details>

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

1. Unzip `Available Plugins/llm_assistant.zip` into your plugin directory, then set `plugin_enabled = 1` in `llm_assistant/main.py` (or use the Plugins page) and restart the GUI.
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

### Live Stream Monitor (`live_stream_monitor`)

Adds a **📺 Live Monitor** sidebar page that polls your subscriptions, detects when a creator goes live, and captures the stream with Playwright Chromium into `{username}/Live_Streams/`.

This is **separate** from the Areas checkbox **Streams** (API VODs / stream posts in your normal scrape folders).

**Highlights (plugin v1.3.6)**

The version shows on the Plugins page and next to the Live Monitor page title.

- Privacy mode masks usernames/paths in the plugin UI and console
- Windows capture paths use normal backslash display
- **No window (headless browser)**, on by default: captures run in Chrome's headless mode, with no window at all. Untick it to use a real Chrome window (optionally kept off-screen with *Hide capture window*), e.g. to log in by hand
- The capture browser logs in with the **Authentication** login: its cookies, its **user-agent** (OnlyFans ties the session to it, even a Firefox one) and its **x-bc** (put where the website reads it). Each capture starts from a clean browser profile. If OnlyFans still shows its login page, headless captures stop straight away with a message to re-import cookies (Authentication → Test must pass)
- Chromium install prompt when needed; Stop / Unload while a capture is running
- Subscriptions table expands to fill the page (resizable columns); terminal sits full-width at the bottom
- **Capture selected** / **Stop all** / per-row **Stop** (poller can keep running). Buttons that can't do anything right now (nothing selected, creator ignored or already capturing) are greyed out
- **Right-click a creator** for Capture now, Stop, Open recordings folder, Ignore and Copy name (Copy name is hidden in Privacy mode). Double-click opens the recordings folder; if there are no recordings yet, the console says so instead of creating an empty folder
- Ignored creators are greyed out and marked "ignored". **Only live** next to the filter box shows just the creators who are live or being captured
- While recording, the Status column shows the time and file size so far, e.g. `Recording 🔴 (12:04 · 850 MB)`
- **Desktop notifications** (on by default) when a recording starts, is saved, or a capture fails. Names are hidden in Privacy mode
- Once Chromium works, Playwright Setup shrinks to "🟢 Chromium ready"; **Manage…** shows Reinstall Chromium and Clear saved browser logins
- The table updates rows in place between polls, so your scroll position and selection stay put
- The top of the page shows whether the monitor is working: last check time, seconds until the next one, how many creators are live and recording
- Poll interval, capture folder and Auto-Capture are remembered. If Auto-Capture was on when you closed the GUI, it starts again on the next launch (an auth failure turns it off)
- The console keeps the last 2,000 lines, and stays where you scrolled until you go back to the bottom
- Capture cooldown so Auto-Capture does not immediately re-spawn the same creator: 30 s after **Stop**, 2 min after any start that didn't reach recording, 10 min after a login timeout
- **Stop** takes effect within a few seconds, even while the browser is waiting for a login or for the player
- The capture browser runs with Chrome's **sandbox on**. It's turned off only as root or in a container (where Chrome can't use it), or if Chrome reports it can't start one; the console then says so
- When a stream ends, the recording's length is fixed with the **FFmpeg from Configuration → Download** (or a built-in fallback). Long recordings are processed without loading them into memory
- **Clear saved browser logins** (Playwright Setup → Manage…) deletes the capture browser's saved OnlyFans logins. There is one per creator under `<config>/playwright_profiles/`, readable only by you
- **Show diagnostics** (off by default) reveals optional tools and the detailed audio/player log lines during captures:
  - *Diagnostics probe only* / **Probe selected…** — join live ~45s, redacted HLS/WebRTC/API evidence under `live_probe_reports/` (no WebM)
  - **Fetch live API dump…** — redacted `/streams/active` + `/streams/active/url` JSON under `live_api_dumps/`
  - Reports hide tokens and email addresses, but they still contain creator names and stream details; check them before sharing
- Native Agora Server SDK joins are **not** supported (OF rejects them); Playwright is the capture path on Windows and Linux

**Setup**
1. Copy the `Available Plugins/live_stream_monitor` folder into your plugins folder
2. Enable via Plugins page or `plugin_enabled = 1`, then Load now / restart
3. Install Chromium from the Live Monitor page if prompted. Playwright is installed the same way OF-Scraper was: `pipx inject ofscraper playwright` for pipx, `uv pip install` into OF-Scraper's uv environment for uv, and pip otherwise. If that fails, the console shows the command to run yourself. On Linux the plugin never asks for your password: it installs Chromium's system libraries only when it already runs as root (e.g. Docker). Desktops usually have them; if Chromium can't start, run the `sudo … playwright install-deps chromium` command the console shows
4. Enable Auto-Capture — polling uses normal GUI auth; Chromium opens only when someone goes live

---

### Trial Link Scanner (`trial_link_scanner`)

Automatically scans every direct message collected during a scrape for OnlyFans trial/free-trial links (`https://onlyfans.com/<creator>/trial/<token>`), logs all matches to a daily log file, and optionally posts them to your Discord webhook — including any images attached to the message.

**Screenshots**

<details><summary>Screenshot</summary>

<img src="https://github.com/user-attachments/assets/f2e08ad4-a335-47ea-8275-13c34c64d01d" width="600" alt="Trial Link Scanner">

</details>

**How it works**

1. During scraping, every direct message collected for each model is passed to the plugin via the `on_posts_collected` hook
2. The plugin searches the raw HTML message text (not the stripped display text) for trial link URLs using a regex — this catches the full URL even when OnlyFans truncates it in the UI
3. Each unique link found is written to a daily log file (`logs/trial_links_YYYY-MM-DD.log`) inside the plugin directory
4. If Discord is enabled and a webhook URL is configured in OF-Scraper's Configuration → General, a notification is sent immediately (or held until the scrape ends in summary mode)
5. Images attached to the message are downloaded from OnlyFans' CDN locally (using the IP-restricted signed URL) and uploaded directly to Discord as file attachments, so they display permanently in Discord without relying on OnlyFans' CDN

**Setup**

1. Unzip `Available Plugins/trial_link_scanner.zip` into your plugin directory, so the folder ends up at:
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
