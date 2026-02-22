# Work in progress OF-Scraper 3.12.9 GUI Patch. There may be bugs/issues

A self-contained Python script that patches an installed (non binary version) copy of [OF-Scraper](https://github.com/datawhores/OF-Scraper) v3.12.9 to add a full **PyQt6 GUI** accessible via the `--gui` flag.

## Screenshots


| Main Window | Select Content Areas & Filters |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/5bf55728-fe98-4306-9624-218fd9934ce1" width="450" alt="Main Window"> | <img src="https://github.com/user-attachments/assets/16cc4477-6686-4c0f-8ab8-908490e7fd1b" width="450" alt="Select Content Areas & Filters"> |

| Authentication | Configuration |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/6c296bef-b3e2-47b4-bff4-3aa6b729b3f4" width="450" alt="Authentication"> | <img src="https://github.com/user-attachments/assets/c18de136-ed00-439e-b431-330b908bcf8d" width="450" alt="Configuration"> |

| Select Models | Scraper Running |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/a24b3be9-6431-4ae7-8c91-edde5e9cb49d" width="450" alt="Select Models"> | <img src="https://github.com/user-attachments/assets/fb5b1ffc-b02b-4f2a-9f8c-1d0bda2b0379" width="450" alt="Scraper Running"> |

| Profile | Help/README |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/18665429-03ae-4677-af40-bb9c788ff2fd" width="450" alt="Profile"> | <img src="https://github.com/user-attachments/assets/1c06d05a-545f-4b1e-9e76-fde331abcbbe" width="450" alt="Help / README"> |



## What it does

- Adds a (Catppuccin-inspired) dark/light theme GUI to OF-Scraper with pages for:
  - **Scraper** — select actions, content areas, and models with a filterable table
  - **Authentication** — edit credentials, import cookies from your browser (Chrome, Firefox, Edge, Brave, etc.), auto-detect User Agent
  - **Configuration** — edit all config.json settings across tabbed sections (General, File Options, Download, Performance, Content, CDM, Advanced, Response Type, Overwrites)
  - **Profiles** — create, rename, delete, and switch profiles
  - **Merge DBs** — merge model databases
  - **Help / README** — built-in documentation with table of contents and section jump links
- Installs **PyQt6** automatically using the correct method for your setup
- Creates a **timestamped backup** of all original files before patching
- Supports `--restore` to revert to the original files from a backup

## GUI features

### Theme
- Toggle between **Dark** and **Light** mode using the button in the bottom-left navigation bar
- Theme preference is saved to `gui_settings.json` in your ofscraper config directory

### Context-sensitive help
- Every section and option throughout the GUI has a small **?** button next to it
- Clicking a **?** button navigates directly to the matching section in the Help / README page

### Startup dependency check
- On launch, the GUI checks whether **FFmpeg** and **CDM key paths** are configured
- If either is missing, a notice pops up with quick links to jump directly to the relevant config fields

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
- **New Scrape** button: if scraping is active, confirms cancellation first; optionally resets all options and model selections back to defaults before returning to the start

### CLI auto-start
- If launched with `ofscraper --gui` together with action, area, and username flags, the GUI wizard is skipped and scraping begins automatically — matching the TUI behavior for scripted/automated workflows

### Help / README page
- Built-in documentation rendered from `GUI_HELP.md`
- **Jump to…** combo box for quick navigation to any section
- Full **table of contents** with clickable links; each TOC entry scrolls directly to the matching section
- **Additional Help** button links to the project Discord

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
- **Mac**: Mac OS has not been tested with this GUI patch.
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

- **Options 1-3** install OF-Scraper v3.12.9 using your chosen package manager, then continue with patching
- **Option 4** lets you provide the path to your ofscraper package directory manually (e.g. `/path/to/site-packages/ofscraper`). The script validates the path contains `__main__.py` before proceeding
- You can also use `--target /path/to/ofscraper` to skip detection entirely

## Usage

```bash
# Basic usage — auto-detect and patch
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

## After patching

Launch the GUI with:

```bash
ofscraper --gui
```

## Notes

- This patch is specifically for **OF-Scraper v3.12.9** — other versions are not supported
- A backup of all modified files is saved to your system temp directory before patching
- The `--restore` flag can undo the patch using any previous backup
- PyQt6 is installed automatically via the same package manager used for OF-Scraper (pip/pipx inject/uv)
- This was created with the help of AI and has been tested to the best of my ability. I take no responsibility for any damage or loss of data. Backups are recommended.

## Disclaimer

1. This tool is not affiliated, associated, or partnered with OnlyFans in any way. We are not authorized, endorsed, or sponsored by OnlyFans. All OnlyFans trademarks remain the property of Fenix International Limited.
2. This is a theoretical program only and is for educational purposes. If you choose to use it then it may or may not work. You solely accept full responsibility and indemnify the creator, hosts, contributors and all other involved persons from any and all responsibility.
