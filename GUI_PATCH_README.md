# OF-Scraper 3.12.9 GUI Patch

A self-contained Python script that patches an installed copy of [OF-Scraper](https://github.com/datawhores/OF-Scraper) v3.12.9 to add a full **PyQt6 GUI** accessible via the `--gui` flag.

## Screenshots

<!-- Replace these with actual screenshot paths/URLs -->
| Main Window | Authentication |
|:-----------:|:--------------:|
| ![GUI Main Window](screenshots/main_window.png) | ![Authentication Page](screenshots/auth_page.png) |

| Configuration | Model Table |
|:-------------:|:-----------:|
| ![Configuration Page](screenshots/config_page.png) | ![Model Table](screenshots/model_table.png) |

| Scraper Running | Profiles |
|:---------------:|:--------:|
| ![Scraper Running](screenshots/scraper_running.png) | ![Profiles Page](screenshots/profiles_page.png) |

## What it does

- Adds a dark-themed (Catppuccin-inspired) GUI to OF-Scraper with pages for:
  - **Scraper** — select actions, content areas, and models with a filterable table
  - **Authentication** — edit credentials, import cookies from your browser (Chrome, Firefox, Edge, Brave, etc.), auto-detect User Agent
  - **Configuration** — edit all config.json settings across tabbed sections (General, File Options, Download, Performance, Content, CDM, Advanced, Response Type, Overwrites)
  - **Profiles** — create, rename, delete, and switch profiles
  - **Merge DBs** — merge model databases
  - **Help / README** — built-in documentation
- Installs **PyQt6** automatically using the correct method for your setup
- Creates a **timestamped backup** of all original files before patching
- Supports `--restore` to revert to the original files from a backup

## Supported platforms and install methods

| Platform | pip | pipx | uv |
|----------|:---:|:----:|:--:|
| Windows  | ✅  | ✅   | ✅ |
| Linux (Debian-based) | ✅  | ✅   | ✅ |

### Platform notes

- **Windows**: Tested on **Windows 11** but should work on Windows 10 and other versions
- **Linux**: Only **Debian-based** distributions are supported (Ubuntu, Debian, Linux Mint, KDE Neon, Pop!_OS, etc.). Other distributions (Arch, Fedora, etc.) have not been tested and may require additional setup

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
- This was created with the help of AI and has been tested to the best of my ability
