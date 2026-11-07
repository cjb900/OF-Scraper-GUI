[🏠 README](../README.md) · [Install](install.md) · [GUI guide](gui-guide.md) · [Docker](docker.md) · [Plugins](plugins.md) · [Versions](versions.md) · [Troubleshooting](troubleshooting.md)

---

# Versions

Each patch script works with exactly one OF-Scraper version. To see which patch you have installed, click the version button at the bottom of the sidebar (**About → GUI patch**), e.g. `20261107_gui_3_16_4_v420`.

> [!WARNING]
> **3.16.4 is now the maintained patch.** It is for [OF-Scraper-Community](https://github.com/cloakedkeys/OF-Scraper-Community) 3.16.4, the maintained fork of OF-Scraper, which is on PyPI as [`ofscraper-community`](https://pypi.org/project/ofscraper-community/) (`pip install ofscraper-community==3.16.4`). Uninstall the older `ofscraper` package first: both use the same folder ([Install](install.md#moving-from-ofscraper-3147-or-a-git-install)). The 3.14.7 patch stays for existing OF-Scraper 3.14.7 installs. The 3.12.9, 3.14.3 and 3.14.5 patches have not been updated and may not work properly.

| Patch script | OF-Scraper version | Status |
|---|---|---|
| `patch_ofscraper_3.16.4_gui.py` | OF-Scraper-Community 3.16.4 (`ofscraper-community`) | **Maintained** (all current fixes and features) |
| `patch_ofscraper_3.14.7_gui.py` | 3.14.7 | Updated until the move to 3.16.4 |
| `patch_ofscraper_3.14.5_gui.py` | 3.14.5 | Not updated, may not work properly |
| `patch_ofscraper_3.14.3_gui.py` | 3.14.3 | Not updated, may not work properly |
| `patch_ofscraper_3.12.9_gui.py` | 3.12.9 | Not updated, may not work properly |

## Feature availability by version

| Feature | 3.12.9 | 3.14.3 | 3.14.5 | 3.14.7 | 3.16.4 |
|---|:---:|:---:|:---:|:---:|:---:|
| Core scraper workflow (download, like/unlike) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Authentication, Configuration, Profiles, Merge DBs | ✅ | ✅ | ✅ | ✅ | ✅ |
| Daemon mode | ✅ | ✅ | ✅ | ✅ | ✅ |
| Discord webhook toggle | ✅ | ✅ | ✅ | ✅ | ✅ |
| DRM Key Creation | ✅ | ✅ | ✅ | ✅ | ✅ |
| Table page (filters, sort, cart, avatars) | ✅ | ✅ | ✅ | ✅ | ✅ |
| CLI auto-start (`--username`, `-a`, `-o`) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Check modes (Post / Message / Paid / Story Check) | ❌ | ✅ | ✅ | ✅ | ✅ |
| Include Post Text | ❌ | ✅ | ✅ | ✅ | ✅ |
| User Lists (`--ul`) + Reload Models | ❌ | ❌ | ✅ | ✅ | ✅ |
| Discord notification level selector (LOW / NORMAL) | ❌ | ❌ | ✅ | ✅ | ✅ |
| Per-run Discord scrape summary | ❌ | ❌ | ✅ | ✅ | ✅ |
| Scrape by URL / Post ID | ❌ | ❌ | ✅ | ✅ | ✅ |
| CLI auto-start with `--ul` | ❌ | ❌ | ✅ | ✅ | ✅ |
| Video quality selector (`-q` / `--quality`) | ❌ | ❌ | ❌ | ✅ | ✅ |
| Login in Browser (embedded auth) | ❌ | ❌ | ❌ | ✅ | ✅ |
| Confirm scrape (pre-start review + ETA) | ❌ | ❌ | ❌ | ✅ | ✅ |
| Privacy / demo mode | ❌ | ❌ | ❌ | ✅ | ✅ |
| Status strip + Auth/Config/Key health chips | ❌ | ❌ | ❌ | ✅ | ✅ |
| Plugins page (Load / Unload now) | ❌ | ❌ | ❌ | ✅ | ✅ |
| History / filter presets / sticky columns / CSV | ❌ | ❌ | ❌ | ✅ | ✅ |
| Allow duplicates + Messages/Purchased keep-both | ❌ | ❌ | ❌ | ✅ | ✅ |
| Windows path backslashes in Config | ❌ | ❌ | ❌ | ✅ | ✅ |
| Scripts tab + preferred file extensions | ❌ | ❌ | ❌ | ✅ | ✅ |
| Crash diagnostics (`gui_crash_logs/`) | ❌ | ❌ | ❌ | ✅ | ✅ |
| About dialog (sidebar `v…`) + global text size | ❌ | ❌ | ❌ | ✅ | ✅ |
| Duplicate column in content table | ❌ | ❌ | ❌ | ✅ | ✅ |
| Save/Reset Settings confirmation dialogs | ❌ | ❌ | ❌ | ✅ | ✅ |
| TUI-style scrape summary with global totals | ❌ | ❌ | ❌ | ✅ | ✅ |
| Collapsible filter sidebar | ❌ | ❌ | ❌ | ✅ | ✅ |
| Update metadata options (Update / Check / Complete, mark locked, hashes) | ❌ | ❌ | ❌ | ✅ | ✅ |
| Download all purchased content (all creators, exclude list) | ❌ | ❌ | ❌ | ✅ | ✅ |
| Recover files lost to old filename collisions (`recover_collisions`) | ❌ | ❌ | ❌ | ✅ | ✅ |
| Clear one-time message when manual-mode CDM key files are missing | ❌ | ❌ | ❌ | ✅ | ✅ |
| Clean stop on SIGTERM; SIGUSR1 starts the next daemon run | ❌ | ❌ | ❌ | ✅ | ✅ |
| Docker `MODE=cli` (CLI daemon without the GUI) | ❌ | ❌ | ❌ | ✅ | ✅ |
| Login window DevTools off by default (`OFSCRAPER_GUI_WEBENGINE_DEBUG=1`) | ❌ | ❌ | ❌ | ✅ | ✅ |
| Non-blocking startup dependency popup | ✅ | ✅ | ✅ | ✅ | ✅ |
| Plugin system (JoyCaption, LLM, Live Monitor, Trial Links) | ✅ | ✅ | ✅ | ✅ | ✅ |
| OF-Scraper-Community fixes and features: Fansly (command line), request timeouts, a working speed limit, clearer login errors, `--before`/`--after` date formats | ❌ | ❌ | ❌ | ❌ | ✅ |
| OF-Scraper-Community 3.16.4: resumed downloads that keep the right size, error and empty replies no longer saved as files, `--output LOW`/`PROMPT` quiet the console | ❌ | ❌ | ❌ | ❌ | ✅ |
