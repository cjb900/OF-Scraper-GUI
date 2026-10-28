[🏠 README](../README.md) · [Install](install.md) · [GUI guide](gui-guide.md) · [Docker](docker.md) · [Plugins](plugins.md) · [Versions](versions.md) · [Troubleshooting](troubleshooting.md)

---

# Troubleshooting

The in-app **Help / README** page has the most detailed troubleshooting (especially **Auth Issues**). This page covers the common problems and where to look. For Docker-specific problems, see [Troubleshooting Docker](docker.md#troubleshooting-docker).

When reporting a problem, include your **GUI patch id** (sidebar version button → **About**, e.g. `20261028_gui_3_14_7_v402`) and the relevant log lines.

## The patch or the GUI won't install or start

- **Python:** 3.11 and 3.12 are supported, and newer versions also work. **If you run into issues with a newer Python version, use Python [3.11.6](https://www.python.org/downloads/release/python-3116/).** See [Install → Python version](install.md#python-version)
- **OF-Scraper not found:** the script asks how to install it, or use `--target /path/to/site-packages/ofscraper`. See [Install](install.md#if-of-scraper-is-not-detected)
- **Broken earlier install:** the script detects it and reinstalls OF-Scraper before patching. You can force this with `--force`
- **`ofscraper --gui` runs the wrong copy:** if you are inside a source folder such as `OF-Scraper-3.14.7/`, run it from another folder (e.g. your home folder)
- **Undo the patch:** `python patch_ofscraper_3.14.7_gui.py --restore /path/to/backup` (the backup path is printed when you patch)

## Login and authentication

- If the model list won't load, the GUI offers **Retry**, **Go to Authentication**, **Dynamic Mode** and **SSL Verify**. See [Auth failure handling](gui-guide.md#auth-failure-handling)
- Credentials look right but loading still fails: try another **Dynamic Mode** (Configuration → Advanced). Behind a proxy or antivirus that inspects TLS, try **SSL Verify** = `false` (less secure)
- The in-app **Help → Auth Issues** walks through every capture method, including copying headers by hand from DevTools

## DRM videos are skipped or fail

- **"Key Mode is manual but the CDM files can't be used (…)"**: `client-id` or `private-key` under Configuration → CDM is blank or points to a missing file. The message is logged **once**, and DRM videos are skipped right away, without downloading or retrying. Photos and non-DRM videos still download. Fix the paths, or create keys with **DRM Key Creation**
- **DRM videos still download with a blank key path:** that's expected. Keys saved by earlier runs are reused, so videos you've downloaded before don't need the key files. To test without saved keys, run once with `OFSC_USE_WIV_CACHE_KEY=false` (this doesn't delete them)
- **Remote key modes** (`cdrm`, `cdrm2`, `keydb`) depend on outside services and may fail; **KeyDB** is currently not working. Prefer **manual**
- **Videos stuck as `.part`, or rejected after merging:** check the FFmpeg path in Configuration → Download (see below)

## FFmpeg

- FFmpeg **6 or newer** works, including FFmpeg 8
- **If you run into issues with a version above 7.1.1, use FFmpeg 7.1.1**
- Set the path in **Configuration → Download → FFmpeg Path**. The **Config** health chip in the footer flags a path that doesn't exist, and the startup check reminds you when none is set
- In Docker, use the FFmpeg that comes with the image

## Files lost to old filename collisions

Older versions (and a File Format with no unique token, e.g. `{date}-{time}_{count}`) could give two **different** media the same file name. Only one file was kept, but **both** were recorded as downloaded, so the lost one was never retried.

`recover_collisions` finds those media in a model's database and marks them **not downloaded**, so the next normal scrape fetches them again. It never touches your files, and it can only bring back media the site **still offers**.

1. **Close OF-Scraper** (GUI and CLI).
2. Find the model's database: `<config>/<profile>/.data/<model_id>/user_data.db` (e.g. `~/.config/ofscraper/main_profile/.data/123456/user_data.db`; Windows: `%USERPROFILE%\.config\ofscraper\...`).
3. **Preview** (read-only):
   `python -m ofscraper.commands.recover_collisions "<path to user_data.db>"`
   Use the same Python that OF-Scraper is installed with (e.g. `~/.local/share/pipx/venvs/ofscraper/bin/python` for pipx on Linux).
4. **Apply** (saves an undo file next to the database first):
   `python -m ofscraper.commands.recover_collisions "<path to user_data.db>" --apply`
5. Run a normal scrape of that model. Your File Format must now give these media **different** names (e.g. include `{filename}` or `{media_id}`).

**Undo:** `python -m ofscraper.commands.recover_collisions "<db>" --undo "<db>.collision-undo-<id>.json"` previews; add `--apply` to restore.

Check the preview first: the same picture re-posted under a new media id shares a name with **identical content** (nothing was lost), and if you de-duplicated your library with **hard links**, different media really do share one file. The in-app Help (**Troubleshooting → Recovering files lost to old filename collisions**) has the full details.

## The GUI crashed or froze

Diagnostic files are written under your OF-Scraper config folder:

- `~/.config/ofscraper/gui_crash_logs/model_fetch_breadcrumbs.log`: recent UI and scrape steps (including whether a model fetch or scrape was running)
- `~/.config/ofscraper/gui_crash_logs/faulthandler.log`: native crash dumps when available

When reporting a problem, include the last ~30 breadcrumb lines and your GUI patch id. In Docker these files are on the mounted config volume.

**Verbose Log** (bottom of the sidebar) shows every log level in the app and writes a separate verbose log file, which helps with harder problems.

## The window flashes or draws badly

On Windows and Linux the GUI turns on Qt's newer widget renderer (`QT_WIDGETS_RHI=1`) so opening the App Browser login doesn't make the whole window flash. If you see drawing problems instead, start the GUI with `QT_WIDGETS_RHI=0`, e.g. `QT_WIDGETS_RHI=0 ofscraper --gui`.

## Plugins

- Plugins aren't installed by the patch; get them from [`Available Plugins/`](../Available%20Plugins). See [Plugins → Getting the plugins](plugins.md#getting-the-plugins)
- A plugin with missing packages shows a one-click install dialog. If that fails, install the packages into the same environment as OF-Scraper (e.g. `pipx inject ofscraper <package>`)
