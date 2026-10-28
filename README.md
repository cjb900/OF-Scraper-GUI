# OF-Scraper GUI Patch

A self-contained Python script that patches an installed (non-binary) copy of [OF-Scraper](https://github.com/datawhores/OF-Scraper) to add a full **PyQt6 GUI**, opened with `ofscraper --gui`.

**Supported OF-Scraper versions:** `3.12.9`, `3.14.3`, `3.14.5`, and `3.14.7` (one patch script per version; 3.14.7 has the most features, see [Versions](docs/versions.md)).

<img src="https://github.com/user-attachments/assets/e7c590a6-3b05-4e93-9d8c-f35eb673aa46" width="600" alt="Main Window — Select Action">
<img src="https://github.com/user-attachments/assets/0d04b396-9ae2-40db-a29e-c40bf6f55f7a" width="600" alt="Scraping page — media table">

## What it adds

- **A step-by-step scrape wizard**: pick an action, content areas and filters, and models, then watch progress in a live table and log
- **Check modes** to browse everything a creator posted (including locked items) and download only what you pick
- **Authentication made easier**: import cookies from your browser, or log in through a browser window, instead of copying headers by hand
- **Every setting in one place**, with checks that stop bad paths and file names before a scrape starts
- **DRM key creation**, profiles, database merging, daemon mode, Discord notifications, scrape history, CSV export and more
- **Plugins** (experimental): AI image tagging, an AI assistant, live stream capture and trial-link scanning
- **Docker** support: run the GUI on a server and open it in your browser

The [GUI guide](docs/gui-guide.md) walks through every page.

## Before you start

| Platform | pip | pipx | uv |
|----------|:---:|:----:|:--:|
| Windows  | ✅  | ✅   | ✅ |
| Linux (Debian-based) | ❌  | ✅   | ✅ |
| Mac OS   | ❌ | ❌  | ❌ |
| Docker   | ✅ | — | — |

❌ = not tested. Windows is tested on Windows 11; Linux on Debian-based distributions (Ubuntu, Debian, Mint, KDE neon, Pop!_OS, …).

- **Python:** 3.11 and 3.12 are supported, and newer versions also work (the patch installs OF-Scraper with Python 3.12 on 3.13+). **If you run into issues with a newer Python version, use Python [3.11.6](https://www.python.org/downloads/release/python-3116/)** (recommended).
- **FFmpeg** (needed for DRM videos): version 6 or newer works. **If you run into issues with a version above 7.1.1, use FFmpeg 7.1.1.**

More detail: [Install](docs/install.md).

## Quick start

1. Download the patch script for your OF-Scraper version from this repository, e.g. `patch_ofscraper_3.14.7_gui.py`.
2. Run it. It finds your OF-Scraper install (or offers to install it), backs up the files it changes, installs PyQt6, and applies the patch:

   ```bash
   python patch_ofscraper_3.14.7_gui.py
   ```

3. Start the GUI:

   ```bash
   ofscraper --gui
   ```

4. In the GUI: **Authentication** → log in or import cookies; **Configuration** → set your Save Location and FFmpeg path; then **Scraper** → pick an action and go.

To update later, download the newer patch script and run it again. To undo the patch: `python patch_ofscraper_3.14.7_gui.py --restore /path/to/backup`. All options: [Install](docs/install.md).

## Docker

Run the GUI on a machine without a desktop and open it at `http://<host>:6699/` in your browser, or run only the command-line daemon with `MODE=cli`. On Linux:

```bash
# edit the /home/YOU/... volume paths in docker-compose.yml first
docker compose build ofscraper-gui
docker compose up -d ofscraper-gui
```

`docker-compose.yml` uses host networking, which only works on Linux. **On Docker Desktop (Windows / macOS) you must change it first.** Setup, volumes, CDM keys, `GUI_ARGS`, `MODE=cli` and troubleshooting: [Docker](docs/docker.md).

## Documentation

| Guide | What's in it |
|---|---|
| [Install](docs/install.md) | Platforms, Python and FFmpeg, patch script options, how your install is detected, backups and restore, `ofscraper_tools.py` (uninstall and data clean-up) |
| [GUI guide](docs/gui-guide.md) | Every page and feature, in the order you use them |
| [Docker](docs/docker.md) | Running the GUI or the CLI daemon in a container |
| [Plugins](docs/plugins.md) | The plugin system, where to get the plugins, and each plugin's setup |
| [Versions](docs/versions.md) | Which features each patch version has |
| [Troubleshooting](docs/troubleshooting.md) | Login, DRM keys, FFmpeg, lost files, crashes |
| [Plugin development](PLUGIN_DEVELOPMENT.md) | Writing your own plugin |

The GUI also has a built-in **Help / README** page with the full reference; every **?** button in the app jumps to the matching section.

## Notes

- A backup of all modified files is saved to your system temp directory before patching; `--restore` undoes the patch.
- This was created with the help of AI and has been tested to the best of my ability. I take no responsibility for any damage or loss of data. Backups are recommended.

## Disclaimer

1. This tool is not affiliated, associated, or partnered with OnlyFans in any way. We are not authorized, endorsed, or sponsored by OnlyFans. All OnlyFans trademarks remain the property of Fenix International Limited.
2. This is a theoretical program only and is for educational purposes. If you choose to use it then it may or may not work. You solely accept full responsibility and indemnify the creator, hosts, contributors and all other involved persons from any and all responsibility.
