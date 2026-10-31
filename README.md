<p align="center">
  <img src="docs/images/logo.svg" width="128" alt="OF-Scraper GUI logo">
</p>

<h1 align="center">OF-Scraper GUI</h1>

<p align="center">
  <b>A full desktop GUI for OF-Scraper: pick, browse and download from one window instead of the command line.</b>
</p>

<p align="center">
  <img alt="OF-Scraper 3.14.7" src="https://img.shields.io/badge/OF--Scraper-3.14.7-3b82f6">
  <img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776ab?logo=python&logoColor=white">
  <img alt="PyQt6" src="https://img.shields.io/badge/GUI-PyQt6-41cd52?logo=qt&logoColor=white">
  <img alt="Windows, Linux, Docker" src="https://img.shields.io/badge/runs%20on-Windows%20%7C%20Linux%20%7C%20Docker-6b7280">
  <a href="https://github.com/cjb900/OF-Scraper-GUI/actions/workflows/codecov.yml?query=branch%3Atesting"><img alt="tests (testing branch)" src="https://github.com/cjb900/OF-Scraper-GUI/actions/workflows/codecov.yml/badge.svg?branch=testing"></a>
</p>

<p align="center">
  <a href="#quick-start"><b>Get started</b></a> •
  <a href="docs/install.md">Install</a> •
  <a href="docs/gui-guide.md">GUI guide</a> •
  <a href="#docker">Docker</a> •
  <a href="docs/plugins.md">Plugins</a> •
  <a href="docs/versions.md">Versions</a> •
  <a href="docs/troubleshooting.md">Troubleshooting</a>
</p>

---

A self-contained Python script that patches an installed (non-binary) copy of [OF-Scraper](https://github.com/datawhores/OF-Scraper) to add a full **PyQt6 GUI**, opened with `ofscraper --gui`.

**Supported OF-Scraper version:** `3.14.7` (`patch_ofscraper_3.14.7_gui.py`).

> [!WARNING]
> Only the **3.14.7** patch is being updated. The patches for **3.12.9**, **3.14.3** and **3.14.5** are still in the repository but have not been updated and may not work properly. Use OF-Scraper 3.14.7 with the 3.14.7 patch. See [Versions](docs/versions.md).

<p align="center">
  <img src="https://github.com/user-attachments/assets/f78abd65-1fa3-4596-8a76-fe541625722e" width="600" alt="Main Window — Select Action">
  <img src="https://github.com/user-attachments/assets/52530179-6a13-43f6-a8ec-34220c184942" width="600" alt="Scraping page — media table">
</p>

> 📸 **Screenshot to check:** the first picture (Select Action) may be older than the **Update metadata** and **Download all purchased content** actions (patches v391 / v392). Retake it if those two actions are missing. The same picture is in the [GUI guide](docs/gui-guide.md#select-action).

## Contents

- [What it adds](#what-it-adds)
- [Before you start](#before-you-start)
- [Quick start](#quick-start)
- [Docker](#docker)
- [Documentation](#documentation)
- [Notes](#notes)
- [Disclaimer](#disclaimer)

## What it adds

- **A step-by-step scrape wizard**: pick an action, content areas and filters, and models, then watch progress in a live table and log
- **Check modes** to browse everything a creator posted (including locked items) and download only what you pick
- **Authentication made easier**: import cookies from your browser, or log in through a browser window, instead of copying headers by hand
- **Every setting in one place**, with checks that stop bad paths and file names before a scrape starts
- **DRM key creation**, profiles, database merging, daemon mode, Discord notifications, scrape history, CSV export and more
- **Plugins** (experimental): AI image tagging, an AI assistant, live stream capture and trial-link scanning
- **Docker** support: run the GUI on a server and open it in your browser

> 📸 **Screenshot needed:** a small row of pictures for this list, e.g. a Check Mode table, the Authentication page and the Plugins page. The GUI guide already has pictures of these that could be reused; the Live Monitor page still needs one ([Plugins](docs/plugins.md#live-stream-monitor-live_stream_monitor)). Turn on Privacy mode first so no usernames or paths show.

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

**Prerequisites:** you need one of these:

- **OF-Scraper already installed** ([OF-Scraper on GitHub](https://github.com/datawhores/OF-Scraper)), or
- **If OF-Scraper is not installed:** **Python** and one of **pip**, **pipx** or **uv**, so the patch script can install OF-Scraper for you.

More detail: [Prerequisites](docs/install.md#prerequisites).

1. Download the patch script for your OF-Scraper version from this repository, e.g. `patch_ofscraper_3.14.7_gui.py`.
2. Run it. It finds your OF-Scraper install (or offers to install it), backs up the files it changes, installs PyQt6, and applies the patch:

   ```bash
   python patch_ofscraper_3.14.7_gui.py
   ```
  <img src="https://github.com/user-attachments/assets/d29886fd-59e8-4093-882e-4c2ee7c43b05" width="600" alt="Terminal Install">

3. Start the GUI:

   ```bash
   ofscraper --gui
   ```
  <img src="https://github.com/user-attachments/assets/2713008a-8d0e-4d35-be65-4f42ad011dad" width="600" alt="Start GUI">

4. In the GUI: **Authentication** → log in or import cookies; **Configuration** → set your Save Location and FFmpeg path; then **Scraper** → pick an action and go.

> 📸 **Screenshot needed:** the terminal at the end of a successful patch run ("Patch applied successfully" and the offer to launch the GUI). The same picture is wanted in [Install](docs/install.md#after-patching).

To update later, download the newer patch script and run it again. To undo the patch: `python patch_ofscraper_3.14.7_gui.py --restore /path/to/backup`. All options: [Install](docs/install.md).

## Docker

Run the GUI on a machine without a desktop and open it at `http://<host>:6699/` in your browser, or run only the command-line daemon with `MODE=cli`. On Linux:

```bash
# edit the /home/YOU/... volume paths in docker-compose.yml first
docker compose build ofscraper-gui
docker compose up -d ofscraper-gui
```
<img src="https://github.com/user-attachments/assets/8ab70762-3964-4de1-a471-34becf6d88bb" width="600" alt="Docker GUI">

> 📸 **Screenshot needed:** the GUI open in a web browser through noVNC at `http://localhost:6699/`, with the address bar visible. The same picture is wanted in [Docker](docs/docker.md#accessing-the-gui).

The desktop resizes to fit your browser window, and the GUI stays maximized in it: resize the window or go full screen and the GUI follows. `SCREEN_WIDTH` / `SCREEN_HEIGHT` in `docker-compose.yml` are only the starting size.

If the container keeps restarting with `exec /entrypoint.sh: no such file or directory`, `docker/entrypoint.sh` has Windows line endings (this happens when it was copied or edited on Windows). Fix it with `sed -i 's/\r$//' docker/entrypoint.sh`, then rebuild.

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
