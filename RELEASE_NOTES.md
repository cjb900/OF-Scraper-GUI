# What's New

---

## Unreleased (draft) — OF-Scraper GUI on OF-Scraper-Community 3.16.1

The GUI moves from OF-Scraper 3.14.7 to [OF-Scraper-Community](https://github.com/cloakedkeys/OF-Scraper-Community) **3.16.1**, the maintained fork of OF-Scraper. New patch: **`patch_ofscraper_3.16.1_gui.py`** (patch **`20261107_gui_3_16_1_v419`**). The GUI itself is the same as `v419`. The 3.14.7 patch stays in the repository for existing installs.

### ⚠️ Changes to check before moving

- **Install from GitHub.** OF-Scraper-Community is not on PyPI (PyPI's `ofscraper` is the older 3.14.7). The patch script installs it from GitHub with pip, pipx or uv, which needs **git**. If you install it yourself: `uv tool install git+https://github.com/cloakedkeys/OF-Scraper-Community@3.16.1` (or the same URL with `pipx install`).
- **Python 3.11 to 3.15** are supported. Python 3.13 to 3.15 no longer fall back to 3.12.
- **`filename_collision` now defaults to `"media_id"`** (it was `"overwrite"`): when two media get the same file name, both are kept, the second as `name_<media_id>`. This applies when the setting is missing from config.json; a config.json that already has it keeps its value. Set it to `"overwrite"` to keep the old behavior.
- **Docker** builds 3.16.1 by default (`GUI_PATCH_VERSION: "3.16.1"`); rebuild the image.

### New from OF-Scraper-Community

- **Fansly**: posts, messages, purchases and livestream recording, from the command line (`site` setting). The GUI's pages are still OnlyFans-only.
- **Downloads that don't hang**: requests and TLS handshakes time out instead of waiting forever, the download speed limit works, and a cancelled request is not retried.
- **Clearer login problems**: a logged-out session shows as bad auth, network errors as network errors.
- **Command line**: `--before` / `--after` take `MM/DD/YYYY` and dates like "3 weeks ago"; a bad option prints a short usage message; a failed run exits with status 1.
- **Settings read as written**: `incremental_downloads: false`, `cache-mode`, `download_sems: 0`, upper-case user-list names and unknown dynamic rules now behave as the config says.
- **Database**: table rebuilds and merges keep every row; stories are updated and messages keep their deleted flag.
- The session cookie is masked in every log line.

### Kept from the GUI

- The remote key helper (`cdrm`) still gets only the pssh and the licence URL, never your cookies (the fork sends them). Manual key mode is still recommended.
- The purchased-scan warning names the error without the request headers.
- All GUI settings and behaviours, including the host allowlist, API path and endpoint overrides, signing rules in config, per-type file extensions and the DRM length threshold.

### Fixes found during the move

- The GUI no longer offers PyPI's 3.14.7 as an "update" to 3.16.1.
- The patch script reads `pipx list --json` again (`json` was never imported, so it always fell back to slower checks).
- Each scrape no longer leaves an unclosed event loop behind in the Discord log handler.

---

## 2026-11-01 — Update (September–November 2026) — OF-Scraper GUI 3.14.7

Everything since the **2026-08-29** release (patch `v365`, Live Stream Monitor `1.3.1`). GUI patch tip is now **`20261101_gui_3_14_7_v419`**; **Live Stream Monitor** is **`1.3.18`**. Only the **3.14.7** patch is maintained; the 3.12.9 / 3.14.3 / 3.14.5 patches are still in the repository but only got the installer fix below.

Re-apply with `python patch_ofscraper_3.14.7_gui.py`. Docker: copy the new patch and `docker/*` into the build context, then `docker compose build --no-cache` and recreate the container. Plugins: install the new `.zip` from `Available Plugins/` on the **Plugins** page.

### ⚠️ Changes to check after updating

- **Text Length > 0** now really shortens the post text in filenames (it was ignored before), so those filenames change for new downloads (v371).
- Short CLI flags: `ofscraper metadata` **`--mark-stray-locked` is now `-msl`** (`-ms` stays `--mass-skip`); **`--promo-skip` is now `-psk`** (`-ps` stays `--post-script`) (v393 / v394).
- New config option **`filename_collision`**: default `"overwrite"` keeps the old behavior; `"media_id"` keeps both files when two media get the same name (v383).
- Two debugging features are now opt-in: WebEngine remote debugging (`OFSCRAPER_GUI_WEBENGINE_DEBUG=1`) and periodic hang dumps (`OFSCRAPER_GUI_HANG_DUMP_SECONDS`) (v395 / v398).

---

### New GUI actions

- **Update metadata from files on disk (no downloads)**: the same job as `ofscraper metadata`. Update / Check / Complete mode, mark unmatched media as locked, optional file-hash check. Saved in History and can be re-run (v391).
- **Download all purchased content (all creators)**: everything you bought from every creator, including expired subscriptions and deleted accounts, like `--scrape-paid`. An **Exclude creators** box with a **Pick…** list (it can load your subscriptions for you), plus media types; it skips the Areas and Models pages (v392, v396, v397, v416).

### Scraping fixes (merged community PRs #2–#28)

- FFmpeg 8+ works for DRM videos (`strip_pssh`).
- Text Length / Text Type in filenames work, with a correct word count.
- A path that can't be resolved no longer fails a finished download; quotes around path settings are ignored, and the GUI's own checks no longer warn about them.
- Messages: paging no longer skips or wrongly "deletes" messages at chunk edges or exactly at `--before`.
- Deleted accounts no longer cause tracebacks or show up in the normal scrape.
- `--scrape-paid` respects `--excluded-username`; paid scrapes show correct per-creator counts and keep every creator in the table.
- Filename collisions can be handled (`filename_collision`), and a new offline `recover_collisions` tool can preview, apply and undo a recovery.
- Smaller fixes: unencodable characters print as `?` instead of crashing, one asyncio lock per event loop, server-set cookies are ignored, the terminal model selector restores its output, and newer Python versions work for source installs.

### Daemon, shutdown and stability

- The CLI daemon stops cleanly on SIGTERM / Ctrl+C, and **SIGUSR1** starts the next run now. The GUI cancels the scrape and quits cleanly on SIGTERM / `docker stop`, and records that run as *cancelled* (v386, v387, v390).
- Fixed Windows crashes: one 5 minutes after start (hang dump) and one when closing the GUI (safe shutdown order, also on any Python exit) (v395, v405, v406).
- Manual key mode with missing CDM files fails once with a plain message, and skipped DRM videos no longer write a traceback each (v401, v402).
- **Delete model DB / Also delete downloaded files** now work on every scrape in a GUI session, not only the first (v411).

### Privacy and security

- Request headers (cookie, `x-bc`, `sign`) can't leak into logs through exception text; two download log lines hide the media link (v377, v398).
- WebEngine no longer runs with `--disable-web-security` or open remote debugging (v398).
- Privacy mode now also covers: the DRM and Merge pages, the **Download all purchased** exclude box and Pick… list, the account name in **Test Credentials**, and the Scraper console (usernames and model IDs of loaded creators, and username lists in logged settings) (v403, v415–v418).

### GUI improvements

- **Select Models**: ticked models hidden by the search box are counted in orange, and **Next** asks whether to include them. The per-model chips above the table are cleared for each new selection and scrape (v412).
- Easier-to-read colors in both themes, disabled controls that look disabled, one page-title style, Next in the bottom-right corner of the Areas page, a Filters panel that fits and remembers its width, and fewer colored toolbar buttons (v403, v404, v407, v408).
- No more whole-window flashing when opening the App Browser on Windows and Linux (v399, v400).
- While cancelling, only **Cancel** reads "Cancelling…"; the daemon **@here Discord mention** option has a **?** help button (v419).

### Installer (`patch_ofscraper_3.14.7_gui.py`)

- `--force` reinstalls ofscraper and all GUI packages from scratch to repair a broken install; `--force --skip-deps` reinstalls only ofscraper (v409).
- On Python 3.13+, the pipx option downloads a Python 3.12 for ofscraper when none is installed (v389).
- When pipx is missing, the help matches your OS (no more `sudo apt install pipx` on Windows), and the menu lets you pick another option. Also in the 3.14.5 / 3.14.3 / 3.12.9 installers (v413).
- pipx / uv installs no longer reinstall the GUI packages on every run (v414).

### Docker

- **`MODE=cli`** runs the CLI daemon without the GUI.
- The desktop resizes to fit the browser window (TigerVNC), and the GUI stays maximized.
- **Login in App Browser** works in the container (v410).
- Color emoji font, so emoji no longer show as boxes.
- Docs: the config folder must be mounted at `/root/.config/ofscraper`, and how to fix `exec /entrypoint.sh: no such file or directory` (Windows line endings).

### Live Stream Monitor plugin (1.3.1 → 1.3.18)

- **Headless capture** by default (no browser window), using the Authentication login (cookies, user-agent and x-bc) (1.3.6).
- **Stops by itself when the stream ends**, usually within seconds: it reacts to OnlyFans' "Live video has ended" message after checking with OnlyFans, with the monitor poll as a backup (1.3.7, 1.3.8, 1.3.11).
- **Starts recording within seconds**: no more fixed waits before the login check, the player and the audio (1.3.12, 1.3.13).
- **Discord @here alerts** when a creator goes live and when the stream ends, with a warning if no webhook is set (1.3.9, 1.3.10, 1.3.14).
- When you tick **Enable Auto-Capture**, it asks whether to start the monitor every time the GUI launches; monitor logs stay out of the Scraper console, and it always watches all your subscriptions (1.3.15).
- An OnlyFans alert over the JOIN button no longer leaves a capture stuck on "Connecting". The plugin **never accepts anything**: it only closes such alerts, and logs which button it used (1.3.16, 1.3.17).
- Less memory when saving recordings, the FFmpeg path from Configuration, Chrome's sandbox kept on where possible, and faster Stop (1.3.4).
- Its own log file, and Privacy mode hides creator names in its console (1.3.11, 1.3.18).

### Docs and CI

- The README was split into `docs/` (install, GUI guide, plugins, Docker, troubleshooting, versions), with a new logo and **new screenshots** taken in Privacy mode.
- Plugins ship as zips in `Available Plugins/`.
- CI runs the GUI tests on the `testing` branch too (with FFmpeg and the Qt libraries).

---

## 2026-08-29 — Major update (June–August 2026) — OF-Scraper GUI 3.14.7

Large feature, safety, and stability pass for **OF-Scraper 3.14.7**. This entry consolidates everything that previously shipped as separate dated notes after **2026-05-17**, including authentication / 2FA cookie reliability work, the mid-August GUI hardening series, Advanced **API resilience** settings, and **Live Stream Monitor** through v1.3.x.

Re-apply with `python patch_ofscraper_3.14.7_gui.py` (or the latest release asset; tip **`20260829_gui_3_14_7_v365`**). Docker: sync the patch into the compose build context, then `docker compose build --no-cache` and recreate the container. Crash logs (desktop and Docker config mount): `~/.config/ofscraper/gui_crash_logs/`. Optional plugins live under `example_plugins/` — copy into `~/.config/ofscraper/plugins/` (or `%USERPROFILE%\.config\ofscraper\plugins\`) and **Enable** + **Load now** on the Plugins page.

High-level Discord paste notes: `RELEASE_NOTES_DISCORD.md`. Engineering chronology (patch-by-patch): `UI_IMPROVEMENTS.md` in the Pika tree.

---

### About & GUI text size

Click the sidebar version control (e.g. **`v3.14.7`**) — styled like Light / Verbose / Privacy so it reads as a real button — or **Help / README → About** to open a single-instance **About OF-Scraper** window (later clicks focus the same window).

About shows:

- **App version**, **GUI patch** id, **Operating system**, **FFmpeg**, and **FFprobe**
- **Updates** status plus **Check for updates** / **Open PyPI** (PyPI, same source as the CLI). Startup also quietly checks PyPI and can prompt once when a newer release exists.

**Text size** lives in About (and is mirrored on the Help toolbar):

| Control | Behaviour |
|--------|-----------|
| **A−** / **A+** | Step through allowed sizes |
| Size dropdown | **12**, **13** (default), **14**, **16**, **18**, **20** px |
| **Reset** | Restore default **13** px |

The preference scales the **whole GUI** (theme QSS, pages, dialogs, Help HTML, status chips) via `ofscraper/gui/utils/ui_scale.py` (`scale_px` / `apply_font`). It is saved as `gui_font_size` in `gui_settings.json` (legacy `help_font_size` migrates automatically). Like the theme toggle, size changes defer while a model list is loading or a scrape is running. The sidebar ASCII logo stays at a fixed size and is **not** scaled with text size.

---

### Authentication & sessions

**Login in System Browser** and **Login in App Browser** both support **Cancel Login**, an elapsed wait timer while credentials are pending, and an optional hard timeout that auto-cancels after N minutes with a warning. Cancel no longer destroys running QThreads mid-CDP: the cookie-fetcher and CDP listener are stoppable, cleanup waits for them to finish (terminate only as a last resort), and threads are detached from the dialog before it is destroyed — preventing the previous hard crash of “QThread destroyed while still running.”

**Import Cookies** runs on a background `QThread` with a cancelable progress dialog (closing the dialog cancels). Cookie DB decrypt walks poll for cancel at safe checkpoints so aborting does not leave partial credentials in the form. On Windows builds, Chrome-family **Import Cookies** remains Linux-oriented; **System Browser** login still works with any browser in the dropdown.

Auth storage is tightened with a cookie **allowlist** (`sess` / `auth_id` / `auth_uid*` / `x-bc` / UA), restrictive `auth.json` permissions, rejection of lookalike cookie hosts, and dropping of unrelated browser cookies. Remote CDM helpers (**cdrm** / **cdrm2** / **keydb**) **never send session cookies** in the key-request payload.

The Auth page adds **(?)** help on Credentials, Import Cookies, System Browser, App Browser, and Auth Issues; shorter on-page hints; sticky Save/Test under a scroll body so credential fields are not crushed on short windows; theme-aware Select Browser combo and System Browser Login Sync labels (readable in Light Mode).

**User-Agent on Import Cookies** was reworked so auth headers match what OnlyFans actually sees:

- Stop synthesizing a Chrome UA for Windows Zen; resolve the Gecko milestone / profile UA instead.
- Detect active Firefox/Zen **User-Agent Switcher** overrides; ignore disabled leftover addons so stale spoofs do not trigger a paste prompt.
- Prefer live `navigator.userAgent` via remote debugging (**CDP**) when a browser is available.
- Do **not** force Fingerprinting Protection’s frozen `Firefox/115` when Network still sends the real Gecko milestone (common on Zen).

**2FA / `auth_uid` reliability:** the dynamic `auth_uid_<user_id>` cookie key is supported; GUI import matches any `auth_uid*` cookie; Client Hints + `accept-language` are sent on API requests to reduce Cloudflare challenges.

When the subscription model list cannot be loaded, the **Unable to Load Models** dialog asks you to re-check auth and, if credentials look correct, try **Configuration → Advanced**: change **Dynamic Mode** and/or set **SSL Verify** to **`false`** (helps some TLS / certificate / proxy setups; less secure). Shortcuts include **Dynamic Mode (Config)**, **SSL Verify (Config)**, **Go to Authentication**, and **Help / README** (Auth Issues).

**Auth Issues** Help is ordered for multiple auth methods: prefer Import Cookies / System Browser / App Browser first; if those fail, open DevTools → **Network**, filter **`init`**, stay on the **main OnlyFans timeline**, **refresh**, and copy `sess` / `auth_id` / `auth_uid*` / User-Agent / `x-bc` from Request Headers into Credentials; then Dynamic Mode / SSL Verify and environment tips.

**Test Credentials** and **Unable to Load Models** explain OnlyFans **Wrong user** (API code **301** — typically a `sess` / `auth_id` mismatch, missing `auth_uid*` for 2FA, or an already-invalidated session) with actionable re-import steps instead of cryptic Python errors such as `'NoneType' object is not subscriptable` when the profile response was empty.

---

### Safety & scrape UX

A dedicated red **Cancel** on the table toolbar appears for every start path (Start Scraping, check modes, manual URL, daemon). **Cancelling…** disables Start until the scraper thread exits. Cancel is cooperative first (`_gui_cancel_event`): download consumers stop between items; API pagination, mid-file chunk loops, per-model action boundaries, and cookie decrypt walks all check the flag. A force `KeyboardInterrupt` is injected only after a **5s** grace if the thread is still stuck.

Before large jobs, the GUI can **Confirm scrape** (size/ETA), **Confirm cart / Send Downloads**, and run **disk space** checks (critical <256 MiB always; estimate×1.25 / <2 GiB for download jobs; skip like/unlike-only; “Don’t ask again” for non-critical). **Config validation** runs on Save and before scrape (Save Location, File/Directory Format uniqueness and confinement, FFmpeg path, empty download filters).

**Privacy / demo mode** (sidebar toggle, persisted) masks credentials, paths, Discord webhooks, table usernames, Select Models names/prices/avatars, failure-dialog Model column, and status lines like `Processing <user>…`, plus extra console redaction of cookies / webhooks / home paths.

New installs default **Key Mode → manual**. Configuration → CDM shows an inline banner for remote modes, Save requires confirm, and pre-scrape warns that remote helpers may send session material (“Don’t ask again this session”). First-run **Welcome** appears before missing FFmpeg/CDM prompts; missing-deps dialogs are rewritten for safety (no `QTextBrowser`, blocking `exec()`, navigate only after close), with the FFmpeg download link restored in visible blue and a QMessageBox fallback if the custom dialog fails to import. Areas no longer races model fetch against that dialog.

**Light Mode** toggle waits / is deferred while model fetch or scrape is active so stylesheet swaps cannot collide with worker teardown. Empty-table overlay copy is contextual (ready / scraping / filters / none found) and fully hidden when rows exist. Manual post/URL scrapes bind models after download so the results table and Final Stats Summary populate. Check mode honors **Allow duplicates** and receives advanced options before auto-start (Areas **Next** emits them; check args also fall back to the live checkbox / `gui_settings.json`). Scrape History timestamps use the local system clock (new runs store local; When column converts older UTC entries).

---

### Status strip & results table

The scrape table footer uses a unified **status strip**: phase badge, status text, progress, daemon countdown, row count, **Auth / Config / Key** health chips, and a live **elapsed timer** (`m:ss` / `h:mm:ss`) while Running/Cancelling (final value remains on Complete). Per-model live success/fail badges update during the run; Final Stats snapshots per-model counters before each model resets globals so Action Download lines and GLOBAL RUN TOTALS sum correctly.

After Final Stats, a **Download failures** dialog (up to 500 tracked failures with model, media ID, type, post ID, reason) can filter the table to failures or add them to the cart for retry. **History** keeps the last 20 runs with Details / Re-run this (restores models/areas/mediatypes; skips delete/daemon flags). **Filter presets** (save / rename / last-used / delete; up to 40 in `filter_presets.json`), **sticky columns** with layout persistence (`column_layout.json`) and header Hide/Show/Reset, **Export CSV**, and empty-table guidance are available. Click **username** to select models; click **Post ID / Media ID** to open OnlyFans. Check-mode-only cart toolbar, multi-select cart, and daemon **last-run** + **next-run** countdown with wall-clock ETA round out the table UX.

Left-nav icons are colored for Scraper, Authentication, Configuration, DRM, Profiles, Merge DBs, Plugins, and Help; loaded plugins add their own entries. The scrape console sits in a vertical splitter: drag to resize, height is debounced into `gui_settings.json` (~5s after the last move, with a single settle log line), double-click the splitter to reset ~180 px, and height restores correctly on relaunch / page entry (non-stretching console pane). Light Mode picks darker amber/green for WARNING/summary console lines; the console rebuilds visible colors on theme toggle.

Select Models uses Consolas columns with a Username / Subscribed / Price header; avatar header inset is measured from Qt layout (`QStyle.SE_ItemViewItemText`) so columns stay aligned when Show Avatars is on. Areas & Filters: Duration/Price Enable alignment, tighter group spacing (help on first content row), and uniform QGroupBox chrome.

---

### Duplicates & check mode

**Allow duplicates** plus optional **Also keep Messages + Purchased copies of the same media** (default off) keeps other-area reposts while collapsing Messages↔Purchased/Paid to Messages only when keep-both is off. Multi-area scrapes no longer double-queue the same `(media_id, post_id)` / post id when keep-both is off (Purchased re-adding the same post into `raw_posts` was previously treated as a second download under Allow duplicates). Check mode builds from `raw_all_media` when Allow duplicates is on so multi-area/repost rows are kept.

---

### Configuration — Scripts & paths

A new **Scripts** tab covers all five `script_options` paths (`after_action_script`, `post_script`, `naming_script`, `after_download_script`, `skip_download_script`); empty/`null` disables each. Load/save use the correct `script_options` key; a legacy `scripts_options` typo is migrated away on Save; the duplicate Post Script field was removed from Download.

**Preferred file extensions** on Scripts: per-type checkboxes for **Images / Videos / Audios** (off by default) remap only `{ext}` — no convert/remux and no other filename changes. Keys: `override_image_extension` / `override_video_extension` / `override_audio_extension` (plus `image_extension` / `video_extension` / `audio_extension`). Legacy `override_file_extensions` migrates to all-three-on until Save. Applied in `Placeholders` for main download, DRM alt download, and metadata paths; an external naming script still owns any returned full path.

Windows filesystem paths (Save Location, FFmpeg, CDM keys, temp dir) display and save with `\`; `json.dumps` writes `\\` in `config.json`. Format templates keep `/`. Config **Reload** clears **both** in-memory caches so a fresh `config.json` (including DRM key paths) is shown, and privacy-path scratch state is reset.

---

### Configuration — OnlyFans API resilience (Advanced)

Configuration → **Advanced** exposes config levers so many OnlyFans signing / path / CDN breaks can be handled without shipping a new code patch (environment variables still override when set):

| Setting | Purpose |
|--------|---------|
| **API Path** | Rewrite the default `/api2/v2` prefix globally (`OFSC_API_PATH`) |
| **Manual Dynamic Rules** | Paste or load local signing-rules JSON when Dynamic Mode is `manual` |
| **Dynamic Rules URL** | Custom remote rules JSON URL when Dynamic Mode is `generic` |
| **API Endpoint Overrides** | JSON map of endpoint keys (e.g. `meEP`) → full URL templates |
| **Media Host Suffixes** | Extra allowed media/DRM CDN hosts beyond `onlyfans.com` / `cloudfront.net` |

**SSL Verify** (`custom` / `true` / `false`) remains on Advanced as well. When model load fails despite good auth, try **`false`** (Save → Retry) — useful for some proxy / TLS-inspecting antivirus / broken CA-store cases; prefer `custom` or `true` when possible because `false` disables certificate checks.

In-app **Help → Configuration → Advanced** and the public GUI README document the same fields (screenshot-led README walkthrough + detailed Help). Configuration tab docs in Help and README were merged so both stay aligned.

---

### CDM / DRM / download integrity

**DRM Duration Match %** (default 98%) rejects empty/tiny muxes and compares remux duration to the API expectation. Short remuxes that were false-failing under a strict percentage (e.g. expected 12s, actual 11.71s) also pass when the shortfall is ≤ **1.0s** absolute slack. Stall watchdog plus stricter `.part` finalize / Content-Range resume reduce corrupt partials. Media host **allowlist** and runtime Save Location path confinement limit where downloads may land.

DRM keygen: a missing/broken `emulator-check` binary (often antivirus quarantine) is repaired when possible and is no longer treated as “no CPU virtualization” when Hyper-V/BIOS virt is present. AVD create prefers classic cmdline-tools (major ≤ 13), auto-replaces Android CLI wrapper installs that report success without writing system images, installs SDK packages one-by-one, and verifies system image files on disk before `avdmanager create`.

---

### Stability & crash diagnostics

Always-on crash breadcrumbs and Python `faulthandler` write under `~/.config/ofscraper/gui_crash_logs/` (`model_fetch_breadcrumbs.log`, `faulthandler.log`), with `sys` / `threading` / Qt fatal hooks. Every breadcrumb line includes `model_fetch=` / `scrape=` / `page=`; UI clicks, navigation, and scrape start/finish append markers without requiring Verbose Log.

Subscription model-list fetch (Areas / Select Models / CLI auto-start) was hardened against hard Qt crashes:

- Serialize concurrent OF fetches; hard asyncio timeout (default 180s).
- Install NullLive + quiet console stubs for the fetch duration (Rich Live / `console.print` from a worker was hard-crashing Qt).
- Soft-skip unparseable payloads; route worker failures through normal error signals.
- Cross-thread handoff is **plain dicts only**; `Model` instances are built on the main thread after env cleanup (live `Model` objects across QueuedConnection previously AVed).
- Windows uses `SelectorEventLoop`; NullLive/Model patch uninstall is deferred; the worker waits for a UI ack after publishing handoff so theme toggles and teardown cannot race.
- Normalize duck-types / uses the saved real `Model` class while the safe constructor is installed (avoids raw=64 → count=0).

**Scrape-time crash hardening:** force `args.no_rich = True` for GUI scrapes / check / manual URL; strip `RichHandler` after every `resetLogger()`; install NullLive on the **Qt main thread** before starting `gui-scraper`; emit reliable `scrape_started` / `scrape_active` so breadcrumbs show `scrape=1` while running. Help/About are single-instance; progress updates are throttled/batched.

---

### Docker

noVNC is unified on **`NOVNC_PORT=6699`**. The entrypoint **auto-restarts** the GUI after exit/crash (`GUI_RESTART_DELAY`). GUI stdout/stderr is teed to `logging/gui-docker.log` on the mounted config volume. The image creates `logging/`, `gui_crash_logs/`, and `device/` under config; the Dockerfile defaults to **3.14.7** and prints `Applied GUI patch: <PATCH_ID>` after apply. `GUI_ARGS` / CLI auto-start skips interactive scrape-confirm / disk / remote-key dialogs for unattended containers. Prefer the image FFmpeg (do not bind-mount host `ffmpeg`).

---

### Plugins

Sidebar **Plugins** page: Enable/Disable (`plugin_enabled`), **Load now**, and **Unload now** (`on_ui_teardown`) without a full restart. Example plugins were updated for clean unload (Immich, Live Monitor, LLM Assistant, AI Tagger, JoyCaption).

**Live Stream Monitor** (through v1.3.1): Playwright Chromium MediaRecorder is the supported live-capture path on Windows and Linux. Captures land in `{username}/Live_Streams/`, separate from the Areas checkbox **Streams** (API VODs in normal scrape folders).

- Base UX: durable log bridge (Stop/Unload mid-capture no longer crashes the host); recording timers; Privacy mode; Windows path normalization; `auth_uid*` cookie inject; Chromium install modal; theme-aware badges; subscriptions table expands under the header with a full-width terminal at the bottom.
- **Capture controls:** **Capture selected**, **Stop selected** / **Stop all** / per-row **Stop**; resizable subscription-table columns; selection preserved across poll refreshes; capture cooldown after stop/fail so Auto-Capture does not immediately re-spawn the same creator.
- **Diagnostics (optional):** **Diagnostics probe** (~45s redacted network evidence → `live_probe_reports/`); **Fetch live API dump** (redacted `/streams/active` + `/streams/active/url`, token *claims* only → `live_api_dumps/`); controls sit behind **Show diagnostics** (off by default; preference saved in `live_stream_settings.json`).
- **Native Agora experiment (discontinued):** an experimental Server SDK join path was evaluated on Linux. AccessToken2 claims matched the join arguments, but OnlyFans’ Agora edge rejected those joins (`CONNECTION_CHANGED_REJECTED_BY_SERVER`). That path is not a supported product feature; useful UX was merged into Live Stream Monitor, and the Agora example plugin is deprecated (`plugin_enabled = 0`).

---

### Docs

In-app Help expanded (About / Text size, auth options, Wrong user / Auth Issues, Scripts, Privacy, Live Monitor vs Streams, Allow-duplicates Messages+Purchased, crash diagnostics, DRM Duration Match %, API resilience, SSL Verify / auth-failure troubleshooting). GitHub README refreshed as product/feature docs (including About & text size); detailed changelog remains in these release notes.

---

## 2026-05-17

### Improvement — In-app Help / README updated with DRM Key Creation guide — *3.12.9, 3.14.3, 3.14.5, 3.14.7*

The built-in **Help / README** page has been updated to document the DRM Key Creation workflow, which was previously undocumented in the help text.

New **DRM Key Creation** section added (all four versions):

- System requirements (OS, CPU, RAM, Disk, Internet)
- First-run downloads list (~3 GB — JDK 17, Android SDK, system image, Frida server, Kaltura APK)
- Hardware virtualisation table (KVM / VT-x: 10–20 min vs software emulation / TCG: 45–90 min)
- Output files table (`client_id.bin`, `private_key.pem`) and default save location (`~/.config/ofscraper/device/`)
- Options reference (Extraction Script and Output Folder fields)

**3.14.7 only** — two additional sections added:

- **Authentication (Login in Browser)** — explains the embedded browser login feature step-by-step, the status bar indicators (`⚠ Not logged in` / `✓ Logged in`), how `auth_id` confirmation triggers credential reveal, the x-bc manual capture fallback via DevTools, the `PyQt6-WebEngine` requirement, and the KDE Plasma transparency note.
- **Duplicate column** — documents the Duplicate column in the Table columns reference (shows `Duplicate` highlighted in orange when the same `media_id` appears more than once; rows are skipped by the download pipeline unless **Allow duplicates** is enabled).

### Improvement — DRM Key Creation page: Requirements panel moved below console — *3.14.7*

The **Requirements & Information** panel on the DRM Key Creation page was displayed above the console output log, requiring the user to scroll past the full requirements block every time they wanted to see the extraction progress. The panel has been moved to below the console output, so the controls (Extraction Script path, Output Folder, Generate Keys button) and the live log are immediately visible on page load without any scrolling.

### Improvement — "Missing configuration paths" startup popup is now non-blocking — *3.12.9, 3.14.3, 3.14.5, 3.14.7*

The **Missing configuration paths** dialog (shown on startup when FFmpeg or manual DRM keys are not configured) was a blocking modal window. While it was open, it was impossible to interact with the main GUI window — so clicking **Open Config → Download (FFmpeg)** navigated the main window to the config page but the user could not interact with the config fields because the modal dialog was blocking everything.

The dialog is now non-modal. Clicking any action button opens the relevant page in the main window while the dialog remains open and visible for reference:

- **Open Config → Download (FFmpeg)** — navigates to the config Download tab and keeps the dialog open so the FFmpeg path instructions remain visible while you fill in the path
- **Open Config → CDM (Manual keys)** — navigates to the config CDM tab and keeps the dialog open for the same reason
- **Generate DRM Keys** — still closes the dialog and navigates to the DRM Key Creation page (since that is a full page navigation that replaces the need for the dialog)
- The intermediate **"Open Configuration? Yes / No"** confirm prompts have been removed — the action buttons now act immediately without a secondary confirmation step

### Improvement — FFmpeg download link updated in startup popup — *3.12.9, 3.14.3, 3.14.5, 3.14.7*

The FFmpeg download link in the **Missing configuration paths** popup previously pointed to `https://www.gyan.dev/ffmpeg/builds`, which no longer hosts FFmpeg version 7.1.1 (the last version known to work correctly with OF-Scraper). The link has been replaced with a direct download link to the 7.1.1 full build (`ffmpeg-7.1.1-full_build.7z`).

The popup text now also:

- Clarifies that the download link is for **Windows systems only**
- Adds an instruction to extract the 7z archive and provide the full path to `ffmpeg.exe` in the FFmpeg Path field in Configuration

---

## 2026-05-16

### Bug fix — DRM key extraction failing on Linux without KVM (TCG/software emulation) — *3.14.3, 3.14.5*

On Linux machines without hardware virtualisation (no KVM — e.g. VMs, WSL2, or hosts without the `vmx`/`svm` CPU flag available), DRM key extraction failed silently or was unreliable in ways that were difficult to diagnose. Several independent bugs combined to produce the failure.

#### 1. False success reporting — extraction script always exited 0

When the KeyDive hook succeeded but the UI automation step failed to trigger a Widevine licence exchange, `run_keydive()` returned `None` rather than `True`/`False`. The top-level `run()` function treated this as success and exited with code 0. The GUI showed the "✓ Key extraction completed successfully" message even though no keys had been written to disk. Users had no indication that the extraction had failed.

#### 2. UIAutomator commands hanging indefinitely on TCG (software) emulation

On TCG (software) emulation — the mandatory fallback when KVM is unavailable — `uiautomator dump` is far slower than under hardware acceleration and can stall completely when the emulator is under CPU pressure. The UI automation loop had a 600-second total budget but no per-command timeout. A single hung `uiautomator dump` call consumed the entire budget and the loop exited with no keys, again falsely reporting success.

#### 3. AVD `.ini` pointer file written to wrong location by newer `avdmanager`

After `avdmanager create avd` completed, the script looked for the `.ini` pointer file at `$ANDROID_AVD_HOME/<avd_name>.ini`. Newer versions of the Android SDK `cmdline-tools` (14.x) write this file to `$HOME/.android/avd/` regardless of whether `$ANDROID_AVD_HOME` is set. The emulator checks **only** `$ANDROID_AVD_HOME` when that variable is defined — it does not fall through to `$HOME/.android/avd/` — so the AVD was created successfully but the emulator immediately reported "Unknown AVD name" and exited.

#### 4. Kaltura APK install failing with no fallback

If the primary `adb install` of the Kaltura Device Info APK failed (network timeout, checksum mismatch, or an `INSTALL_FAILED_*` status), the script had no fallback. The KeyDive hook had nothing to attach to and the extraction failed silently.

---

All four issues are resolved in the DRM extraction script for 3.14.3 and 3.14.5, which has been replaced with the fully-fixed version from 3.14.7:

- **Exit codes**: `run_keydive()` now returns `True` on success and `False` on failure; `run()` calls `sys.exit(1)` on any failure path.
- **UIAutomator timeouts**: every `uiautomator dump` call now has a 45-second timeout; the overall UI automation loop budget is 1,200 seconds (20 minutes) to accommodate slow TCG boot and hook-attach times.
- **AVD `.ini` verification**: after AVD creation, the script checks whether the `.ini` pointer file exists at the expected location. If missing, it searches `$HOME/.android/avd/`, `$ANDROID_SDK_HOME/avd/`, and the SDK's own `avd/` directory for an alternate copy and copies it to the expected path. If no `.ini` is found anywhere, it synthesises one from the known AVD name and path.
- **Kaltura APK fallback install**: the script now tries multiple install methods in order — direct `adb install`, pushing the APK to `/data/local/tmp/` and running `pm install`, and as a last resort `adb shell pm install -r -t`. A dedicated download function retries the APK from the GitHub releases URL with progress reporting.

**Affected versions:** 3.14.3, 3.14.5, 3.12.9. The 3.14.7 script already contained all of these fixes.

### Bug fix — DRM emulator using wrong KVM acceleration flag on older Android emulators — *3.12.9, 3.14.3, 3.14.5, 3.14.7*

On Linux systems where `/dev/kvm` is present (hardware virtualisation is available), the emulator launch code passed `-accel kvm` to the Android emulator. Newer emulators (36.5.x) accept this value, but older ones (36.4.x — e.g. the version shipped with Pika OS's SDK) only accept `on`, `off`, or `auto`. The emulator exited immediately with `ERROR | Invalid '-accel kvm' parameter, valid values are: on off auto`, then the script fell back to slow software emulation (`-accel off`). Under software emulation, the emulator boot was unstable enough that the Frida server connection failed after rooting, producing a cryptic `device not found` / `could not connect to TCP port 5554: Connection refused` error even though the initial boot had completed.

Fixed by changing `-accel kvm` to `-accel on`. The `on` value requests the best available hardware accelerator (KVM on Linux) and is accepted by all emulator versions from 36.x onward. With KVM active, the emulator runs at native speed and the Frida connection is reliable.

A second, related issue was also discovered during testing: on some Linux kernels (e.g. the custom 7.x kernel shipped with Pika OS), KVM acceleration causes the Widevine DRM process to crash during the licence exchange, after the hook has already successfully attached and begun capturing key material. The emulator itself dies at this point, leaving no keys on disk. The script now detects this condition — the emulator process is dead and the fallback to software emulation has not yet been attempted — and automatically restarts with `-accel off` (software emulation) to complete the extraction. The output will show:

```
⚠️ Emulator crashed during DRM extraction under KVM.
 Some kernels have KVM + Widevine compatibility issues.
🔄 Retrying with software acceleration (-accel off)...
 NOTE: Software emulation is very slow — allow up to 15 minutes.
```

**Affected versions:** 3.12.9, 3.14.3, 3.14.5, 3.14.7.

### Bug fix — DRM key extraction broken on Windows 11 with frida 17.9.10 — *3.12.9, 3.14.3, 3.14.5, 3.14.7*

On Windows 11, attempting DRM key extraction with frida 17.9.10 (the version pip resolves to by default) immediately failed with:

```
AttributeError: module 'frida._frida' has no attribute 'Cancellable'
```

Root cause: the frida 17.9.10 Windows native wheel ships an incomplete `_frida` extension that is missing the `Cancellable` symbol. The attribute is present on other platforms (Linux, macOS) and in earlier frida releases, so the frida package imports cleanly on `pip install` but crashes the moment any frida API is called.

Fixed by adding a post-install validation step to `setup_keydive()`: after frida is installed or confirmed in the venv, the script runs `python -c "import frida; print(frida.__version__)"` inside the venv. If this command exits non-zero (import fails for any reason), the script automatically force-reinstalls with `frida<17.9`, which resolves to 17.0.x — a version with a working Windows wheel. The validated version is printed to the console:

```
 ✅ Frida 17.0.8 OK.
```

**Affected versions:** 3.12.9, 3.14.3, 3.14.5, 3.14.7.

### Bug fix — DRM key extraction reporting timeout despite successful key export — *3.12.9, 3.14.3, 3.14.5, 3.14.7*

On Linux systems running under TCG (software) emulation — the mandatory fallback when KVM is unavailable, such as on KDE Neon without nested virtualisation — DRM key extraction completed successfully (KeyDive exported the keys and logged them to disk) but `run_keydive()` returned `False` and the script printed "KeyDive timed out without extracting keys."

Root cause: KeyDive calls `adb emu kill` as part of its own exit sequence, not just when keys are exported. The emulator process dies before our UI automation loop has a chance to scan for output files. The existing file-scan only ran at fixed polling points inside the loop; if KeyDive had already exited and killed the emulator before the loop could check, the scan never ran and the function fell through to the timeout failure path.

Fixed with three layered checks:

1. **Post-exit scan** — when the KeyDive process exits unexpectedly inside the monitoring loop, the script immediately scans the output directory for `client_id.bin`. If found and > 500 bytes, the keys are copied and `True` is returned.
2. **Post-loop scan** — after the monitoring loop ends (by timeout or loop exit), a final scan runs before reporting failure.
3. **Pre-loop scan after `_ensure_kaltura_ready()` failure** — if the Kaltura readiness check fails (emulator already dead), the script checks for keys before reporting failure and returning.

**Affected versions:** 3.12.9, 3.14.3, 3.14.5, 3.14.7.

### Bug fix — DRM Kaltura APK install failing on TCG emulation with "Performing Streamed Install" error — *3.12.9, 3.14.3, 3.14.5, 3.14.7*

On TCG (software) emulation, `adb install` without the `--no-streaming` flag fails with:

```
adb: failed to install...: Error: Performing Streamed Install
cmd: Can't find service: package
```

KeyDive's own internal install path does not pass `--no-streaming`, so the Kaltura Device Info APK could not be installed on TCG emulators. Without the APK installed, KeyDive was unable to trigger the Widevine licence exchange and exited without extracting any keys, then killed the emulator.

Fixed by adding a `_preinstall_kaltura()` step that runs before `run_keydive()` is called. It attempts installation in order: `adb install --no-streaming -r -g`, `adb install -r -g`, and `adb shell pm install -r /data/local/tmp/tmp.apk`. If any method succeeds (exit code 0 or "Success" in output), the method returns after confirming the package is visible to `pm list packages`. When KeyDive starts, the APK is already installed and it skips its own install step, avoiding the streamed-install failure entirely.

**Affected versions:** 3.12.9, 3.14.3, 3.14.5, 3.14.7.

### Bug fix — DRM Kaltura pre-install failing: "Can't find service: package" immediately after boot — *3.12.9, 3.14.3, 3.14.5, 3.14.7*

Even with the `--no-streaming` fix in place, the Kaltura pre-install continued to fail on TCG emulation with:

```
cmd: Can't find service: package
```

Root cause: Android emits `sys.boot_completed=1` (which the `wait_for_boot()` step waits for) before the Android package manager service (`PackageManagerService`) has finished initialising. On hardware-accelerated emulators, the gap is milliseconds and not noticeable. On TCG software emulation — where a single CPU core is emulating the guest — the package manager can take 60–120+ seconds after boot_completed before it is ready to accept `pm` commands. Any `adb install` or `pm list packages` call during this window fails with `cmd: Can't find service: package`.

Fixed by adding a `_wait_for_package_manager(timeout=180)` method that polls `adb shell pm list packages android` every 5 seconds until `package:android` appears in the output (meaning the package manager is ready) or the timeout is reached. This method is now called after `wait_for_boot()` and `install_frida()` in both the initial boot path and the software-emulation retry path.

With the package manager reliably ready before the pre-install attempt, `--no-streaming` install succeeds and the entire extraction flow completes correctly on all platforms.

**Affected versions:** 3.12.9, 3.14.3, 3.14.5, 3.14.7.

---

## 2026-05-15

### Bug fix — Scrape summary showing inflated duplicate count — *3.14.7*

After a full unfiltered scrape, the `| duplicates: N` figure in the scrape summary reflected all duplicate `media_id` occurrences across the entire live row set (e.g. ~4783 rows), producing inflated counts such as "1228 duplicates" that had no practical meaning.

Root cause: the count was derived from the full post-scrape row set with no regard for when the model's DB was last actually populated. Items in the DB from years ago were being included, so every row that shared a `media_id` with any historical row counted as a duplicate.

Fixed by querying `SELECT MAX(posted_at) FROM medias` against the model's database before the scrape starts. This gives the true content boundary — the date of the newest post already stored. Only rows on or after that boundary are counted for duplicates, so the figure represents "duplicates discovered since this model was last scraped." For example, if the DB was last populated on October 6, 2025, the duplicate count now reflects only new or reposted content from that date forward (e.g. 134 duplicates), not the entire multi-year history.

### Bug fix — Table showing only date-filtered subset on unfiltered scrape — *3.14.7*

When running a scrape with the After/Before date filters disabled, the content table showed only the rows that fell on or after the internal DB content boundary (e.g. 742 rows from October 2025 onward) rather than all rows the current scrape returned from the API.

Root cause: the same date cutoff used for the duplicate count was also being applied to filter the emitted table rows, so the table behaved as if a date filter were active even when none was set.

Fixed by decoupling the two operations: the DB content boundary is used solely for computing the duplicate count in the summary, and the full live row set is always emitted to the table unchanged. With no date filter active, all rows from the current scrape are now visible (e.g. 5350 rows for a creator with a large back-catalogue).

### Bug fix — Labels API rate limiting causing missing downloads — *3.14.7*

When a creator has a large number of label categories (40+), content tagged only in certain labels was missing from the download queue. In affected runs, typically 5–12 labels returned 0 posts and the per-label warning log confirmed rate-limit exhaustion as the cause.

Root cause: all label content requests were fired simultaneously as independent asyncio tasks. With 40+ labels each making their own HTTP request chain at the same time, the OnlyFans API reliably hit its rate limit. The HTTP client's retry logic exhausted all attempts while still rate-limited, so those labels returned empty and their content was permanently missed for that run.

Fixed by introducing an `asyncio.Semaphore(5)` around each label's producer task in `process_tasks_get_posts_for_labels`. At most 5 label fetches now run concurrently at any time — the remaining tasks queue up and acquire the semaphore as earlier ones complete. This gives the API rate window time to recover between batches and eliminates the burst that previously caused failures.

### Improvement — Warning log when a label returns 0 posts — *3.14.7*

A `[WARN]` line is now written to the console whenever a label category returns 0 posts after all request attempts:

```
[WARN] Label 'Car' (id=...) returned 0 posts after all retries — possible rate-limit failure; content count may be lower than expected
```

Previously these failures were completely silent. The warning makes it immediately visible which labels failed and flags the run as potentially incomplete, so you know to investigate rather than assume the label was genuinely empty.

### Improvement — TUI-style scrape summary with global totals — *3.14.7*

The scrape summary shown in the console panel at the end of each run has been redesigned to match the TUI output format. It now shows two sections:

- **Per-model action line** — one line per model scraped:
 ```
 [username][Action Download] (2.05 GB) (24 downloads total [10 videos, 0 audios, 14 photos], 0 skipped, 0 failed) | duplicates: 4 | DB: 20/20
 ```
- **GLOBAL RUN TOTALS** — aggregate counts across all models:
 ```
 📊 GLOBAL RUN TOTALS (ALL MODELS)
 ==================================================

 --- MEDIA DOWNLOADS ---
 ➜ TOTAL ITEMS: 24
 ➜ TOTAL DATA: 2.05 GB
 ➜ VIDEOS: 10 downloaded
 ➜ AUDIOS: 0 downloaded
 ➜ IMAGES: 14 downloaded
 ➜ SKIPPED: 0 overall
 ➜ FAILED: 0 overall
 ```

### Improvement — Scrape summary written to log file — *3.14.7*

The new TUI-style scrape summary is now also written to the ofscraper log file at `WARNING` level, so completed runs are permanently recorded alongside all other log output.

### Improvement — Startup log includes OF-Scraper and GUI patch versions — *3.14.7*

The first log line written when the GUI starts now includes both the installed OF-Scraper version and the applied GUI patch id (instead of a generic `OF-Scraper GUI started` with no version information).

### Bug fix — Progress bar total bytes not updated after scrape — *3.14.7*

After a scrape completed, the **Total** bytes counter in the footer progress bar remained at its last mid-download value (e.g. "289.7 MB") rather than updating to the confirmed final total. Fixed by emitting the confirmed total bytes from `_pending_summary_data` via `total_bytes_updated` once the summary has been rendered.

### Bug fix — Progress bar bytes overflow for scrapes exceeding 2 GB — *3.14.7*

When the total bytes scraped exceeded 2 GB (2,147,483,647 bytes — the 32-bit signed integer limit), the `total_bytes_updated` signal raised an `OverflowError` that was silently caught. The bytes label froze at the last valid mid-download value and never reflected the true total. Fixed by changing `total_bytes_updated` from `pyqtSignal(int)` to `pyqtSignal(float)` (64-bit double), which handles any practical file size without overflow.

### Bug fix — Progress bar bytes precision mismatch vs summary — *3.14.7*

The footer bytes label (e.g. "2.1 GB") and the TOTAL DATA line in the summary (e.g. "2.05 GB") formatted the same underlying value with different precision — `.1f` in the progress panel vs `.2f` in the summary. Both now use `.2f` precision so the displayed values always match.

### Bug fix — Scrape summary appearing twice in console output — *3.14.7*

The scrape summary was being emitted to the GUI console panel twice: once directly via `log_message.emit` and once via `log.warning()` routing through `GUILogHandler`. Fixed by removing the direct signal emit — `log.warning()` alone now handles both the log file and the GUI console.

### Improvement — Confirmation dialogs for Save Settings and Reset Settings — *3.14.7*

The **Save Settings** and **Reset Settings** buttons on the Select Content Areas & Filters page now show a confirmation dialog before acting, making it harder to accidentally trigger them.

- **Save Settings** — prompts "Save the current Content Areas & Filters selections?" (defaults to **Yes**). Cancelling leaves settings unchanged.
- **Reset Settings** — prompts "Reset all Content Areas & Filters options to their default values? This will also clear any saved settings from gui_settings.json." (defaults to **No** — safer default for a destructive action). Cancelling leaves settings unchanged.

Previously both buttons acted immediately with only a small status-bar notice in the corner, which was easy to miss.

### Bug fix — Browser login window transparent on Linux (KDE neon / KDE Plasma) — *3.14.7*

On KDE neon and KDE Plasma, the **Login in Browser** window appeared partially or fully transparent while the OnlyFans page was loading. The desktop or other windows behind the dialog were visible through the area where the web content should have been. Root cause: no background colour was set on the `QWebEnginePage` before the first page load, so the compositing window manager had nothing to render while Chromium initialised. Fixed by calling `page.setBackgroundColor(QColor(30, 30, 46))` immediately after the page is created, giving the browser view a solid background that matches the dialog chrome and is visible throughout the entire load cycle.

### Improvement — Login status indicator in browser login dialog — *3.14.7*

A **"⚠ Not logged in"** / **"✓ Logged in"** status badge has been added to the left side of the credential status bar in the **Login in Browser** dialog. Previously, some credential fields (`sess`, `x-bc`, `user-agent`) showed green ✓ marks even before logging in, because OnlyFans sets pre-login session cookies and generates `x-bc` headers for any page load — not just authenticated ones. This was confusing because it looked like valid credentials had been captured.

The new behaviour:
- All credential fields start blank (`—`) regardless of what the browser has captured
- Values are collected silently in the background while you log in
- The moment `auth_id` is received (which OnlyFans only sets on a successful login), all captured values are revealed at once and the status changes to **"✓ Logged in"**
- If a previous session is still valid in the persistent browser profile, the dialog opens already showing all credentials and **"✓ Logged in"**
- **"Use These Credentials"** remains disabled until `auth_id` is confirmed

### Bug fix — Fresh-install terminal spam: missing auth.json log repeating thousands of times — *3.12.9, 3.14.3, 3.14.5, 3.14.7*

On a completely fresh install — no existing ofscraper config directory, no `auth.json` present — launching the GUI caused the terminal to flood with the same log line about a missing `auth.json` file repeating continuously until the application was force-killed. The line count routinely reached several thousand per second.

Root cause: the GUI startup path calls `read_auth()`, which is wrapped in a `while True` retry loop. Each iteration attempted to read `auth.json`, caught `FileNotFoundError`, and delegated to the error handler. In GUI mode the error handler was designed to skip the interactive terminal prompt (which would freeze the GUI) and return `None` to signal "retry." However, the handler never actually created the missing file, so the next retry raised the same `FileNotFoundError` again — producing the infinite loop.

Fixed in all four supported versions:

- **3.14.3, 3.14.5, 3.14.7** — `utils/auth/utils/error.py`: the `FileNotFoundError` branch in GUI mode now creates an empty `auth.json` (using `auth_dict.get_empty()`) before returning `None`. The retry loop reads the newly created file on the very next iteration, parses it as an empty-but-valid auth object, and breaks.
- **3.12.9** — `utils/auth/utils/context.py`: same fix applied to the `auth_context()` context manager, which is the equivalent error-handling layer for the 3.12.9 architecture. When `FileNotFoundError` is caught in GUI mode, an empty `auth.json` is created before returning so the retry loop breaks cleanly.

In all cases: if the file creation itself fails (e.g. a permissions error writing to the config directory), the error handler returns `"quit"` instead of `None`, which causes `read_auth()` to exit cleanly rather than spinning forever.

---

## 2026-05-13

### Bug fix — Allow Duplicates not working on Linux — *3.14.5*

When **Allow duplicates** (`allow_dupe_downloads`) was enabled, scrapes on Linux produced fewer downloads than expected and in some cases silently failed on items that succeeded on Windows. Four separate root causes were found and fixed.

#### 1. Temp-file collision for concurrent duplicate downloads

When the same `(media_id, post_id)` pair appeared multiple times in the download queue — for example, the same post indexed in both Timeline and Labels — two async download coroutines opened an identical `.part` temp file simultaneously in append mode, interleaving writes and corrupting the download. Both coroutines returned as failed. Fixed by appending a `_dup_seq` suffix to the temp filename for duplicate media objects (the suffix is already assigned during queue preparation), so each coroutine gets its own unique temp file. Result: all duplicates in the queue download successfully and land on disk as separate files.

#### 2. `dupefiltermedia` stripping duplicates from the queue

Linux installs with an older `filters.py` were missing the `allow_dupe_downloads` bypass in `dupefiltermedia()`. The function always deduplicated by `media_id` alone — stripping 4 items from the queue — regardless of the GUI setting. Fixed in `postcollection.py`'s `get_media_to_download()`: when `allow_dupe_downloads=True`, `dupefiltermedia` is skipped entirely. Only items with the same `(media_id, post_id)` pair are treated as duplicates, so reposts of the same media in different posts are correctly kept.

#### 3. `find_unique_path()` not available on older Linux installs

When `allow_dupe_downloads=True` and a downloaded file already existed at the destination, `main_download.py` and `alt_download.py` called `common_paths.find_unique_path()` to find a `filename(1).ext` slot. That function was added to `paths.py` in our source tree but not included in the patch, so older Linux installs threw `AttributeError`. The exception was caught silently by the download engine's inner `except` at DEBUG level — invisible in the GUI console — and returned `"skipped"`. Fixed by defining `_find_unique_path()` as a local module-level function in both `main_download.py` and `alt_download.py` (same logic, no external dependency). All items that previously failed as "skipped" now succeed, and each duplicate gets its own `filename(1).ext` / `filename(2).ext` file on disk.

#### 4. `previous_download_filter` too aggressive on older Linux installs

Even after the above fixes, Linux installs showed 478 downloads for a model where 595 were expected. The older Linux `filters.py` lacked the `allow_dupe_downloads` conditional in `previous_download_filter()`. It always filtered by `media_id` alone, so any duplicate media (same `media_id`, different `post_id`) whose original had already been downloaded was stripped from the queue — 117 extra items removed incorrectly. Fixed by adding `filters/media/filters.py` to the patch (now 67 files). The patched version filters by `(media_id, post_id)` pair when `allow_dupe_downloads=True`, so only the exact same post is treated as already downloaded, and reposts are correctly included.

### Bug fix — Messages incremental scan drops posts — *3.14.5*

When scraping messages incrementally (a re-scan after previously downloading some messages), some posts were silently dropped from the pipeline, causing the download count to be well short of the expected total — for example, 418 downloads instead of 592 after caching 640 messages with 63 new ones since the last scan.

Root cause: in `scrape_messages`, when the set of `required_ids` (cached post IDs not yet validated against a live API batch) became empty, the code executed `break` before the `yield batch` at the bottom of the loop. The "completion batch" — the API batch that contained the cached posts satisfying `required_ids` — was discarded in full. Only the batches before it (which contained only newly-scraped messages) reached the pipeline.

Fixed by adding `yield batch` immediately before the `break` in the completion path. The completion batch now yields before breaking, so all its posts (both newly scraped and cached) enter the pipeline. Also updated `_fetch_old_undownloaded_messages` (the safety net that catches any cached posts not yet written to the media DB) to query the messages table rather than the medias table, so posts whose media was never written are also caught.

---

## 2026-05-09

### Bug fix — Content table not populating during or after scrape — *3.14.3*

After starting a scrape, the content table showed **0 / N rows (filtered)** and remained empty throughout the run and after completion, even though the console confirmed content was being scraped and files were landing on disk.

Root cause — two separate issues compounded each other:

1. **`copy_filter_state_to()` was copying `resp_checks` and `media_checks` from the area selector page to the table sidebar.** On the area page, those checkboxes control which content types are *downloaded* — for example, leaving "Timeline" unchecked means timeline posts are skipped. When those states were mirrored to the table sidebar, the table's filter treated unchecked types as "hide these rows", so all timeline rows (or whichever types were unchecked) were immediately hidden.

2. **`_on_start_scraping()` called `apply_filter(collect_state())` at the start of each scrape.** This locked in the restrictive filter before any rows arrived, so every incoming row was tested against a filter that rejected its response type. Fixed by replacing that call with `reset_filter()`, which clears any stale filter and lets all incoming rows through.

Both changes are in `ofscraper/gui/pages/area_selector_page.py` (`copy_filter_state_to`) and `ofscraper/gui/pages/table_page.py` (`_on_start_scraping`). The table sidebar retains its own default state (all types shown) independent of the area page selection.

### Bug fix — Paid content not scraped (0 results) — *3.12.9*

When scraping paid content, the console logged `media found 0` and `hasmore undefined` for every creator, and no paid media was downloaded. The scrape count for affected creators fell significantly short of the correct total (e.g. 528 instead of 592).

Root cause: OnlyFans changed its paid content API endpoint. The old URL path (`/api2/v2/posts/paid`) and user-id parameter (`user_id=`) now return empty results. The new endpoint is `/api2/v2/posts/paid/all` with the parameter renamed to `author=`.

Fixed by updating both constants in `ofscraper/const/values/url/url.py`:

| Constant | Before | After |
|---|---|---|
| `purchased_contentEP` | `/posts/paid?…&user_id={}` | `/posts/paid/all?…&author={}` |
| `purchased_contentALL` | `/posts/paid?…` | `/posts/paid/all?…` |

Re-run the patch script to pick up the fix.

---

## 2026-04-20

### Duplicate column in content table — *3.14.7*

A **Duplicate** column has been added to the content table (between **Downloaded** and **Unlocked**). When the same `media_id` appears more than once in the API response — for example because a post is indexed in both Timeline and Archived — the first occurrence is left blank and every subsequent occurrence shows **Duplicate** highlighted in orange. Hovering over a Duplicate cell shows a tooltip explaining that the download pipeline will skip it.

When **Allow duplicates** (`allow_dupe_downloads`) is disabled (the default), duplicate rows also display `Downloaded: False` regardless of what the DB says about the original media item — making it clear those specific rows were not downloaded. The download pipeline behavior is unchanged; this is a purely visual indicator.

### Bug fix — Locked rows overwritten by download-status signal — *3.14.7*

After a scrape completed, rows whose **Download Cart** showed `Locked` could have that state silently overwritten by the `[downloaded]` status propagation signal. This happened because the signal handler iterated all rows sharing a `media_id` without checking the current cart state first. Fixed: the handler now skips any row whose cart cell already reads `Locked`.

The same protection was added to the `_raw_data` backing store sync so that a `Locked` cell cannot be overwritten there either.

### Bug fix — Re-scrape blocked by interactive "reset username" prompt — *3.14.7*

Clicking **New Scrape** (or any second scrape in the same session) caused the GUI to freeze while a **"Do you want to reset username info?"** prompt appeared in the terminal. This is an interactive TUI prompt in `managers/model.py` intended for CLI use. It was only bypassed for daemon mode; GUI mode was not covered. Fixed by extending the same bypass to `--gui` mode.

### Bug fix — No-date-filter scrape showing only live rows — *3.14.7*

When running a scrape with the **After / Before** date filters disabled (a full all-time scan), the content table showed only the rows the API returned during that run (e.g. 590 rows) instead of the full DB history (e.g. 4745 rows). Root cause: the `is_normal_gui_download` condition and its `elif` branch both assumed a date filter was active, so the full DB reload was never triggered for unfiltered runs. Fixed by adding a `_has_date_filter` check to both branches; unfiltered runs now always load the complete DB.

### Bug fix — Summary showing cumulative DB total instead of run count — *3.14.7*

For scrapes that reload the full DB (unfiltered runs, paid content, etc.), the scrape summary displayed the cumulative total already in the DB — for example `3489 downloaded / 4745 total` — rather than how many items were actually downloaded in the current run. Fixed: all code paths now store run counters from `common_globals` into `_pending_summary_data` so the summary always leads with the current run's count, e.g.:

```
creator_username: 339 scraped (115 videos, 224 photos, 0 audios) | DB: 3489/4745
```

### Bug fix — Progress bar inflated mid-run — *3.14.7*

During a scrape the **Downloads** progress bar showed a total larger than the number of items that would ultimately be downloaded — for example `Downloads: 362 / 652` while scraping, but `339 / 339` after completion. The inflated total came from the duplicate-count offset (`_gui_duplicate_count`) being added to the download queue size at the start of the download phase. Fixed by removing the offset: the progress bar total is now set to the actual download queue size, so the numerator and denominator stay consistent throughout the entire run.

### Bug fix — Previously-downloaded rows showing `Downloaded: False` after scrape — *3.12.9*

After a date-filtered scrape, rows for content that had already been downloaded in a previous run showed `Downloaded: False` in the table even though the **Download Cart** correctly read `[downloaded]`. These rows were not new failures — the console confirmed 0 failed, 0 skipped. Root cause: items filtered from the download queue by `previous_download_filter` (already-downloaded content) still went through `_emit_download_status`. That function queries the media DB by `model_id`; if a row's `media_id` was not found in that query (e.g. stored under a different `model_id` entry), the function emitted `downloaded=False`, overwriting the correct table state. Fixed by falling back to the build-time `downloaded` value stored in the row dict — if the row was already marked downloaded when the table was built, that state is preserved regardless of the DB query result.

---

## 2026-04-19

### OF-Scraper 3.14.7 support — *new version*

A new patch script `patch_ofscraper_3.14.7_gui.py` is now available, bringing the full GUI feature set to OF-Scraper 3.14.7. Because 3.14.7 contains internal API changes versus 3.14.5, several bugs were discovered and fixed during the initial port before the patch was released.

- **`get_rows_for_gui_table()` missing from `PostCollection`** — `workflow.py` called the method on startup; without it an `AttributeError` was silently caught and the download pipeline never ran. Fixed by adding the method to `postcollection.py`.
- **`verify_media_integrity()` crash on DRM alt-downloads** — `ffprobe.py` referenced `diff` before it was assigned when `expected_duration_seconds=None`. This caused every DRM alt-download to be silently "skipped" — the file was moved correctly via ffmpeg but the DB was never marked `downloaded=1` and the table was never updated. Fixed by initialising `diff = None` before the conditional block.
- **`system.get_parent_process()` removed in 3.14.7** — `alt_download.py` and `main_download.py` called `system.get_parent_process()` to decide whether to add the output directory to the global path list. That function was removed in 3.14.7; the original code simply calls `common_paths.addGlobalDir(filedir)` directly. Fixed by replacing the conditional with the direct call and removing the unused import.

### Date range not applied when Rescrape Everything enabled — *3.14.5 and 3.14.7*

When the GUI date range filter (After/Before) was configured alongside **Rescrape everything**, the date range was silently ignored. The `args.after = 0` assignment lived inside the `if rescrape_all:` branch, and the date range application block only ran in the `else` branch — so enabling Rescrape everything always overrode and discarded the date range. Fixed by moving the date range block outside the if/else so it always runs unconditionally and always takes precedence.

### Messages API date range — boundary batch dropped — *all versions*

When scraping a specific date range, messages that fell within the range could be silently lost if they were in the same API response page as older messages. The `scrape_messages` pagination loop breaks when the oldest message in a batch crosses the `after` boundary — but `yield batch` sits below that break, so the entire batch was discarded before any of its in-range messages could be collected. Fixed by filtering the boundary batch to only the in-range messages and yielding those before breaking.

### Progress bar and summary counting locked/paid content — *3.14.7*

The Downloads progress bar total and scrape summary were counting locked/paid rows as downloadable items. For example, a scrape with 42 table rows (including 3 locked videos) displayed "Downloads: 42/42" and "42 scraped (20 videos, 22 photos)" even though locked items cannot be downloaded. Fixed by excluding locked rows when computing the progress bar total and all summary counts. Locked rows remain visible in the table.

### Duplicate content — table and download pipeline fixes — *3.14.3 and 3.14.5*

Two bugs were causing duplicate/reposted content to be silently ignored even when **Allow duplicates** and **Rescrape everything** were both enabled in the GUI.

- **Duplicate posts filtered out of the content table** — in `postcollection.py`, when a post with the same `post_id` was encountered a second time, the new raw post instance added to `_raw_posts` did not have its `is_download_candidate` flag set. Only the canonical `existing_post` (which is not the object stored in `_raw_posts` for the duplicate) had the flag, so `get_rows_for_gui_table()` filtered every duplicate post out entirely. Fixed by propagating all action flags (`is_download_candidate`, `is_like_candidate`, etc.) from the canonical post to the incoming duplicate instance.
- **Duplicate media deduplicated regardless of GUI setting** — `get_media_to_download()` called `dupefiltermedia()`, which reads the `OFSC_ALLOW_DUPE_MEDIA` environment variable (always `False` by default) and ignores the `allow_dupe_downloads` GUI argument entirely. Fixed by checking `allow_dupe_downloads` directly: when enabled, media is deduplicated only by `(media_id, post_id)` pair so the same media appearing in different posts is kept; when disabled, `dupefiltermedia()` is used as before.

### Summary type-count mismatch fix — *3.14.3 and 3.14.5*

After a scrape, the summary line showed the correct total row count but broke down as `0 videos / 0 photos / 0 audios`, then fell back to the global download counters (which do not include duplicates). Root cause: the `global` declaration in `postcollection.py`'s `get_rows_for_gui_table()` was missing `_gui_video_count`, `_gui_photo_count`, and `_gui_audio_count` — writes to those names created local variables that were immediately discarded. Fixed by restoring the full `global` declaration.

### Scrape summary and progress bar consistency — *3.14.7*

The scrape summary shown at the end of each run previously read counts from the database totals, which could differ from the progress bar (which tracks downloads within the current run). The summary now reads `photo_count`, `video_count`, and `audio_count` from `common_globals` — the same per-run counters the progress bar uses — so the two always agree. The DB totals are still shown as a reference when they differ, e.g.:

```
creator_username: 39 scraped (17 videos, 22 photos, 0 audios) | duplicates: 4 | DB: 35/38
```

### Duplicate count in scrape summary — *3.14.7*

The GUI table now shows all raw media rows including items that appear in multiple API content areas (e.g. Timeline and Labels). The scrape summary appends `| duplicates: N` when N > 0 so you can see at a glance how many cross-area duplicates were present.

### Video quality selector — *3.14.7*

A **Video quality** combo box has been added to the **Advanced Scrape Options** section of the Select Content Areas & Filters page. Available choices:

| Choice | Behaviour |
|---|---|
| Default | Defaults to source/highest quality available on OnlyFans (same as selecting **source**) |
| 240 | Prefer 240p |
| 720 | Prefer 720p |
| source | Prefer the highest-quality original |

Corresponds to the `-q` / `--quality` CLI option. Full documentation has been added to the in-app **Help / README**.

### OF-Scraper version logged before scraping starts — *all versions*

The installed ofscraper version (`OF-Scraper version: X.X.X`) is now printed to the console log at the very start of each scrape run, before any scraping work begins. Previously the version line appeared at or near the end of the run, so if scraping errored out early it was never visible. Applies to 3.12.9, 3.14.3, 3.14.5, and 3.14.7.

---

## 2026-04-08

### Trial Link Scanner plugin — *new, all versions*

A new **Trial Link Scanner** plugin is now available (no changes to the main ofscraper package or patch files). It automatically scans for trial links and posts results to Discord via webhook. Place it in your ofscraper plugins directory to enable it.

Two bugs discovered during initial testing have also been fixed:

- **Settings not reflecting saved values** — the GUI combo boxes (Post timing, Post mode, Discord) reverted to defaults on every launch despite `settings.json` having different values. Root cause: `currentIndexChanged` fired mid-initialization before all combos were set, overwriting `settings.json`. Fixed by blocking signals on all combo boxes during `_sync_controls_to_settings()`.
- **Summary mode missing images** — when Post timing was set to `summary`, Discord messages included text and links but no images. Fixed by reusing the same per-entry send logic as immediate mode, so each entry in the summary gets its images uploaded as attachments.

### JoyCaption Tagger plugin fixes — *all versions*

Bug fixes for the JoyCaption Tagger plugin (no changes to the main ofscraper package or patch files).

- **Gallery capped at 2000 images** — the gallery query had a hardcoded `.limit(2000)`, causing folders with more than 2000 tagged images to display a truncated count. The limit has been removed.
- **No activity logging during folder scans** — scanning a folder produced no log output. Added `INFO`-level log messages for each image tagged (`JoyCaption: tagging …`, `JoyCaption: tagged … — N tag(s)`) and `WARNING` when no caption is returned. Errors that were previously swallowed silently in the scan thread now log at `ERROR` level.

### Discord scrape summary showing 0/0 — *all versions*

The per-run Discord summary (`[username] X/Y media downloaded`) always showed `0/0` for normal GUI download scrapes. Root cause: the code skipped reading DB stats entirely for normal downloads (to avoid replacing live table rows), leaving the stats dict empty. Fixed by adding a `stats_only=True` path to `_load_models_from_db` that reads stats from the DB without emitting table-replacement signals.

### Daemon mode — @here Discord ping — *all versions*

A new **@here Discord mention when new content is found** checkbox has been added to the Daemon Mode section of the Select Content Areas & Filters page. When enabled, the Discord scrape summary will be prefixed with `@here` — notifying your whole server — but only when new content was actually downloaded during that run. If a daemon run finds nothing new, no ping is sent.

- Requires a Discord webhook to be configured and the Discord updates checkbox to be enabled
- The checkbox is disabled until daemon mode is turned on
- The preference is saved to `gui_settings.json` and persists across sessions

### Daemon mode — table and Discord stats fixes — *all versions*

Four bugs affecting daemon mode (scheduled re-runs) have been fixed.

- **Crash on every run after the first** — `stop_live_screen()` in ofscraper's live display layer accessed `live.transient` on the GUI's `_NullLive` stub, which did not have that attribute. On daemon run #2+, `_NullLive.start()` had been called during run #1, setting `is_started = True`, so the early-return guard was skipped and the crash occurred. Fixed by adding `transient = False` to `_NullLive` and updating `start()` to accept the `refresh` keyword argument.
- **Table empty after daemon re-run** — the `_live_rows_emitted` flag was not reset between daemon iterations. After run #1 set it to `True`, run #2 would "skip DB table replacement" (correct behavior) but also skip emitting any live rows (since the run crashed before downloads began), leaving the table blank. Fixed by resetting `_live_rows_emitted = False` at the top of each daemon loop iteration.
- **Error tracebacks posted to Discord** — when a scrape run failed, the full Python traceback was sent to Discord because the Discord log handler was still active at the point the error was logged. Fixed by calling `_mute_discord_handler()` at the start of the error handler, and downgrading internal DIAG diagnostic log messages from `WARNING` to `DEBUG` so they do not reach the Discord handler.
- **Discord stats showing same cumulative count every run** — the per-run Discord summary always reported the same totals (e.g. 165/199 on every daemon run) because it was reading the cumulative DB totals rather than what was actually downloaded in that run. Fixed by reading `photo_count`/`video_count`/`audio_count` from `common_globals` (reset at the start of each daemon iteration) for the per-run new count, while the DB totals are shown separately as `downloaded/total in DB`.
- **Table showing only incremental rows on daemon re-run** — after a daemon re-run, the content table showed only the small number of newly downloaded items instead of the full model DB (e.g. 5 rows instead of 199). Root cause: the `is_normal_gui_download` and `elif self._live_rows_emitted` conditions were not guarded by `run_count == 1`, so run #2+ skipped the full DB load. Fixed by adding `and run_count == 1` to both conditions, forcing daemon re-runs to always reload the full DB.
- **Profile/avatar images showing as not downloaded** — profile images were filtered out of the download queue by `seperate_avatars()` before reaching `_emit_download_status`, so they were never checked against the profile cache and always appeared as `[]`/False in the table. Fixed by passing all filtered rows (`extra_table_rows`) to `_emit_download_status`, which now checks each row against the media DB with a profile cache fallback for Profile-type rows. Also fixed a second instance where all items were filtered (empty download queue), causing the `finally` block to be bypassed entirely via an early `continue`.

---

## 2026-04-05

### User Lists support (`--ul` / `--userlist`) — *3.14.5 only*

A **User Lists** field is now available on the **Select Action** page as a sub-option under "Download content from a user". Enter one or more OnlyFans list names (comma-separated) to load only models who are members of those lists — the full subscription list is never fetched in this mode.

- Leave blank to load all subscribed models (default, unchanged behavior)
- Reserved internal names (`main`, `ofscraper.main`) are automatically stripped and never used as list filters
- Equivalent to the `--ul` / `--userlist` CLI flag
- CLI auto-start is also supported: `ofscraper --gui --ul testing -a download -o all` will skip the wizard and start scraping automatically using the named list
- A **Reload Models** button appears in the navigation bar after models load, allowing re-fetching without returning to the Select Action page

### Include Post Text — *3.14.3 and 3.14.5*

A new **Include Post Text** checkbox has been added to the **Select Content Areas & Filters** page. When enabled, the text body of each post is included alongside the downloaded media.

### Discord notification level default changed to LOW — *3.14.5 only*

The default Discord notification level has been changed from **NORMAL** to **LOW**. LOW sends only important messages — warnings, errors, and the run completion summary — reducing Discord noise during large scrapes. On the first time Discord notifications are enabled, a one-time prompt asks whether to save LOW as the permanent default in `gui_settings.json`. The level can still be changed per-session on the Select Content Areas & Filters page.

> In 3.14.3 and 3.12.9, Discord always fires at NORMAL with no level selector.

### JoyCaption Tagger improvements — *all versions*

These are changes within the JoyCaption plugin itself and do not require any changes to the ofscraper package. The plugin system is available in all supported versions (3.12.9, 3.14.3, and 3.14.5).

- **Browse by model** — the image gallery now has a model browser view. Click a model to see all their tagged images in one place
- **Open in external image viewer** — any image in the gallery can now be opened in your system's default image viewer

### Removal / Uninstall Tool — *all versions*

A new standalone script `uninstall_ofscraper.py` is included for cleanly removing ofscraper. It auto-detects your install method (uv / pipx / pip) and offers four options:

1. Just uninstall ofscraper
2. Just remove the GUI patch (reinstalls stock ofscraper from PyPI)
3. Remove ofscraper + all config files (`~/.config/ofscraper/`)
4. Purge everything — uninstalls ofscraper, deletes config, and deletes downloaded content (save path is read from `config.json` before the config is removed)

### Docker — DRM key generation not supported — *all versions*

A note has been added to the DRM Key Creation page clarifying that generating DRM keys inside Docker is not supported. Key generation must be done on a normal host system (Windows or Linux desktop).

### Improved logging — *all versions*

- Plugin activity now produces structured debug/logging output visible in the verbose log
- Console output from DRM key generation is now written to the log file alongside the in-app display

---

## 2026-03-29

### Support for OF-Scraper 3.14.5

A new patch script (`patch_ofscraper_3.14.5_gui.py`) is now available, bringing full GUI support to OF-Scraper 3.14.5 alongside the existing 3.12.9 and 3.14.3 scripts.

### Plugin System *(new — all versions — experimental / work in progress)*

> ⚠️ The plugin system is new and the included plugins are experimental and a work in progress. They may not work 100% reliably in all environments. Use at your own risk and report any issues you encounter.

An extensible plugin system has been added to all supported patch versions (3.12.9, 3.14.3, and 3.14.5). Plugins are loaded automatically from your ofscraper config directory on startup. Two plugins are included but **disabled by default**:

- **JoyCaption Tagger** — automatically captions downloaded images via a JoyCaption Alpha Two node running in ComfyUI and stores the results in a local database. Supports adult/explicit content captioning. Includes an image gallery and Smart Folders support.
- **LLM Assistant** — adds an AI chat panel to the sidebar. Type plain-English commands to control the GUI (set usernames, select areas, start downloads, etc.). Runs fully on CPU using small Qwen2.5 GGUF models.

### Docker

- Docker setup updated with a `GUI_PATCH_VERSION` build arg to control which GUI patch is applied at image build time
- New `GUI_ARGS` environment variable — pass `ofscraper --gui` arguments at container startup to skip the GUI wizard and begin scraping automatically

### Discord Webhook

- A per-run scrape summary is now posted to your Discord webhook after each run completes
- New **Notification Level** selector (3.14.5): choose **LOW** (summary only) or **NORMAL** (all events)

### Scrape by URL / Post ID

- New input on the scrape page to target individual posts directly by URL or Post ID — bypasses model and area selection entirely. Available in all supported versions.

---

## 2026-03-19

### Fixes

#### Check mode — locked content and progress bar

Two bugs in the check mode table and its "Send Downloads" flow have been fixed.

**Locked / paid content now correctly labeled**

Content that is behind a paywall (no download URL available — e.g. a PPV message you have not purchased) previously did not show a distinct state in the check table. It is now labeled **Locked** in the Download Cart column, matching the styled "locked" cell state already present in the table (grey background, click-protected). Previously the internal value was "Not Unlocked", which the table did not recognise, so locked rows appeared visually identical to unlocked rows.

- Affects all check modes: `post_check`, `msg_check`, `paid_check`, `story_check`
- Locked cells cannot be toggled for download — clicking them has no effect
- Use the **Unlocked** filter (`Locked`) to isolate paywalled content

**Progress bar now tracks check mode downloads correctly**

When downloading items via **Send Downloads** in check mode, the footer progress bar was stuck at "Downloads: 0 / 0" the entire time. Downloads completed correctly but there was no visual feedback.

Root cause: OF-Scraper's download engine resets its internal counters (`photo_count`, `video_count`, etc.) via `mainProcessVariableInit()` at the start of each individual item's download. Because check mode fires one download call per item, these counters never accumulated across items. In addition, the progress hook was emitting "0 completed" at the start of each new item, overwriting any progress already shown.

Fix: a dedicated `check_completed` counter is now maintained inside the GUI state. It increments once per completed item (via the `update_overall_task` hook) and is never reset by the per-item counter resets. The hook no longer emits a "0 completed" reset signal in check mode at the start of each item.

Result: the bar now advances correctly — e.g. `3 / 10` after three items finish — and the bytes counter updates as each file is saved.

---

## Previous releases

### Fixes

#### DRM key generation — antivirus / missing adb.exe

Fixed a crash that occurred after the AVD was created when `adb.exe` was missing. The most common cause on Windows is Defender or another antivirus quarantining `adb.exe` immediately after it is downloaded by sdkmanager — the script previously continued silently and only crashed later with a confusing `FileNotFoundError`.

- **Early detection**: after sdkmanager installs components the script now immediately checks that `adb.exe` exists and exits with a clear, actionable message if not — rather than crashing later
- **Smarter diagnostics**: the error message checks whether the `platform-tools` folder itself exists to tell the difference between an antivirus quarantine (folder present, binary absent) and a failed download (folder not created at all), and gives specific instructions for each case
- **sdkmanager output now shown**: output from sdkmanager is printed to the log during installation so any download or extraction failures are visible
- **Graceful fallback**: the `adb kill-server` cleanup step now falls back to a system PATH `adb` if the SDK copy is missing, instead of crashing

### Improvements

#### Configuration page now matches the real config schema

The Configuration page has been audited against the actual `config.json` schema for each supported OF-Scraper version. Fields that were silently ignored by OF-Scraper have been removed, and real options that were missing have been added.

**OF-Scraper 3.14.3** — fields removed (not present in 3.14.3 config schema):
- Advanced: Backend, Allow Code Execution, Append Log, Custom Values
- Performance: Thread Count
- CDM: KeyDB API Key
- Download: Post Download Script
- Overwrites tab (entire tab — not part of 3.14.3 config)

**OF-Scraper 3.14.3** — fields added (were missing from GUI):
- Advanced: Skip Unavailable Content, SSL Verify, Env Files
- Download: Verify All Integrity
- Download: Media type filter checkboxes (Images / Audios / Videos / Text)
- Advanced: Enable Auto After corrected to **Incremental Downloads** (the real key name in 3.14.3)

**OF-Scraper 3.12.9** — all of the above fields *are* real and valid in 3.12.9, so the Configuration page for 3.12.9 is unchanged. The only addition for 3.12.9 is the **Download Filter** media type checkboxes, which are valid in both versions.

#### Model selector — creator avatars
The Select Models page now has a **Show Avatars** toggle. When enabled, each creator's profile picture is displayed alongside their name in the table. Clicking an avatar opens that creator's OnlyFans page directly in your browser.

#### DRM Key Creation page
A built-in tool for generating the DRM decryption keys required to download protected content. Accessible from the sidebar navigation and from the quick link in the startup dependency notice. Once keys are generated, the CDM key paths in your config are updated automatically — no manual config.json editing needed. The startup dependency dialog also includes a **Generate DRM Keys** button when CDM key paths are missing.

#### Verbose Log toggle
A new **Verbose Log** button in the bottom-left navigation bar (below the Theme toggle) enables full debug-level logging. When active, all log levels are shown in the in-app log panel and a dedicated log file is written to your ofscraper config directory (`ofscraper_gui_verbose_<profile>_<timestamp>.log`). The preference is saved across sessions.

#### Open Downloads Folder button
A new button in the scraper toolbar opens the configured `save_location` from your config directly in your file manager — no more manually navigating to find your downloaded content.

#### Progress bar bytes counter no longer goes backward
The total bytes counter in the footer progress bar previously fluctuated up and down mid-scrape. It now only ever increases — values are tracked as a high-water mark so the counter reflects the peak bytes seen for the current session and resets cleanly when a new scrape begins.

#### Support for OF-Scraper 3.14.3
A new patch script (`patch_ofscraper_3.14.3_gui.py`) is available alongside the existing 3.12.9 script. Both patch scripts include all of the same GUI features.

#### Broken installation detection and auto-repair
The patch script detects broken ofscraper installations before patching — for example, a corrupt `~fscraper` artifact left behind by an interrupted pip install, or a missing entry point script. When detected, a `--force-reinstall` is automatically run to repair the installation before the GUI patch is applied.

#### Launch prompt after patching
After a successful patch the script asks if you want to launch the OF-Scraper GUI immediately, using `python -m ofscraper --gui` so it works regardless of whether the `ofscraper` command is in your PATH.
