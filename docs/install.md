[🏠 README](../README.md) · [Install](install.md) · [GUI guide](gui-guide.md) · [Docker](docker.md) · [Plugins](plugins.md) · [Versions](versions.md) · [Troubleshooting](troubleshooting.md)

---

# Install and patch

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
- **Docker**: Runs on any host that supports Docker. The container uses Ubuntu 24.04 with Xvfb and noVNC — no display required on the host. See [Docker](docker.md)

### Python version

- Python **3.11** and **3.12** are supported
- Newer versions (**3.13** and up) also work: on Python 3.13+ the patch script installs OF-Scraper with Python 3.12 through uv or pipx, which download it if it isn't installed
- **If you run into issues with a newer Python version, use Python [3.11.6](https://www.python.org/downloads/release/python-3116/)** (recommended)
- Python below 3.11 is **not supported**

### FFmpeg

FFmpeg is needed to merge DRM audio and video and to check downloaded files. Set its path in **Configuration → Download → FFmpeg Path**.

- FFmpeg **6 or newer** works, including FFmpeg 8
- **If you run into issues with a version above 7.1.1, use FFmpeg 7.1.1**
- Windows builds: [gyan.dev](https://www.gyan.dev/ffmpeg/builds/). Linux: your package manager (`sudo apt install ffmpeg`)
- The Docker image includes its own FFmpeg; don't mount a host copy into it

## Running the patch script

Download the patch script for your OF-Scraper version from the repository root (e.g. `patch_ofscraper_3.14.7_gui.py`) and run it with Python. If OF-Scraper isn't installed yet, the script offers to install it ([see below](#if-of-scraper-is-not-detected)).

**Updating:** to move to a newer GUI patch, download the new script and run it again. It replaces the patched files and makes a fresh backup first.

```bash
# Basic usage — auto-detect and patch (replace version number as needed)
python patch_ofscraper_3.14.7_gui.py

# Skip confirmation prompt
python patch_ofscraper_3.14.7_gui.py -y

# Force-reinstall ofscraper 3.14.7 and all GUI dependencies, then patch
python patch_ofscraper_3.14.7_gui.py --force

# Force-reinstall ofscraper only (skip GUI dependency reinstall)
python patch_ofscraper_3.14.7_gui.py --force --skip-deps

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

## Backups and restore

- A backup of all modified files is saved to your system temp directory before patching
- The `--restore` flag can undo the patch using any previous backup
- PyQt6 is installed automatically via the same package manager used for OF-Scraper (pip/pipx inject/uv)
