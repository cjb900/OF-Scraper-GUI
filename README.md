# Work in progress OF-Scraper 3.12.9 GUI Patch. There may be bugs/issues

A self-contained Python script that patches an installed copy of [OF-Scraper](https://github.com/datawhores/OF-Scraper) v3.12.9 to add a full **PyQt6 GUI** accessible via the `--gui` flag.

## Screenshots


| Main Window | Authentication |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/0ebd1a62-d865-4032-a70b-fb17bad868f1" width="450" alt="GUI Main Window"> | <img src="https://github.com/user-attachments/assets/a0f4a3a6-cdfd-4eec-b89d-b6a6446b920a" width="450" alt="Authentication Page"> |

| Configuration | Select Content Areas & Filters |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/358dfa99-2989-40a5-99cc-5cf180f1844c" width="450" alt="Configuration Page"> | <img src="https://github.com/user-attachments/assets/124624c8-cf8a-4465-a1e4-19b081420577" width="450" alt="Select Content Areas & Filters"> |

| Select Models | Scraper Running |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/093fcaf0-50c6-4218-a30e-369db65578a6" width="450" alt="Select Models"> | <img src="https://github.com/user-attachments/assets/c6cc216f-dc45-4556-89e4-6bd484ad4dbc" width="450" alt="Scraper Running"> |

| Profile | Help/README |
| --- | --- |
| <img src="https://github.com/user-attachments/assets/03ee5001-6a3f-4bee-8fb8-dd81dd3392b6" width="450" alt="Profile"> | <img src="https://github.com/user-attachments/assets/54a1ccda-997f-409e-a6f9-1d7799210da3" width="450" alt="Help / README"> |



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
| Linux (Debian-based) | ❌  | ✅   | ✅ |

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
- This was created with the help of AI and has been tested to the best of my ability. I take no responcibility for any damage or loss of data. Baskups are recommended. 
