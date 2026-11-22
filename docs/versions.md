[🏠 README](../README.md) · [Install](install.md) · [GUI guide](gui-guide.md) · [Docker](docker.md) · [Plugins](plugins.md) · [Versions](versions.md) · [Troubleshooting](troubleshooting.md)

---

# Versions

Each patch script works with exactly one OF-Scraper version. To see which patch you have installed, click the version button at the bottom of the sidebar (**About → GUI patch**), e.g. `20261116_gui_3_17_1_v477`.

> [!WARNING]
> New features go into the **3.17.1** patch; fixes that apply are also made in **3.14.7**. The 3.12.9, 3.14.3 and 3.14.5 patches have not been updated and may not work properly.

| Patch script | OF-Scraper version | Status |
|---|---|---|
| `patch_ofscraper_3.17.1_gui.py` | 3.17.1 | **Recommended.** All current features, OnlyFans and Fansly |
| `patch_ofscraper_3.14.7_gui.py` | 3.14.7 | **Updated** with fixes that apply; OnlyFans only |
| `patch_ofscraper_3.14.5_gui.py` | 3.14.5 | Not updated, may not work properly |
| `patch_ofscraper_3.14.3_gui.py` | 3.14.3 | Not updated, may not work properly |
| `patch_ofscraper_3.12.9_gui.py` | 3.12.9 | Not updated, may not work properly |

## Feature availability by version

| Feature | 3.12.9 | 3.14.3 | 3.14.5 | 3.14.7 | 3.17.1 |
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
| User Lists (`-ul` / `--userlist`) + Reload Models | ❌ | ❌ | ✅ | ✅ | ✅ |
| Discord notification level selector (LOW / NORMAL) | ❌ | ❌ | ✅ | ✅ | ✅ |
| Per-run Discord scrape summary | ❌ | ❌ | ✅ | ✅ | ✅ |
| Scrape by URL / Post ID | ❌ | ❌ | ✅ | ✅ | ✅ |
| CLI auto-start with `-ul` | ❌ | ❌ | ✅ | ✅ | ✅ |
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
| Check options (fetch fresh data, compare with files on disk) and Check messages filter | ❌ | ❌ | ❌ | ✅ | ✅ |
| Download speed limit that works (KB/s on the Config page) | ❌ | ❌ | ❌ | ✅ | ✅ |
| "Network or server problem" and age-verification messages in Test Credentials | ❌ | ❌ | ❌ | ✅ | ✅ |
| Labels stop paging when nothing is new | ❌ | ❌ | ❌ | ✅ | ✅ |
| Non-blocking startup dependency popup | ✅ | ✅ | ✅ | ✅ | ✅ |
| Plugin system (JoyCaption, LLM, Live Monitor, Trial Links) | ✅ | ✅ | ✅ | ✅ | ✅ |
| OnlyFans and Fansly tabs in one window, both scraping at once | ❌ | ❌ | ❌ | ❌ | ✅ |
| Fansly: Timeline, Messages, Purchased and Walls; HLS/DASH videos | ❌ | ❌ | ❌ | ❌ | ✅ |
| Fansly check mode (compare with files on disk, cart) | ❌ | ❌ | ❌ | ❌ | ✅ |
| Fansly My lists and black lists (`-ul` or `-ml` / `--ml`, `-bl`; My Lists box) | ❌ | ❌ | ❌ | ❌ | ✅ |
| Docker: start both sites (`ONLYFANS_GUI_ARGS`, `FANSLY_GUI_ARGS`) | ❌ | ❌ | ❌ | ❌ | ✅ |
| Discord: site in the sender name, totals card, model avatars option | ❌ | ❌ | ❌ | ❌ | ✅ |
| Update now (download and apply a newer patch from the GUI) | ❌ | ❌ | ❌ | ❌ | ✅ |
| Warning when both sites share a temp folder | ❌ | ❌ | ❌ | ❌ | ✅ |
