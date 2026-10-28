[🏠 README](../README.md) · [Install](install.md) · [GUI guide](gui-guide.md) · [Docker](docker.md) · [Plugins](plugins.md) · [Versions](versions.md) · [Troubleshooting](troubleshooting.md)

---

# Versions

Each patch script works with exactly one OF-Scraper version. To see which patch you have installed, click the version button at the bottom of the sidebar (**About → GUI patch**), e.g. `20261028_gui_3_14_7_v402`.

| Patch script | OF-Scraper version |
|---|---|
| `patch_ofscraper_3.12.9_gui.py` | 3.12.9 |
| `patch_ofscraper_3.14.3_gui.py` | 3.14.3 |
| `patch_ofscraper_3.14.5_gui.py` | 3.14.5 |
| `patch_ofscraper_3.14.7_gui.py` | 3.14.7 |

## Feature availability by version

| Feature | 3.12.9 | 3.14.3 | 3.14.5 | 3.14.7 |
|---|:---:|:---:|:---:|:---:|
| Core scraper workflow (download, like/unlike) | ✅ | ✅ | ✅ | ✅ |
| Authentication, Configuration, Profiles, Merge DBs | ✅ | ✅ | ✅ | ✅ |
| Daemon mode | ✅ | ✅ | ✅ | ✅ |
| Discord webhook toggle | ✅ | ✅ | ✅ | ✅ |
| DRM Key Creation | ✅ | ✅ | ✅ | ✅ |
| Table page (filters, sort, cart, avatars) | ✅ | ✅ | ✅ | ✅ |
| CLI auto-start (`--username`, `-a`, `-o`) | ✅ | ✅ | ✅ | ✅ |
| Check modes (Post / Message / Paid / Story Check) | ❌ | ✅ | ✅ | ✅ |
| Include Post Text | ❌ | ✅ | ✅ | ✅ |
| User Lists (`--ul`) + Reload Models | ❌ | ❌ | ✅ | ✅ |
| Discord notification level selector (LOW / NORMAL) | ❌ | ❌ | ✅ | ✅ |
| Per-run Discord scrape summary | ❌ | ❌ | ✅ | ✅ |
| Scrape by URL / Post ID | ❌ | ❌ | ✅ | ✅ |
| CLI auto-start with `--ul` | ❌ | ❌ | ✅ | ✅ |
| Video quality selector (`-q` / `--quality`) | ❌ | ❌ | ❌ | ✅ |
| Login in Browser (embedded auth) | ❌ | ❌ | ❌ | ✅ |
| Confirm scrape (pre-start review + ETA) | ❌ | ❌ | ❌ | ✅ |
| Privacy / demo mode | ❌ | ❌ | ❌ | ✅ |
| Status strip + Auth/Config/Key health chips | ❌ | ❌ | ❌ | ✅ |
| Plugins page (Load / Unload now) | ❌ | ❌ | ❌ | ✅ |
| History / filter presets / sticky columns / CSV | ❌ | ❌ | ❌ | ✅ |
| Allow duplicates + Messages/Purchased keep-both | ❌ | ❌ | ❌ | ✅ |
| Windows path backslashes in Config | ❌ | ❌ | ❌ | ✅ |
| Scripts tab + preferred file extensions | ❌ | ❌ | ❌ | ✅ |
| Crash diagnostics (`gui_crash_logs/`) | ❌ | ❌ | ❌ | ✅ |
| About dialog (sidebar `v…`) + global text size | ❌ | ❌ | ❌ | ✅ |
| Duplicate column in content table | ❌ | ❌ | ❌ | ✅ |
| Save/Reset Settings confirmation dialogs | ❌ | ❌ | ❌ | ✅ |
| TUI-style scrape summary with global totals | ❌ | ❌ | ❌ | ✅ |
| Collapsible filter sidebar | ❌ | ❌ | ❌ | ✅ |
| Update metadata options (Update / Check / Complete, mark locked, hashes) | ❌ | ❌ | ❌ | ✅ |
| Download all purchased content (all creators, exclude list) | ❌ | ❌ | ❌ | ✅ |
| Recover files lost to old filename collisions (`recover_collisions`) | ❌ | ❌ | ❌ | ✅ |
| Clear one-time message when manual-mode CDM key files are missing | ❌ | ❌ | ❌ | ✅ |
| Clean stop on SIGTERM; SIGUSR1 starts the next daemon run | ❌ | ❌ | ❌ | ✅ |
| Docker `MODE=cli` (CLI daemon without the GUI) | ❌ | ❌ | ❌ | ✅ |
| Login window DevTools off by default (`OFSCRAPER_GUI_WEBENGINE_DEBUG=1`) | ❌ | ❌ | ❌ | ✅ |
| Non-blocking startup dependency popup | ✅ | ✅ | ✅ | ✅ |
| Plugin system (JoyCaption, LLM, Live Monitor, Trial Links) | ✅ | ✅ | ✅ | ✅ |
