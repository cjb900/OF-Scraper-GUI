# OF-Scraper GUI — Discord Update Notes

Paste-ready overview (keep ≤ 4000 characters). Full dated changelog: `RELEASE_NOTES.md`.

---

## 2026-11-11

**OF-Scraper GUI 3.14.7 — v420–v422 update**

Re-apply the latest `patch_ofscraper_3.14.7_gui.py` / release asset (tip `20261111_gui_3_14_7_v422`). Docker: copy the new patch, then `docker compose build --no-cache` and recreate the container. Most fixes are community PRs **#29–#39** by **cloakedkeys**. Thank you!

**⚠️ Check after updating**
• **Download speed limit now works.** Older GUI versions saved it in the wrong unit, so "500" can now mean ~1 KB/s. Open **Configuration**, check **Download Speed Limit** and save again.
• **`{my_id}`** (your own account, not the creator) now holds your account ID instead of your display name. Only matters if you put `{my_id}` in a folder or file format; default save folders are unchanged.
• **Check messages** filter now works; the default **Paid / PPV only** hides free messages.
• A failed run now exits with status 1.

**New — Check options**
**Fetch fresh data from OnlyFans** skips the 3-day check cache. **Compare with files on disk** marks items whose file was deleted as not downloaded.

**Fix — Patch**
The patch now ships every changed scraper file. Several fixes never reached patched installs before.

**Fix — Downloads and connections**
Stalled servers time out instead of hanging. Cancels aren't retried. No leaked connections. Rate-limit backoff fixes.

**Fix — Login**
Network or server problems no longer show as "Credentials Invalid". Age verification (code 117) is explained. Logged-out sessions are caught.

**Improvement — Labels**
Labels stop paging once nothing is new: far fewer requests and 429s.

**Improvement — Privacy**
`sess`, `x-bc` and the account IDs are masked in every log line, including the GUI console and Verbose Log.

**Fix — Config and CLI**
Config page shows and keeps the default dynamic rule (`digital`), and Cache Mode offers `api_disabled`. Ignored `config.json` settings now work, including `incremental_downloads: false`. Usage errors no longer show a traceback. `--before`/`--after` take `MM/DD/YYYY` and "3 weeks ago". `--block-ads` and `--env-files` work.

**Fix — GUI**
The table explains rows hidden by filters. Clearing search restores rows. Cancelled runs count their downloads in History.

**Fix — Database and likes**
Multi-creator `db --export`, Merge DBs and safe table rebuilds. Story updates are saved. Failed likes are marked.

---

## 2026-11-01

**OF-Scraper GUI 3.14.7 — September–November 2026 update**

Re-apply the latest `patch_ofscraper_3.14.7_gui.py` / release asset (tip `20261101_gui_3_14_7_v419`). **Live Stream Monitor** is now **1.3.18**; install the new zip from `Available Plugins/` on the **Plugins** page. Docker: copy the new patch + `docker/*`, then `docker compose build --no-cache` and recreate the container.

**⚠️ Check after updating**
• **Text Length > 0** now really shortens post text in filenames, so new filenames change.
• `ofscraper metadata` **`--mark-stray-locked` → `-msl`**; **`--promo-skip` → `-psk`**.
• New **`filename_collision`** option: `"overwrite"` (default, old behavior) or `"media_id"` (keep both files).
• WebEngine remote debugging and hang dumps are now opt-in (env vars).

**New — Two GUI actions**
**Update metadata from files on disk** (like `ofscraper metadata`: Update / Check / Complete, mark unmatched as locked, optional hash check). **Download all purchased content (all creators)**, including expired subs and deleted accounts, with an **Exclude creators** box + **Pick…** list. Both saved in History and re-runnable.

**Fix — Scraping (community PRs #2–#28)**
FFmpeg 8+ works for DRM videos. Messages paging no longer skips messages at chunk edges or at `--before`. Deleted accounts no longer cause tracebacks. `--scrape-paid` respects `--excluded-username` and shows correct per-creator counts. Unresolvable paths and quoted path settings no longer fail downloads. New offline `recover_collisions` tool (preview / apply / undo).

**Fix — Daemon, shutdown and stability**
Daemon stops cleanly on SIGTERM / Ctrl+C; **SIGUSR1** starts the next run now. GUI cancels and quits cleanly on `docker stop`. Fixed two Windows crashes (5 min after start, and on close). **Delete model DB** now works on every scrape in a session, not just the first.

**Improvement — Privacy and security**
Cookie / `x-bc` / `sign` headers can't leak into logs; WebEngine no longer runs with web security off. Privacy mode now also covers the DRM and Merge pages, the purchased-content exclude list, Test Credentials, and creator names/IDs in the Scraper console.

**Improvement — GUI**
Select Models warns about ticked models hidden by search. Easier-to-read colors in both themes, clearer disabled controls, a Filters panel that remembers its width, no window flashing when opening the App Browser.

**Improvement — Installer**
`--force` repairs a broken install from scratch. On Python 3.13+, pipx mode fetches Python 3.12 for ofscraper. OS-correct help when pipx is missing. pipx/uv no longer reinstall GUI packages every run.

**Improvement — Docker**
**`MODE=cli`** runs the daemon without the GUI. Desktop resizes to your browser window, **App Browser login** works, color emoji font. Docs on the config mount and fixing `exec /entrypoint.sh: no such file or directory`.

**Improvement — Live Stream Monitor 1.3.18**
**Headless capture** by default using your Authentication login. Starts recording within seconds and **stops itself when the stream ends**. **Discord @here alerts** on go-live and stream end. Optional auto-start on GUI launch. Fixed captures stuck on "Connecting" (it only closes OnlyFans alerts, never accepts them). Own log file; Privacy mode hides creators.

**Docs** — README split into `docs/` with new Privacy-mode screenshots.

Details: `RELEASE_NOTES.md` / README / in-app Help.

---

## 2026-08-29

**OF-Scraper GUI 3.14.7 — June–August 2026 major update**

Re-apply the latest `patch_ofscraper_3.14.7_gui.py` / release asset (tip `20260829_gui_3_14_7_v365`).

**Improvement — About + GUI text size**
Click sidebar **v3.14.7** (or Help → About) for app version, GUI patch id, OS, FFmpeg/FFprobe, and **Check for updates**. **Text size** (**A−** / **A+** / 12–20 px / **Reset**) scales the whole GUI; saved as `gui_font_size`. Same controls on the Help toolbar.

**Improvement — Auth: System Browser + App Browser login**
Login in System Browser or App Browser with **Cancel Login**, wait timer, and optional hard timeout. Import Cookies on a cancelable background thread; cookie allowlist; better Firefox/Zen UA + CDP; dynamic `auth_uid*` for 2FA. Remote CDM helpers never send session cookies. **Unable to Load Models**: try Dynamic Mode and/or **SSL Verify → false**. Help → **Auth Issues**: built-in capture first; if that fails, DevTools **Network** → filter **`init`** → main timeline → refresh → copy headers. **Wrong user** / sess–auth_id mismatch explained in Test Credentials and Help.

**Improvement — Safer Cancel and scrape confirms**
Dedicated red **Cancel** on the table toolbar for every start path. Cooperative cancel first; force-stop only after a short grace if stuck. Confirm scrape (size/ETA), cart / Send Downloads, and disk-space checks before large jobs. **Privacy / demo mode** for screenshots. New installs default Key Mode to **manual**, with Save + pre-scrape warnings for remote helpers. First-run Welcome before missing FFmpeg/CDM prompts.

**Improvement — Status strip, History, and results table**
Footer **Auth / Config / Key** health chips plus a live elapsed timer while Running/Cancelling. Post-run **Download failures** dialog (filter table / add failures to cart). **History** (last 20 runs) with Details / Re-run. Filter presets, sticky columns, Export CSV, empty-table guidance. Click username to select models; click Post ID / Media ID to open OnlyFans. Resizable scrape console (height saved).

**Improvement — Scripts tab + preferred extensions**
New Configuration **Scripts** tab for all five script paths (`after_action`, `post`, `naming`, `after_download`, `skip_download`). Preferred file extensions for Images / Videos / Audios remap `{ext}` only (no convert/remux). Windows paths display/save with `\`.

**Improvement — Allow duplicates + Messages/Purchased keep-both**
**Allow duplicates** plus optional **Also keep Messages + Purchased copies of the same media** (default off) — keeps other-area reposts while collapsing Messages↔Purchased/Paid to Messages only when keep-both is off. Check mode honors Allow duplicates and advanced options.

**Improvement — Advanced API resilience settings**
Configuration → Advanced: **API Path**, **Manual Dynamic Rules**, **Dynamic Rules URL**, **API Endpoint Overrides**, and **Media Host Suffixes**. Many OnlyFans signing / path / CDN breaks can be handled from config (or env overrides) without a new code patch.

**Improvement — DRM integrity + Docker**
**DRM Duration Match %** (default 98%), stall watchdog, stricter `.part` finalize / resume. Docker noVNC unified on **6699**; GUI auto-restart after exit/crash; logs teed under the config mount.

**Improvement — Crash diagnostics + scrape stability**
Always-on crash breadcrumbs + faulthandler under `~/.config/ofscraper/gui_crash_logs/`. Safer subscription model-list fetch (timeouts, NullLive, plain-dict handoff). Rich handlers stripped during GUI scrapes to avoid hard Qt crashes mid-run.

**Improvement — Plugins page**
Sidebar Plugins: Enable/Disable, **Load now** / **Unload now** without a full restart. Optional plugins: copy from `example_plugins/` → `~/.config/ofscraper/plugins/`.

Details: `RELEASE_NOTES.md` / README / in-app Help.
