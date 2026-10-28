# Open Pull Requests: Review and Implementation Plan

- **Started:** 2026-10-23
- **Base commit:** `aa17b43` (branch `main`)
- **Source:** `open_pull_requests/` (a snapshot of 27 open PRs on `cjb900/OF-Scraper-GUI`, all by `cloakedkeys`)
- **Related:** [`SYSTEM_ANALYSIS.md`](SYSTEM_ANALYSIS.md)

## How each PR is reviewed

1. Read the description and the full diff.
2. Check its claims against the code in this tree.
3. Apply it to a throwaway copy of the tree and run `test/unit`.
4. Where the PR adds a test, check that the test fails without the fix and passes with it.
5. Give a verdict: **Implement**, **Implement with changes**, **Defer** or **Skip**.

**Where git lives:** the git repository root is the parent folder `OF-Scraper-GUI/`, not `OF-Scraper-3.14.7/`. The PR diffs use paths like `OF-Scraper-3.14.7/ofscraper/...`, so apply them **from the parent folder** with `git apply -p1`. Running `git apply` from inside `OF-Scraper-3.14.7/` silently skips every file.

**Important for every PR that touches a file the GUI patch ships:** `patch_ofscraper_3.14.7_gui.py` overwrites 152 files (132 before `v368`, 133 before `v369`, 134 before `v370`, 135 before `v371`, 137 before `v372`, 138 before `v375`, 140 before `v376`, 141 before `v378`, 144 before `v379`, 145 before `v381`, 146 before `v384`, 147 before `v386`, 148 before `v387`, 150 before `v388`) in the installed package. A fix to one of those files only reaches users after the patch is rebuilt. There are **two identical copies** of the patch: `OF-Scraper-GUI/patch_ofscraper_3.14.7_gui.py` and `OF-Scraper-GUI/OF-Scraper-3.14.7/patch_ofscraper_3.14.7_gui.py`. Keep them in sync.

### How the patch is rebuilt

Use `OF-Scraper-3.14.7/rebuild_patch_zip.py` (the original tool). It keeps the existing `FILES` list and installer code, packs the 132 source files into `ZIP_B64`, and with `--patch-id` also updates `PATCH_ID` in both the patch script and `ofscraper/gui/patch_version.py` (the About dialog shows it).

```bash
cd OF-Scraper-3.14.7
python3 rebuild_patch_zip.py --patch-id <YYYYMMDD>_gui_3_14_7_v<next number> --sync-root
```

`--sync-root` also writes the repo-root copy (`../patch_ofscraper_3.14.7_gui.py`). Then check: unpack the payload and compare all 132 files to the tree, and test-install it into a scratch copy of the package.

**Tool changes (2026-10-23):**
- `FILE_COUNT` is now rewritten from the `FILES` list every time. It used to be left alone, which is why it said 87.
- New `--sync-root` flag updates the repo-root copy.
- Fixed: rebuilding with no source changes used to fail with "ZIP_B64 replacement had no effect", because an identical payload looked like a missing pattern. It now counts matches instead.

**Line endings:** the tool packs files byte-for-byte. The old CRLF payload means `v365` was built from a Windows checkout. Building on Linux gives LF. Python doesn't care either way.

| Patch ID | Date | Contents |
|---|---|---|
| `20260829_gui_3_14_7_v365` | 2026-08-29 | Original release |
| `20261023_gui_3_14_7_v366` | 2026-10-23 | PR #2, plus the newer `GUI_HELP.md` that was already in the tree. `FILE_COUNT` corrected from 87 to 132. Files are now stored with LF line endings, as in the tree, instead of CRLF. |
| `20261023_gui_3_14_7_v367` | 2026-10-23 | PR #3 (ffmpeg 8+, `strip_pssh`), with a broader `except` around `strip_pssh` and an updated FFmpeg recommendation in `GUI_HELP.md` |
| `20261023_gui_3_14_7_v368` | 2026-10-23 | PR #4 (filename hidden with plain text, filename step moved first, empty-name guard). **`commands/scraper/actions/utils/log.py` added to `FILES`** (132 → 133). |
| `20261023_gui_3_14_7_v369` | 2026-10-23 | PR #5 (one asyncio.Lock per event loop, finished loops dropped). **`managers/sessionmanager/sessionmanager.py` added to `FILES`** (133 → 134). This also ships 2 earlier unshipped lines that ignore server-set cookies. |
| `20261023_gui_3_14_7_v370` | 2026-10-23 | PR #6 (unencodable characters print as `?` instead of crashing). **`utils/console.py` added to `FILES`** (134 → 135). |
| `20261024_gui_3_14_7_v371` | 2026-10-24 | PR #7 (Text Length / Text Type take effect, correct word count, no trailing separator) + Text Length tooltip and help fix. **`classes/of/base.py` and `utils/args/parse/arguments/file.py` added to `FILES`** (135 → 137). ⚠️ New filenames change for users with Text Length > 0. |
| `20261024_gui_3_14_7_v372` | 2026-10-24 | PR #8 (an unresolvable path no longer fails finished downloads, folder-dating walk guarded). **`commands/scraper/actions/utils/paths.py` added to `FILES`** (137 → 138). |
| `20261024_gui_3_14_7_v373` | 2026-10-24 | PR #9 (quotes stripped from the 5 path settings, empty ffmpeg falls back to `OFSC_FFMPEG_DEFAULT` at runtime only). All 3 files were already in `FILES` (still 138). |
| `20261024_gui_3_14_7_v374` | 2026-10-24 | PR #9 follow-up: the GUI's own checks (Key chip, Config chip, startup missing-files notice) also strip quotes, so a quoted path no longer shows a false warning. `strip_path_quotes` moved to `utils/config/path_norm.py`. All files already in `FILES` (still 138). |
| `20261024_gui_3_14_7_v375` | 2026-10-24 | PR #10 (terminal model selector: range select and filter menu visible, `nostdout()` always restores stdout) + devnull opened as UTF-8. **`prompts/utils/prompt_helpers.py` and `utils/context/stdout.py` added to `FILES`** (138 → 140). |
| `20261024_gui_3_14_7_v376` | 2026-10-24 | PR #11 ("Yes Update Selection" resets usernames to `[]`, guard in `_select_models_scraper`). **`utils/args/mutators/user.py` added to `FILES`** (140 → 141). |
| `20261024_gui_3_14_7_v377` | 2026-10-24 | PR #12 (Purchases scan early stops logged as warnings) with the security fix: exceptions logged as `type: str`, never `repr`, so request headers (cookie, `x-bc`, `sign`) can't leak. `data/api/paid.py` was already in `FILES` (still 141). |
| `20261024_gui_3_14_7_v378` | 2026-10-24 | PR #13 (`--scrape-paid` honours `--excluded-username`). **`data/posts/post.py`, `filters/models/other.py`, `utils/args/parse/arguments/user_select.py` added to `FILES`** (141 → 144). |
| `20261024_gui_3_14_7_v379` | 2026-10-24 | PR #14 (metadata hash: no `mediatype=` argument to `get_hash`). **`commands/metadata/manager.py` added to `FILES`** (144 → 145). |
| `20261024_gui_3_14_7_v380` | 2026-10-24 | PR #15 (deleted accounts: Profile area skipped without a traceback). `data/posts/post.py` was already in `FILES` (still 145). |
| `20261024_gui_3_14_7_v381` | 2026-10-24 | PR #16 (deleted-account placeholders kept out of the normal scrape; `Model.avatar`/`header` return `None` when missing). **`classes/of/models.py` added to `FILES`** (145 → 146). |
| `20261024_gui_3_14_7_v382` | 2026-10-24 | PR #17 (messages: each chunk keeps its final page, chunks continue from the previous tail) + strict `> before` anchor so a message exactly at `--before` isn't skipped or marked deleted. `data/api/messages.py` was already in `FILES` (still 146). |
| `20261024_gui_3_14_7_v383` | 2026-10-24 | PR #19 (filename collisions), merged by hand with PRs #8/#9, with **default `filename_collision: "overwrite"`** (old behavior); `"media_id"` is opt-in. All changed files were already in `FILES` (still 146). |
| `20261024_gui_3_14_7_v384` | 2026-10-24 | PR #22 (offline `recover_collisions` tool, preview / apply / undo) + GUI help: new Troubleshooting section and a `filename_collision` entry. **`commands/recover_collisions.py` added to `FILES`** (146 → 147). |
| `20261024_gui_3_14_7_v385` | 2026-10-24 | GUI help only: the collision-recovery section now says it can only bring back media the site still offers (learned from the live run). Still 147 files. |
| `20261024_gui_3_14_7_v386` | 2026-10-24 | PR #25 (GUI cancels the scrape and quits cleanly on SIGTERM) + **`ensure_gui_host()` fix** (missing `global`, from the system analysis). **`gui/utils/shutdown.py` added to `FILES`** (147 → 148). |
| `20261024_gui_3_14_7_v387` | 2026-10-24 | PR #21 (contains #18 + #20): CLI daemon stops cleanly on SIGTERM/Ctrl+C, SIGUSR1 starts the next run. GUI help: Docker CLI mode notes. **`commands/scraper/utils/schedule.py` and `utils/context/exit.py` added to `FILES`** (148 → 150). Also new: Docker `MODE=cli` (Docker files, not in the patch). |
| `20261024_gui_3_14_7_v388` | 2026-10-24 | PR #28 (newer Pythons for source installs): escape-sequence fixes in `log.py`, `media.py` uses the in-repo `async_cached_property`, `check.py` uses `system.new_event_loop()`, `_httpx_funct` uses `build_request`/`send`. **`utils/async_cached_property.py` and `utils/system/system.py` added to `FILES`** (150 → 152). Also (not in the patch): `pyproject.toml`/`uv.lock` allow Python up to 3.15, CI tests 3.11–3.14. |
| `20261025_gui_3_14_7_v389` | 2026-10-25 | Installer fix only (same 152 files): on Python 3.13+ with no `python3.11`/`python3.12` on the PATH, option 2 (pipx) now runs `pipx install --python 3.12 --fetch-python=missing` (`--fetch-missing-python` on older pipx), so pipx downloads a standalone Python 3.12 instead of failing to build `lxml 5.1.1`. Warnings show the real Python version instead of "3.13". Found by the maintainer on Python 3.14.7 + pipx 1.15; the full flow was tested in an isolated home: install, GUI deps, patch, GUI start. **Confirmed by the maintainer on their own system (`ofscraper --gui` runs).** |
| `20261025_gui_3_14_7_v390` | 2026-10-25 | Follow-ups from the manual test run (same 152 files): a GUI stopped by SIGTERM / `docker stop` is now saved in scrape history as `cancelled`, not `ok`; `gui_crash_logs/faulthandler.log` is moved to `faulthandler.log.1` once it passes 5 MB (checked at startup and every 5 min); the CLI daemon writes `Stop requested: shutting down the daemon` to its log on Ctrl+C / SIGTERM. |
| `20261025_gui_3_14_7_v391` | 2026-10-25 | New GUI action **Update metadata from files on disk (no downloads)**, the same job as `ofscraper metadata`: Update / Check / Complete mode (Complete asks first), mark unmatched as locked, per-run hash checking. One-shot run, the table reloads afterwards, cancel works between models, saved in history and Re-run. A later download run gets its normal args back. Same 152 files. |
| `20261025_gui_3_14_7_v392` | 2026-10-25 | New GUI action **Download all purchased content (all creators)**, the same job as `--scrape-paid --excluded-username …`. It has an Exclude box with a Pick… list, plus media types, and skips the Areas/Models pages. Leftover Areas-page options (rescrape, delete DB/files, daemon, dates) are not used. The exclude list doesn't carry into later runs. `process_all_paid`'s username lookup moved into `resolve_paid_username()`. Paid media ids are reset each run. Same 152 files. |
| `20261025_gui_3_14_7_v393` | 2026-10-25 | CLI fix: `ofscraper metadata` had `-ms` for both `--mark-stray-locked` and `--mass-skip`, and mass-skip won, so `-ms` never marked strays. `--mark-stray-locked` is now short `-msl`; `-ms` stays `--mass-skip` like in every other command. Adds `utils/args/parse/group_bundles/metadata.py` to the payload (153 files). |
| `20261025_gui_3_14_7_v394` | 2026-10-25 | CLI fix: in the main command `-ps` was the short flag of both `--promo-skip` and `--post-script`; post-script won, so `-ps` alone errored. `--promo-skip` is now short `-psk`; `-ps` stays `--post-script`. Adds `utils/args/parse/arguments/user_list.py` to the payload (154 files). |
| `20261025_gui_3_14_7_v395` | 2026-10-25 | Crash fix: the GUI died with a Windows access violation 5 minutes after start. The periodic all-thread hang dump (`dump_traceback_later(300, repeat=True)`) reads running threads' stacks, and v390's trim thread woke on the same 300 s, so a thread was always busy at dump time. Hang dumps are now opt-in (`OFSCRAPER_GUI_HANG_DUMP_SECONDS`) and the trim thread is gone (trim at startup stays). Pick… with no known names now offers to load the subscription list and reopens. Same 154 files. |
| `20261025_gui_3_14_7_v396` | 2026-10-25 | Summary fix for paid scrapes (all-purchased and "Scrape entire paid page"): every creator showed the last creator's counts (e.g. "1 video" ×17) and the global total was that one creator. Per-creator stats are now recorded after each paid creator and summed. Also, a normal model with no media recorded the previous model's counters; it now records zeros. Same 154 files. |
| `20261025_gui_3_14_7_v397` | 2026-10-25 | All-purchased / "Scrape entire paid page": the table showed only the last creator while scraping, because each creator's rows replaced the table. The first creator now replaces it and the rest are added. Each scrape log now names the patch (`[GUI] patch …`). Same 154 files. |
| `20261025_gui_3_14_7_v398` | 2026-10-25 | WebEngine remote debugging is now opt-in (`OFSCRAPER_GUI_WEBENGINE_DEBUG=1`), and `--disable-web-security` / `--allow-running-insecure-content` / `--remote-allow-origins=*` are gone; two download log lines now hide the media link; the per-creator size uses the same units as the global totals; `model_selector_dialog.py` imports `QWidget`. Adds `managers/stats.py` (155 files). |
| `20261026_gui_3_14_7_v399` | 2026-10-26 | On Windows the GUI sets `QT_WIDGETS_RHI=1` before `QApplication`, so opening the App Browser login no longer makes the whole GUI flash. |
| `20261026_gui_3_14_7_v400` | 2026-10-26 | `QT_WIDGETS_RHI=1` is now also set on Linux (not in Docker), which stops the same login-browser flash there. |
| `20261026_gui_3_14_7_v401` | 2026-10-26 | Manual key mode with missing CDM files now fails once with a plain message, before downloading and without retries; Download all purchased warns when a creator can't be prepared; CI installs the `gui` extra so the GUI tests run. Adds `download/utils/retries.py` (156 files). |
| `20261028_gui_3_14_7_v402` | 2026-10-28 | After a manual-key-mode test run on Windows (`drm-cdm-blank`), `run.download` no longer writes a full traceback per skipped DRM video for `no_retry` errors; the one ERROR line stays. |

## Status

| # | Title | Verdict | Status |
|---|---|---|---|
| 2 | fix(drm): request purchased wall posts' keys from the post endpoint | **Implement** | ✅ Implemented, patch rebuilt (`v366`) |
| 3 | fix(ffmpeg): accept ffmpeg 8 and newer for DRM | **Implement with small changes** | ✅ Implemented with both changes, patch rebuilt (`v367`), live-tested with ffmpeg 8.1.3 on Linux and Windows |
| 4 | fix(download): don't treat the filename as a regex when hiding it in logs | **Implement with small changes** | ✅ Implemented with both changes + empty-name guard, patch rebuilt (`v368`) |
| 5 | fix(session): use one asyncio.Lock per event loop in SessionSleep | **Implement with small changes** | ✅ Implemented with both changes, patch rebuilt (`v369`) |
| 6 | fix(console): replace unencodable characters instead of crashing | **Implement (ship in patch)** | ✅ Implemented as is, patch rebuilt (`v370`) |
| 7 | fix(naming): make textlength and text type settings take effect | **Implement with small changes** | ✅ Implemented with both changes + tooltip fix, patch rebuilt (`v371`) |
| 8 | fix(download): don't fail finished downloads when a path can't be resolved | **Implement (ship in patch)** | ✅ Implemented as is, patch rebuilt (`v372`) |
| 9 | fix(config): accept quoted CDM/ffmpeg paths and empty ffmpeg setting | **Implement with a tiny change** | ✅ Implemented with the test fix (`v373`), plus GUI follow-up (`v374`). Both live-tested on Windows |
| 10 | fix(prompts): keep model selector prompts visible and stdout intact | **Implement (ship in patch)** | ✅ Implemented + devnull UTF-8, patch rebuilt (`v375`) |
| 11 | fix(models): don't drop to the main menu after 'Yes Update Selection' | **Implement (ship in patch)** | ✅ Implemented as is, patch rebuilt (`v376`), live-tested on Windows |
| 12 | fix(paid): warn when a Purchases scan stops early | **Implement with a security fix** | ✅ Implemented with the fix, patch rebuilt (`v377`) |
| 13 | feat(paid): skip --excluded-username models during --scrape-paid | **Implement (ship in patch)** | ✅ Implemented as is, patch rebuilt (`v378`) |
| 14 | fix(metadata): stop passing mediatype to get_hash | **Implement (ship in patch)** | ✅ Implemented as is, patch rebuilt (`v379`) |
| 15 | fix(profile): skip the profile area for deleted accounts | **Implement** | ✅ Implemented as is, patch rebuilt (`v380`) |
| 16 | fix(models): keep deleted-account placeholders out of the normal scrape | **Implement (ship in patch)** | ✅ Implemented as is, patch rebuilt (`v381`) |
| 17 | fix(messages): keep pages that end a scan and stop re-paginating chunk 0 | **Implement with a small fix** | ✅ Implemented with the anchor fix, patch rebuilt (`v382`), live full-scan checked |
| 18 | fix(daemon): stop on SIGTERM instead of waiting for SIGKILL | **Implement with a fix** | ✅ Implemented through PR #21 (`v387`), with the Docker CLI mode |
| 19 | fix(download): prevent filename collisions at the final move | **Implement, old behavior by default** | ✅ Implemented with `overwrite` default (opt-in `media_id`), patch rebuilt (`v383`) |
| 20 | fix(daemon): only mark a job done after taking it from the queue | **Implement (instead of #18)** | ✅ Implemented through PR #21 (`v387`) |
| 21 | feat(daemon): trigger an idle scraping pass with SIGUSR1 | **Implement (includes #18 + #20)** | ✅ Implemented (`v387`) + Docker CLI mode |
| 22 | feat(recovery): mark old filename collisions for re-download | **Implement + add docs** | ✅ Implemented with docs, patch rebuilt (`v384`), live-run on real data |
| 23 | fix(docker): copy the GUI patches from the repo root | **Implement** | ✅ Implemented as is (Docker files only, no patch rebuild) |
| 24 | fix(docker): pass docker stop on to the GUI instead of waiting for SIGKILL | **Implement with a small fix** | ✅ Implemented with the startup-stop fix (Docker files only, no patch rebuild) |
| 25 | fix(gui): cancel the scrape and quit cleanly on SIGTERM | **Implement (ship in patch)** | ✅ Implemented as is + `ensure_gui_host` fix, patch rebuilt (`v386`) |
| 26 | test: repair the legacy suite and retire tests for removed code | **Implement with a small fix** | ✅ Implemented with isolated test HOME + `.pyc` cleanup (no patch rebuild) |
| 27 | ci: run the tests in the OF-Scraper-3.14.7 project with uv | **Implement (workflow only; rest is #26)** | ✅ Implemented with `--locked` (workflow only, no patch rebuild) |
| 28 | chore: support Python 3.15 for source installs | **Implement with re-lock + 2 patch files** | ✅ Implemented with re-lock, 2 patch files, CI 3.13/3.14 and test leak fixes; patch rebuilt (`v388`) |

---

## PR #2: fix(drm): request purchased wall posts' keys from the post endpoint

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/2
- **Size:** 2 files, +46 / -1
- **Upstream issue:** datawhores/OF-Scraper#636
- **Verdict:** ✅ **Implement**

### The problem, in plain words

To play DRM video, the tool asks OnlyFans for a decryption key. The address it asks depends on where the video came from: a wall post uses `/drm/post/...`, a message uses `/drm/message/...`.

Everything from the **Purchased** tab is labelled `"Paid"` (`ofscraper/data/posts/post.py:104` and `:361`). The current code in `ofscraper/classes/of/media.py:491-501` sends anything that isn't a timeline type to the **message** address. So a purchased **wall post** asks the wrong address, and OnlyFans answers `403 "User have no permissions"`.

### What the PR changes

In `Media.license`:
- Timeline types still go to `post`.
- `messages` / `message` still go to `message`.
- **New:** anything else (like `Paid`) checks the post's raw `responseType` from the API. `"post"` goes to `post`; anything else goes to `message`, which is the old behaviour.

It also adds `test/unit/test_drm_license_url.py` with 7 cases.

### What I checked

| Check | Result |
|---|---|
| The code matches what the PR describes | ✅ `media.py:495-500` is exactly the code being replaced |
| `self.post.post.get("responseType")` is valid | ✅ `Post.post` returns the raw API dict (`posts.py:157-158`) |
| Applies cleanly to this tree | ✅ `git apply -p2 --check` passes (one harmless trailing blank line) |
| New test **without** the fix | ❌ 1 failed (`Paid` + `post`), 6 passed, as expected |
| New test **with** the fix | ✅ all pass |
| Full `test/unit` with the fix | ✅ 46 passed, 4 skipped (Windows-only) |

### Why it's worth implementing

- It fixes a real failure users hit: purchased wall-post videos can't be downloaded at all.
- It's small (5 changed lines in one function), and every case that worked before still goes to the same address. Only the `Paid` + raw `post` case changes.
- It comes with a test that proves the fix.
- The GUI patch ships `classes/of/media.py`, so as the author points out, applying the current patch **puts this bug back**, even for users who already fixed it by hand.

### Small concerns (not blockers)

- The new test sets `sys.argv` and imports `ofscraper.main.open.load` at the top of the file. That affects every test that runs after it. It works today, but it would be cleaner as a fixture in `test/unit/conftest.py`.
- Other non-timeline types (Stories, Highlights, Profile) now also check the raw `responseType`. In practice they don't send `"post"`, so their behaviour doesn't change.
- Shipping the fix to users needs a patch rebuild.

### Implementation (done 2026-10-23)

- Applied from the git root with `git apply -p1 --whitespace=fix` (this dropped the trailing blank line in the new test).
- Changed: `ofscraper/classes/of/media.py`. Added: `test/unit/test_drm_license_url.py`.
- `test/unit`: **46 passed, 4 skipped** (was 39 passed before the new test).
- Patch rebuilt as `20261023_gui_3_14_7_v366`, both copies:
  - All 132 payload files match the tree byte-for-byte.
  - A test install into a scratch copy of the package wrote the fixed `media.py`, and the backup held the old one.
- Not committed yet.

---

## PR #3: fix(ffmpeg): accept ffmpeg 8 and newer for DRM

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/3
- **Size:** 4 files, +180 / -3
- **Upstream (related):** datawhores/OF-Scraper#614, datawhores/OF-Scraper#618
- **Verdict:** ✅ **Implement with small changes** (see below)

### The problem, in plain words

To decrypt DRM videos, OF-Scraper runs ffmpeg. `ofscraper/utils/system/ffmpeg.py:47` refuses any ffmpeg version 8 or newer. Many users now have ffmpeg 8 or 9, so DRM downloads fail or the tool hunts for an older copy.

### What the PR changes

1. **Version check** (`utils/system/ffmpeg.py`): accept 6 or newer, instead of only 6 and 7.
2. **New `strip_pssh()`** (`keyhelpers.py`): ffmpeg 8+ copies the `pssh` box (a small block of DRM setup data) into the decrypted file. ffmpeg 7 didn't. The video is the same either way, but some players may treat a file that still has `pssh` as protected. `strip_pssh()` renames each `pssh` box to `free`, an "ignore me" box of the same size, so nothing else in the file moves.
3. Two new test files: version parsing, and an encrypt → decrypt → compare test.

### What I checked

| Check | Result |
|---|---|
| Applies cleanly to this tree (with PR #2 already in) | ✅ |
| Full `test/unit` with the PR | ✅ 56 passed, 4 skipped |
| The 10 new tests | ✅ all pass (with ffmpeg 7.1.1 and with ffmpeg 8.1.3) |
| No other place enforces "below 8" | ✅ only `utils/system/ffmpeg.py`. The About dialog, ffprobe and the merge step all go through `get_ffmpeg()` |
| Merged audio+video files stay clean | ✅ each stream goes through `un_encrypt` (which strips) before the `-c copy` merge in `alt_download.py:375` |

**Checking the `pssh` claim directly.** ffmpeg's own encryptor doesn't write `pssh`, so I added a Widevine `pssh` box to an encrypted test clip, like real OnlyFans files have, and decrypted it the way `un_encrypt` does:

| ffmpeg | `pssh` in decrypted file | After `strip_pssh` | File size | Frames match original |
|---|---|---|---|---|
| 7.1.1 (system) | 0 | 0 (nothing to do) | unchanged | ✅ |
| 8.1.3 (BtbN static build) | **1** | 0 | unchanged | ✅ |

This confirms the PR's claim and shows the fix works.

### Why it's worth implementing

- ffmpeg 7 is getting harder to find. Linux distros and Windows builds are moving to 8 and 9. Without this, those users can't decrypt DRM media.
- The `pssh` cleanup is careful: it renames 4 bytes per box, never moves data, only looks in the top level and inside `moov`/`moof`, and does nothing on ffmpeg 6/7.
- It adds no new dependencies, unlike upstream's #618, which adds `ffmpeg-python` and leaves `pssh` in place.

### Small changes I'd make

1. **Catch more errors around `strip_pssh`.** The call in `un_encrypt` catches only `OSError`. A truncated file with a 64-bit box size could raise `struct.error`, which would fail a download that had already decrypted fine. Catch `Exception` there, since the cleanup is optional.
2. **Update the docs.** `gui/help/GUI_HELP.md:745` says "Recommended: FFmpeg 7.1.1 or lower". That's now wrong, and "lower" was never right because below 6 is rejected. Change it to "FFmpeg 6 or newer (7.1.1 is a known-good choice)". The missing-deps dialog (`missing_deps_dialog.py:31,133`) can keep linking 7.1.1, since that still works.

### Concerns (not blockers)

- The end-to-end test can't catch a `pssh` regression, because ffmpeg's encryptor never adds one. It does still check that decryption gives the right frames. It could be improved by adding a `pssh` box the way I did above.
- Same `sys.argv` / import-at-top test pattern as PR #2.
- A side note on the version check: builds that print `n8.1.3` (BtbN) or `N-118000` (git builds) were never blocked, because the version pattern can't read them. Only builds like Gyan's `8.1.2-essentials_build` were blocked.

### Ships in the patch?

Yes. `commands/scraper/actions/download/utils/keyhelpers.py` and `utils/system/ffmpeg.py` are both in the patch's `FILES` list, so the patch needs rebuilding.

### Implementation (done 2026-10-23)

- Applied from the git root with `git apply -p1`.
- Changed: `ofscraper/commands/scraper/actions/download/utils/keyhelpers.py`, `ofscraper/utils/system/ffmpeg.py`. Added: `test/unit/test_drm_decrypt_output.py`, `test/unit/test_ffmpeg_version.py`.
- Small change 1: `keyhelpers.py:139` now catches `Exception` (was `OSError`), with a comment saying why.
- Small change 2: `gui/help/GUI_HELP.md:745` now says "FFmpeg 6 or newer (7.1.1 is a known-good choice)".
- `test/unit`: **56 passed, 4 skipped** with ffmpeg 7.1.1. The decrypt tests also pass with ffmpeg 8.1.3.
- Patch rebuilt as `20261023_gui_3_14_7_v367` with `rebuild_patch_zip.py --sync-root`:
  - All 132 payload files match the tree.
  - Test-installed into a clean copy of the original package: PR #2 and PR #3 code, the docs change and the new patch ID all landed.
  - An ffmpeg 8.1.3 decrypt run through the **installed** code removed the `pssh` box, with the file size unchanged and frames matching.
- Not committed yet.

### Live tests by the maintainer (2026-10-23)

#### Linux

- **Result:** ✅ works, no issues found.
- **Setup:** OF-Scraper 3.14.7 with GUI patch `20261023_gui_3_14_7_v367`, installed with uv. `binary_options.ffmpeg` in `config.json` pointed at a BtbN static build, `ffmpeg version n8.1.3-24-g92611900bb-20261023`, with `ffprobe` from the same build in the same folder.
- **Tested by:** cjb900, in the real app against real content.

#### Windows

- **Result:** ✅ works, no issues found.
- **Setup:** OF-Scraper 3.14.7 with GUI patch `v367`. `binary_options.ffmpeg` pointed at the BtbN static Windows build `ffmpeg-n8.1-latest-win64-gpl-8.1.zip` (ffmpeg 8.1.3), with `ffprobe.exe` from the same `bin\` folder.
  - Download: https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n8.1-latest-win64-gpl-8.1.zip. This is a rolling link and may serve a newer 8.1.x later.
- **Tested by:** cjb900, in the real app against real content.

#### Summary

- PR #3 works in practice with ffmpeg above 7.1.1 on both Linux and Windows.
- **Not yet tested:** a Gyan build (for example `ffmpeg-8.1.2-essentials_build`, https://github.com/GyanD/codexffmpeg/releases/download/8.1.2/ffmpeg-8.1.2-essentials_build.zip). Gyan's `8.1.2-essentials_build` version format is the one the **old** check rejected. BtbN's `n8.1.3` format was never blocked. A Gyan test would confirm the version-check part of the fix live. The unit test `test_ffmpeg_version.py` already covers that format.

---

## PR #4: fix(download): don't treat the filename as a regex when hiding it in logs

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/4
- **Size:** 2 files, +34 / -1
- **Verdict:** ✅ **Implement with small changes** (see below)

### The problem, in plain words

Before each download, the tool writes the download URL to the debug log with the filename hidden (`get_url_log`, `ofscraper/commands/scraper/actions/utils/log.py:42-46`). To hide it, the code uses the filename as a **search pattern** (`re.sub(ele.filename, ...)`). In a regex, characters like `(`, `[` and `+` have special meanings.

`Media.filename` (`classes/of/media.py:408-410`) strips punctuation from both ends of the name. So a file uploaded as `Untitled design (7).png` gets the filename `Untitled design (7`, which has an unmatched `(`. That's an invalid regex, so `re.sub` raises `re.error`. The call sits at the top of the download in `main_download.py:61` and `alt_download.py:82`, so **the download fails before it starts**.

### What the PR changes

It replaces `re.sub(ele.filename, "{hidden}", url)` with a plain `url.replace(ele.filename, "{hidden}")`, and adds `test/unit/test_url_log.py` with 2 tests.

### What I checked

| Check | Result |
|---|---|
| Code matches what the PR describes | ✅ `log.py:45` |
| Applies cleanly (on top of PRs #2 and #3) | ✅ |
| Full `test/unit` with the PR | ✅ 58 passed, 4 skipped |
| New test **without** the fix | ❌ 1 failed, 1 passed, as the PR says |
| Is `log.py` in the GUI patch? | ❌ **No.** It's not in `FILES`, so this fix wouldn't reach patched users |
| Is this folder's `log.py` the same as stock 3.14.7? | ✅ identical to the installed stock copy, so shipping it adds only this fix |

**Old vs new log output:**

| Filename | Before the PR | After the PR |
|---|---|---|
| `Untitled design (7` | 💥 `re.error: missing )`, so the download fails | `…/123/{hidden} design (7).png` (no crash, but part of the name shows) |
| `IMG 2024 (1` | 💥 `re.error`, so the download fails | `…/abc/{hidden}).jpg` |
| `my[photo]` | name not hidden: `…/my[photo].jpg` | `…/abc/{hidden}.jpg` |
| `a+b` | wrong parts hidden: `…/a/{hidden}/{hidden}c/a+b.jpg` | `…/abc/{hidden}.jpg` |
| `1000x1800_cb46` | `…/abc/{hidden}.jpeg` | same |

### Why it's worth implementing

- It fixes a real bug where some downloads fail every time. Any file whose name contains `(`, `[` or similar can trigger it, and people often upload files with names like "design (7)".
- It's a one-line change with a test that proves it.
- It also fixes filenames with `+`, `.` or `[]`, which were being matched wrongly and not hidden.

### Small changes I'd make

1. **Hide the filename first, then run the generic rule.** `get_url_log` first replaces any `/` followed by 6+ word characters with `/{hidden}`. For `Untitled design (7).png` that already turns `/Untitled` into `/{hidden}`, so the full filename no longer matches and ` design (7).png` shows in the log. Swapping the two steps gives `…/123/{hidden}).png`, with only the stripped `)` left. It's a small privacy improvement for logs people share in bug reports. The PR's tests still pass.
2. **Add `commands/scraper/actions/utils/log.py` to the patch's `FILES` list** (132 → 133 files), so the fix actually reaches GUI-patch users. `rebuild_patch_zip.py` now updates `FILE_COUNT` by itself, and the patch's backup/restore covers new entries automatically.

### Not in scope

Other places that build a regex from text (`classes/table/fields/textsearch.py:45`, `gui/widgets/sidebar.py:127-131`, `filters/media/filters.py:337,364`) take a **search pattern the user typed**, so treating it as a regex is intended. `utils/paths/paths.py:81,113,129` (`re.sub(ext, "", path.name)`) treats a file extension as a pattern, and it isn't anchored to the end of the name. Worth a look later, but it's not this PR.

### Implementation (done 2026-10-23)

- Applied from the git root with `git apply -p1`.
- **Small change 1 (order):** `get_url_log` now hides the filename **before** the generic `/word` rule (`log.py:41-48`).
- **Extra guard:** the filename step only runs when `ele.filename` isn't empty. `str.replace("")` would put `{hidden}` between every character, and the old regex code had the same problem.
- **Small change 2 (shipping):** `commands/scraper/actions/utils/log.py` added to the patch's `FILES` list, right after `keyhelpers.py`. `FILE_COUNT` is now 133.
- **Tests:** 2 extra tests in `test/unit/test_url_log.py`:
  - `test_no_part_of_the_filename_is_left_behind`
  - `test_empty_filename_leaves_url_readable`
  - Both **fail** on the PR as submitted and pass with the changes above.
- `test/unit`: **60 passed, 4 skipped**.
- Patch rebuilt as `20261023_gui_3_14_7_v368` with `rebuild_patch_zip.py --sync-root`:
  - All 133 payload files match the tree.
  - Test-installed into a clean copy of stock 3.14.7: the new `log.py` landed and the backup held the stock one. PR #2/#3 code and the `v368` ID were present.
  - `--restore` put the stock `log.py` back, so undoing works for the newly added file.
- Not committed yet.

---

## PR #5: fix(session): use one asyncio.Lock per event loop in SessionSleep

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/5
- **Upstream issue:** datawhores/OF-Scraper#616
- **Size:** 2 files, +69 / -1
- **Verdict:** ✅ **Implement with small changes** (see below)

### The problem, in plain words

`SessionSleep` is the "slow down" helper that waits between API calls and backs off after a 429 (too many requests). It made **one** `asyncio.Lock` when it was created (`sessionmanager.py:76`).

An `asyncio.Lock` belongs to the first event loop that has to *wait* on it. After that, waiting on it from any other loop raises `RuntimeError: ... is bound to a different event loop`.

That matters here because:

- The sleepers are **shared app-wide singletons** (`managers/sessionmanager/sleepers.py`), used by every session.
- The app runs async code in more than one event loop (`utils/context/run_async.py` `run` / `run_forever`, worker threads, and each GUI scrape).

So the first time two requests in a *second* loop both have to wait, for example while backing off after a 429, the request fails with that error.

### What the PR changes

- Replaces the single lock with a `weakref.WeakKeyDictionary` of locks keyed by the running loop, behind a `_alock` property.
- A separate `threading.Lock` guards that dictionary. It doesn't reuse `self._lock`, because `do_sleep` holds that one during `time.sleep`.
- Adds `test/unit/test_session_sleep.py` (2 tests: contend in one loop, then contend again in a new loop).

### What I checked

| Check | Result |
|---|---|
| The claim | ✅ True. Reproduced: `RuntimeError: <asyncio.locks.Lock ...> is bound to a different event loop` |
| Applies cleanly | ✅ |
| New tests **without** the fix | ❌ 2 failed, as the PR says |
| New tests with the fix | ✅ 2 passed |
| Works with `uvloop` (used on Linux, `utils/system/system.py:18-23`) | ✅ `uvloop` 0.21 loops support weak references |
| Stress test: 8 threads at once, mixing `uvloop` and default loops, 5 loops each, shared sleeper | ✅ no errors |
| Memory: are finished loops released? | ❌ **No.** All 40 loops from the stress test stayed in the dictionary (see change 1) |
| Is `sessionmanager.py` in the GUI patch? | ❌ **No.** It's not in `FILES`, so the fix wouldn't reach patched users (see change 2) |

### Why it's worth implementing

- It fixes a real crash on exactly the path that matters most: backing off after being rate-limited.
- The fix is small and keeps the same locking rules within each loop.

### Small changes I'd make

1. **Use a plain dict and drop closed loops, not a `WeakKeyDictionary`.** Once an `asyncio.Lock` has had to wait, it stores a reference to its loop (`lock._loop`). The dictionary holds the lock, and the lock holds the loop, so the "weak" key never expires and every loop that ever waited stays in memory. I reproduced this (40 of 40 loops kept). The GUI starts new loops on every run, so the leak grows over a long session. The fix: when a new loop's lock is added, first delete entries whose loop `is_closed()`. That also removes the `weakref` import. In the same stress test, only the last loop per thread is kept (8), and each is removed when the next loop starts.
   - Extra test: `test_finished_loops_are_not_kept`. It **fails** on the PR as submitted and passes with the change.
2. **Add `managers/sessionmanager/sessionmanager.py` to the patch's `FILES` list** (133 → 134 files).
   - ⚠️ This folder's copy isn't stock. Compared with the installed stock 3.14.7, it has **2 extra lines** from the "Major OF_Scraper 3.14.7 update" commit (`334c60f`) that were never shipped:
     - `sessionmanager.py:431` `cookie_jar=aiohttp.DummyCookieJar()` (async client)
     - `sessionmanager.py:689` `self._session.cookies.clear()` (sync client, before each request)
   - Both make the HTTP clients **ignore cookies the server sends back**. The login cookies (`sess`, `auth_id`, `auth_uid_`) are still sent on every request, because they're passed per request through `cookies=` (`auth/request.py:360-372`).
   - Checked with a local test server: aiohttp 3.13.3 and httpx 0.28.1 both still send the auth cookies, and a server-set cookie isn't sent back.
   - So shipping this file also ships that cookie change. It looks intentional and safe, but it's a behavior change for patched users.

### Scratch test results

- `test/unit` on a clean copy of HEAD + PR + change 1: 42 passed, 4 skipped. That copy doesn't include PRs #2–#4, which is why the total is lower than 60.

### Implementation (done 2026-10-23)

- The maintainer chose "implement + ship", including the 2 cookie lines.
- Applied from the git root with `git apply -p1`.
- **Small change 1 (leak):** `_alocks` is a plain dict. When a new loop's lock is added, entries for closed loops are deleted first. The `weakref` import is removed (`sessionmanager.py:124-137`). The file is byte-identical to the version tested in the scratch copy.
- **Extra test:** `test_finished_loops_are_not_kept` in `test/unit/test_session_sleep.py`. It **fails** on the PR as submitted and passes with the change.
- **Small change 2 (shipping):** `managers/sessionmanager/sessionmanager.py` added to the patch's `FILES` list, right after `sleepers.py`. `FILE_COUNT` is now 134.
- `test/unit`: **63 passed, 4 skipped**.
- Patch rebuilt as `20261023_gui_3_14_7_v369` with `rebuild_patch_zip.py --sync-root`:
  - All 134 payload files match the tree.
  - Test-installed into a clean copy of the stock 3.14.7 release (`932e9e1`, so the stock `sessionmanager.py` without the cookie lines). The new `sessionmanager.py` landed and the backup held the stock one. PR #2–#4 code and the `v369` ID were present.
  - `restore()` put the stock `sessionmanager.py` back.
- Not committed yet.

### Live test by the maintainer (2026-10-23)

- Installed `v369` and ran a full GUI scrape of one model (Linux).
- Result: **934 downloads (62 videos, 7 audios, 865 photos), 4.05 GB, 0 skipped, 0 failed**, in 5 min 25 s. 545 duplicates were recognized, and the run finished as "Complete".
- Logging in and requests worked normally with the 2 ignore-server-cookies lines shipped.
- Not covered: the cross-loop 429 backoff path itself (hard to trigger on purpose). The unit tests cover it.

---

## PR #6: fix(console): replace unencodable characters instead of crashing

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/6
- **Upstream issue (related):** datawhores/OF-Scraper#558
- **Size:** 2 files, +58 / -0
- **Verdict:** ✅ **Implement as is**, and add `utils/console.py` to the patch

### The problem, in plain words

Model names and post text can contain emoji. When the program's output isn't UTF-8, it can't write an emoji, and Python stops with `UnicodeEncodeError`. That happens on Windows when output is redirected to a file or pipe (cp1252), in some terminals, and in some bundled-exe setups. rich's message even suggests "add PYTHONIOENCODING=utf-8". The whole run stops, for example right after picking a model with an emoji in its name.

### What the PR changes

- New `replace_unencodable_output()` in `ofscraper/utils/console.py`. It runs once when that module loads, which is very early, because settings import it.
- For `sys.stdout` and `sys.stderr`: if the encoding isn't UTF-8/16/32, it calls `reconfigure(errors="replace")`, so characters that can't be written become `?` instead of crashing.
- UTF-8 streams are left alone. Streams that aren't real text files (`None`, `StringIO`, closed) are skipped.
- Adds `test/unit/test_console_encoding.py` (2 tests).

### What I checked

| Check | Result |
|---|---|
| Applies cleanly | ✅ |
| New tests **without** the fix | ❌ 2 failed, as the PR says |
| New tests with the fix | ✅ 2 passed |
| Real reproduction, `PYTHONIOENCODING=cp1252`, printing `Cherry 🍒` through the app's shared console | Before: 💥 `UnicodeEncodeError`. After: `Cherry ? done` |
| Same run: `logging` and plain `print` | Both fixed too (the fix is on the stream, so it covers every writer) |
| `PYTHONIOENCODING=utf_8` / `UTF8` | ✅ unchanged: emoji print normally, stream stays `strict` (Python reports the name as `utf-8` either way) |
| `None` streams (pythonw / windowed exe), `StringIO`, closed stream, already-written output | ✅ no errors |
| Is this folder's `console.py` the same as stock 3.14.7? | ✅ identical, so shipping it adds only this fix |
| Is `utils/console.py` in the GUI patch? | ❌ No, it isn't in `FILES` |
| `test/unit` on a clean copy of HEAD + PR | ✅ 41 passed, 4 skipped (without PRs #2–#5) |

### Why it's worth implementing

- A whole run can stop just because of an emoji in a name, which is common on this site.
- Changing the stream's error mode is the standard fix. It's small and doesn't change anything for UTF-8 users, which covers most Linux/macOS terminals and the modern Windows console.

### Small changes I'd make

1. **Add `utils/console.py` to the patch's `FILES` list** (134 → 135 files). No code changes needed.

### Not in scope (noted)

- `utils/context/stdout.py` (`lowstdout`, `nostdout`) briefly swaps `sys.stdout` for `open(os.devnull, "w")`. On Windows that uses the locale encoding in strict mode, so an emoji printed inside those blocks could still crash. They're only used around prompts (`prompts/utils/prompt_helpers.py:120,125,145`) and one path step (`utils/paths/manage.py:50`), and the output is thrown away. A one-word follow-up (`open(os.devnull, "w", errors="replace")`) would close it.

### Implementation (done 2026-10-23)

- The maintainer chose "implement + ship" without the `devnull` follow-up.
- Applied from the git root with `git apply -p1`, unchanged.
- `utils/console.py` added to the patch's `FILES` list, right after `utils/text.py`. `FILE_COUNT` is now 135.
- `test/unit`: **65 passed, 4 skipped**.
- Patch rebuilt as `20261023_gui_3_14_7_v370` with `rebuild_patch_zip.py --sync-root`:
  - All 135 payload files match the tree.
  - Test-installed into a clean copy of the stock 3.14.7 release (`932e9e1`). The new `console.py` landed, the backup held the stock one, and PR #2–#5 code and the `v370` ID were present.
  - **End to end:** with `PYTHONIOENCODING=cp1252`, the patched copy printed `Model: Cherry ? done`. After `restore()`, the same run crashed with `UnicodeEncodeError` again, which shows both the fix and the undo work.
- Not committed yet.

### Live test by the maintainer (2026-10-24, Windows)

- `v370` installed. In **cmd**, with `PYTHONIOENCODING` and `PYTHONUTF8` cleared: `ofscraper -u <model> -a download -o Pinned > run_log.txt 2>&1`. Redirected output on Windows uses cp1252.
- Result: **5 videos downloaded, 0 failed**, and the run finished normally.
- The emoji in the log came out as `?` instead of crashing, in 3 places:
  - `Status - ? UP`
  - `Subscription: ? Active` (`command.py:128`)
  - the whole "GLOBAL RUN TOTALS" block (📊 and every `➜`, `stats.py:551-588`)
- Not run: the same test on `v369` for a "before" comparison. The crash itself was reproduced with the app's console on Linux (see above).
- Side note, not this PR: the per-model line says `2.01 GB` and the global total says `2.16 GB` for the same 5 files. That's the same size in binary (GiB) and decimal (GB) units, so the two summaries use different size formats.

---

## PR #7: fix(naming): make textlength and text type settings take effect

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/7
- **Upstream issue:** datawhores/OF-Scraper#634
- **Size:** 4 files, +103 / -6
- **Verdict:** ✅ **Implement with small changes**. ⚠️ It changes new filenames for some users (see "Who sees a change").

### The problem, in plain words

`{text}` in a filename format is the post caption, cut to **Text Length**, counted in letters or words (**Text Type**). Three bugs meant these settings did almost nothing:

1. **`--textlength` was ignored.** click stores it as `args.textlength`, but `settings.py:144` read `args.text_length`. The args object returns `None` for unknown names (`utils/args/main.py:22-30`), so the flag was silently dropped.
2. **Text Type was always "word".** `--text-type` had `default="word"` (`arguments/file.py:15`), so `args.text_type or config` never reached the config. The config default is `"letter"` (`of_env/values/main.py:110`), and the GUI's "Text Type" dropdown writes to that config. **Picking "letter" in the GUI had no effect.**
3. **Word mode was wrong.**
   - It split on `"( )"`, which keeps the spaces as items, then took `length + 1` items. So it kept about half the words asked for: 3 → 2, 5 → 3.
   - It split on spaces, but the text has already been through `file_cleanup`, which swaps spaces for `space_replacer`. With a replacer like `_`, there were no spaces left, so **the whole caption was kept**.

### What the PR changes

- `settings.py`: reads `args.textlength`. It uses `is not None`, so `--textlength 0` (meaning "no limit") also overrides config.
- `arguments/file.py`: removes `default="word"` from `--text-type`, so config is used unless the flag is given.
- `base.py` `text_trunicate`, word mode: splits on `space_replacer` (or on spaces if the replacer isn't in the text) and keeps exactly `length` words.
- Adds `test/unit/test_textlength.py` (10 tests). One of them pins a documented limit: a `_` that was already in the caption counts as a word break when `_` is the replacer.

### What I checked

| Check | Result |
|---|---|
| All 3 claims | ✅ True (see above) |
| What text reaches `text_trunicate` | Always text already through `file_cleanup` (`media.py:388-390`, `placeholder.py:495,499,557`), so splitting on the replacer is right |
| Applies cleanly | ✅ |
| New tests **without** the fix | ❌ 5 failed, 5 passed, as the PR says |
| New tests with the fix | ✅ 10 passed |
| Do renamed files get downloaded again? | ✅ **No.** Skipping already-downloaded media uses the database by media ID (`filters/media/filters.py:216-229`), not the file path. Old files keep their old names; only new downloads use the new names |
| `base.py`, `arguments/file.py` same as stock 3.14.7? | ✅ identical. Neither is in the patch's `FILES` |
| `utils/settings.py` | Already in `FILES` (changed from stock by the GUI work), so it ships anyway |

### Who sees a change

Only users with **Text Length above 0** and `{text}` in their file format, for **new** downloads. Text Length 0 (the default, and **your config**) means "keep the whole caption", and that doesn't change.

Example caption: "Good morning everyone! Here is my new photo-set from the beach"

| Replacer | Length | Text Type in config | Before (always word, buggy) | After (with my change below) |
|---|---|---|---|---|
| space | 5 | word | `Good morning everyone!` (3 words) | `Good morning everyone! Here is` |
| space | 5 | letter | `Good morning everyone!` | `Good` |
| space | 20 | letter | whole caption | `Good morning everyon` |
| `_` | 5 | word | whole caption | `Good_morning_everyone!_Here_is` |
| `_` | 40 | letter | whole caption | `Good_morning_everyone!_Here_is_my_new_ph` |

The biggest change is for people who never set Text Type. The default is "letter", so their Text Length now counts letters. That's what the GUI tooltip, the help text and the config default always said it did.

### Small changes I'd make

1. **Don't let a letter cut end on a separator.** The letter branch `return`ed before the trailing-space cleanup, so `"Good morning"` cut to 5 became `"Good "`, and with `_` as the replacer, `"Good_"`. That code is old but was never reached before this PR. Fix: letter mode falls through to the shared cleanup, and the cleanup strips trailing spaces **and** trailing replacer characters.
   - Extra test: `test_letter_mode_does_not_end_on_a_separator` (space and `_`). It **fails** on the PR as submitted and passes with the change.
2. **Add `classes/of/base.py` and `utils/args/parse/arguments/file.py` to the patch's `FILES`** (135 → 137). Without them, patch users would get only the `settings.py` part (the `--textlength` flag), still be forced into word mode, and keep the broken word count.

### Side finding (not this PR)

- The GUI tooltip for Text Length (`gui/dialogs/config_dialog.py:570`) says "0 = do not include post text in media filenames". That's wrong: 0 means **no limit**, so the whole caption is kept (`base.py:22-23`). It's a one-line text fix.

### Scratch test results

- `test/unit` on a clean copy of HEAD + PR + change 1: 51 passed, 4 skipped (without PRs #2–#6).

### Implementation (done 2026-10-24)

- The maintainer chose "implement + ship + tooltip".
- Applied from the git root with `git apply -p1`.
- **Small change 1 (trailing separator):** `base.py` `text_trunicate`. Letter mode now falls through to the shared cleanup, which strips trailing spaces and trailing `space_replacer` characters. The file is byte-identical to the version tested in the scratch copy.
- **Extra test:** `test_letter_mode_does_not_end_on_a_separator` (space and `_`) in `test/unit/test_textlength.py`. It **fails** on the PR as submitted.
- **Small change 2 (shipping):** `classes/of/base.py` (after `classes/of/media.py`) and `utils/args/parse/arguments/file.py` (after `utils/args/parse/groups/download.py`) added to `FILES`. `FILE_COUNT` is now 137.
- **Side finding fixed:**
  - `gui/dialogs/config_dialog.py:570` tooltip now says "0 = no limit (keep the whole post text)."
  - `gui/help/GUI_HELP.md:640` now adds "`0` means no limit: the whole post text is kept."
- `test/unit`: **77 passed, 4 skipped**.
- Patch rebuilt as `20261024_gui_3_14_7_v371` with `rebuild_patch_zip.py --sync-root`:
  - All 137 payload files match the tree.
  - Test-installed into a clean copy of the stock 3.14.7 release (`932e9e1`). `base.py`, `arguments/file.py`, `settings.py` and `config_dialog.py` match the tree, and `restore()` put the stock files back.
  - **End to end, through the real settings code:** `--textlength 5`, config Text Type "letter", replacer `_`, caption "Good morning everyone":

    | | Settings | `{text}` |
    |---|---|---|
    | Patched (`v371`) | length 5, letter | `Good` |
    | Stock (after restore) | length **0** (flag ignored), **word** (config overridden) | `Good_morning_everyone` |
- Not committed yet.

### Live test by the maintainer (2026-10-24, Linux GUI)

- `v371` installed. Text Length set to 10, Text Type "letter", file format containing `{text}`. Downloaded one new timeline post with 5 images.
- Result: **5 downloads, 0 failed**. Every file got the `{text}` part `Good moani`, which is exactly 10 characters (`Good` + space + `moani`), cut mid-word as letter mode should. There was no trailing space or separator.
- Before `v371`, the same settings would have been forced into (broken) word mode, keeping about 6 words of the caption.

---

## PR #8: fix(download): don't fail finished downloads when a path can't be resolved

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/8
- **Upstream issue:** datawhores/OF-Scraper#619
- **Size:** 2 files, +138 / -37
- **Verdict:** ✅ **Implement as is**, and add `commands/scraper/actions/utils/paths.py` to the patch

### The problem, in plain words

After a file is moved into its folder, `addGlobalDir` remembers that folder so its date can be set at the end of the run. To do that it calls `Path.resolve()`. On some mapped or virtual Windows drives, `resolve()` fails with **WinError 1005** ("The volume does not contain a recognized file system").

It's worse than a wrong "failed" count. `addGlobalDir` runs **after** the move (`main_download.py:350-355`, `alt_download.py:443-450`) but **before** the file is marked downloaded in the database (`main_download.py:365-374`). So on such a drive, every file is saved but never marked. It's reported as failed and **downloaded again on every run**.

Other problems in the same code:
- `path.resolve(x)` calls `resolve` on the outer `path` and passes `x` as the `strict` argument. It worked by accident for a single path.
- A `str` path counts as "iterable", so it was split into characters, which crashes with `AttributeError`.
- `setDirectoriesDate` (end of run) compared resolved folders against an **unresolved** save root, so `is_relative_to` could stop the walk early. Any `OSError` there (from `samefile`, or from setting a folder's date) crashed the end of the download action.

### What the PR changes

`ofscraper/commands/scraper/actions/utils/paths.py`:
- New `_resolve()`: `resolve()`, falling back to `absolute()` on `OSError`. New `_resolve_dir()`: the folder itself, or the parent for a file.
- `addGlobalDir` / `addLocalDir` use them. A `str` or `PathLike` counts as one path.
- `setDirectoriesDate` resolves the save root the same way, and catches `OSError` around the folder walk and around setting each date. Failures are logged at debug level instead of raised.

It also adds `test/unit/test_dir_bookkeeping.py` (7 tests).

### What I checked

| Check | Result |
|---|---|
| The claims | ✅ True. Also confirmed the "never marked downloaded, so downloaded again" effect from the call order |
| Applies cleanly | ✅ |
| New tests **without** the fix | ❌ 4 failed, 3 passed, as the PR says |
| New tests with the fix | ✅ 7 passed |
| `test/unit` on a clean copy of HEAD + PR | ✅ 46 passed, 4 skipped (without PRs #2–#7) |
| **Extra: symlinked save folder** (e.g. `~/Data` → another drive) | Before: only the deepest folder (`Posts`) got its date set. After: `model`, `Free` and `Posts` do, same as a normal folder |
| **Extra: a subfolder that links outside the save root** | Same before and after: the walk stops there, as the original comment intends |
| `paths.py` same as stock 3.14.7? | ✅ identical (git `932e9e1` and the installed copy) |
| Is it in the GUI patch? | ❌ No, it isn't in `FILES` |

### Why it's worth implementing

- On affected drives, it turns "every download fails and re-downloads forever" into normal behavior. The only thing lost on such a drive is folder dates, which are cosmetic.
- Nothing changes on normal drives, apart from the symlink improvement above.
- If a folder's date can't be set, the run no longer crashes at the end.

### Small changes I'd make

1. **Add `commands/scraper/actions/utils/paths.py` to the patch's `FILES`** (137 → 138). No code changes.

### Notes (not blockers)

- `_resolve_dir` still calls `is_dir()`. On Python 3.12 that can raise for unusual errors. But the reported failure is in `resolve()`, and the old code already called `is_dir()` first without problems.
- I can't reproduce WinError 1005 on Linux. The tests simulate it by making `resolve()` / `samefile()` raise. A live test needs a Windows drive that shows the error, such as some RAM disks or virtual and cloud drives.

### Implementation (done 2026-10-24)

- The maintainer chose "implement + ship".
- Applied from the git root with `git apply -p1`, unchanged.
- `commands/scraper/actions/utils/paths.py` added to the patch's `FILES` list, right after `commands/scraper/actions/utils/log.py`. `FILE_COUNT` is now 138.
- `test/unit`: **84 passed, 4 skipped**.
- Patch rebuilt as `20261024_gui_3_14_7_v372` with `rebuild_patch_zip.py --sync-root`:
  - All 138 payload files match the tree.
  - Test-installed into a clean copy of the stock 3.14.7 release (`932e9e1`). The new `paths.py` landed, and `restore()` put the stock one back.
  - **End to end, simulated WinError 1005** (`Path.resolve` made to raise `OSError(1005)`), through the installed module:

    | | `addGlobalDir` after a download | `setDirectoriesDate` at end of run |
    |---|---|---|
    | Patched (`v372`) | ok, so the file goes on to be marked downloaded | ok |
    | Stock (after restore) | 💥 `OSError 1005`, so the file is never marked downloaded | not reached |
- Not committed yet.

---

## PR #9: fix(config): accept quoted CDM/ffmpeg paths and empty ffmpeg setting

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/9
- **Upstream issue:** datawhores/OF-Scraper#587
- **Size:** 4 files, +102 / -5
- **Verdict:** ✅ **Implement with a tiny change** (test file only)

### The problem, in plain words

1. **Quoted paths.** Windows Explorer's "Copy as path" puts double quotes around the path: `"C:\keys\private_key.pem"`. Pasted into `config.json`, the quotes become part of the text. The app then tries to open a file whose name really starts with `"`. On Windows that's `Errno 22 Invalid argument`, so the manual CDM fails every key request and **no DRM video downloads**. The same applies to the ffmpeg path, temp folder and save location.
2. **Empty ffmpeg setting.** The shipped config has `"ffmpeg": ""`. `get_ffmpeg()` returned `""` as is, so the `OFSC_FFMPEG_DEFAULT` environment variable could never be used.

### What the PR changes

- `utils/config/data.py`: new `strip_path_quotes()`, which trims spaces and removes **one** matching pair of `"` or `'` around the value. It's used for `private-key`, `client-id`, `ffmpeg` and `temp_dir`.
- `utils/paths/common.py`: `get_save_location()` strips quotes too.
- `utils/settings.py`: `merged.ffmpeg = get_ffmpeg() or OFSC_FFMPEG_DEFAULT`. The fallback is applied when settings are built, **not** in the getter. That matters because `auto_update_config` writes the config file back from these getters (`schema.py:48`), so a fallback in the getter would save the env value into `config.json`.
- Adds `test/unit/test_config_paths.py` (12 tests).

### What I checked

| Check | Result |
|---|---|
| The claims | ✅ True |
| Same fields as the GUI's own path list? | ✅ Exactly the 5 in `utils/config/path_norm.py:12-18` (`WINDOWS_FS_PATH_FIELDS`). That normalizer doesn't handle quotes: a quoted value doesn't match its drive-letter check, so it's left as is |
| Where the real ffmpeg path comes from | `settings.get_settings().ffmpeg` (`utils/system/ffmpeg.py:97`), so the fallback is in the right place |
| Applies cleanly on the current tree (PRs #2–#8 in) | ✅ |
| New tests **without** the fix | ❌ 10 failed, 2 passed, as the PR says |
| New tests with the fix | ✅ 12 passed |
| `test/unit` on a clean copy of HEAD + PR | ✅ 51 passed, 4 skipped (without PRs #2–#8) |
| Are the files in the GUI patch? | ✅ All 3 (`utils/config/data.py`, `utils/paths/common.py`, `utils/settings.py`) are already in `FILES`. No list change needed, just a rebuild |
| Who sets `OFSC_FFMPEG_DEFAULT`? | Nothing in the repo or `docker/`. It's only for users who set it themselves |

### Why it's worth implementing

- A pasted path with quotes silently breaks DRM downloads, and the error ("Invalid argument") doesn't point to the cause. This is a common mistake on Windows.
- Removing only one matching pair of quotes can't damage a normal path.
- Side benefit: when the config is rewritten, the cleaned values are what get saved, so the quotes disappear from the file too.

### Small change I'd make

1. **Use a raw string in the test.** `test_save_location_is_unquoted` has `"D:\Media\OnlyFans"` written with single backslashes in a normal string. `\M` and `\O` are invalid escape sequences: Python 3.12 shows a `SyntaxWarning`, and it's an error under `-W error` and in future Python versions. Write it as `r"D:\Media\OnlyFans"` (and `r'"D:\Media\OnlyFans"'`). The test result is unchanged.

### Notes (not blockers)

- `advanced_options.env_files` (also normalized in `path_norm.py`) doesn't get quote stripping. It's rarely pasted.
- The GUI's DRM dialog and config dialog could strip quotes when saving, so the file stays clean. The getters now cover it at read time either way.

### Implementation (done 2026-10-24)

- The maintainer chose "implement + rebuild".
- Applied from the git root with `git apply -p1`.
- **Small change 1:** `test_save_location_is_unquoted` uses raw strings. The file now compiles cleanly under `python -W error`.
- `test/unit`: **96 passed, 4 skipped**.
- Patch rebuilt as `20261024_gui_3_14_7_v373` with `rebuild_patch_zip.py --sync-root`:
  - Still 138 files, and all of them match the tree.
  - Test-installed into a clean copy of the stock 3.14.7 release (`932e9e1`). The 3 changed files match the tree, and `restore()` works.
  - **End to end, through the real getters and settings:** config with `"private-key": "\"<path>\""` (as pasted from "Copy as path"), `"ffmpeg": ""`, and `OFSC_FFMPEG_DEFAULT=/opt/env-ffmpeg`:

    | | Private key path | Opens? | `settings.ffmpeg` | ffmpeg written back to config |
    |---|---|---|---|---|
    | Patched (`v373`) | quotes removed | ✅ yes | `/opt/env-ffmpeg` | `""` (env value not saved) |
    | Stock (after restore) | `"\"<path>\""` | ❌ `FileNotFoundError` (on Windows: `Errno 22 Invalid argument`) | `""` (env ignored) | (stock's schema helper differs, not compared) |
- Not committed yet.

### Live test by the maintainer (2026-10-24, Windows GUI, `v373`)

- In Configuration → CDM, the Private Key File was set to `"C:\Users\<user>\.config\ofscraper\device\private_key.pem"` **with the quotes**, as pasted from "Copy as path", and saved.
- Ran a DRM scrape (one timeline video). **1 video downloaded, 0 failed**: keys were fetched and the video decrypted. Before `v373` this failed with `Errno 22 Invalid argument`.
- ⚠️ The status bar showed a **false "Key: CDM?" warning** ("Key Mode is manual but client_id.bin / private_key.pem paths are missing or invalid"). The GUI's own checks read the raw config value, quotes included. That was predicted before the test and is fixed in the follow-up below.

### Follow-up: GUI checks strip quotes too (`v374`, 2026-10-24)

- **Problem:** 3 GUI checks read the raw `config.json` values and test whether those files exist, so a quoted path was reported as missing although downloads work:
  - `gui/utils/health_check.py` `_key_chip` (the "Key: CDM?" chip): client-id, private-key
  - `gui/utils/config_validation.py` `validate_config` (the "Config" chip): save location, ffmpeg
  - `gui/main_window.py` `_maybe_show_missing_dependency_notice` (startup prompt): ffmpeg, client-id, private-key
- **Fix:** all 3 now use `strip_path_quotes`.
- **Where the helper lives:** `strip_path_quotes` moved from `utils/config/data.py` to `utils/config/path_norm.py`, which is import-safe: no settings or CLI side effects, so GUI helpers and unit tests can import it alone. `data.py` re-imports it, so `data.strip_path_quotes` and `paths/common.py` work unchanged.
- **Tests:** 2 new tests in `test/unit/test_config_paths.py`. Both **fail** on the GUI code before this change.
  - `test_key_chip_accepts_quoted_cdm_paths`: supplies a small stand-in for `gui/utils/key_mode_warning`, because the real one imports PyQt6, which `test/unit` doesn't install.
  - `test_config_check_accepts_quoted_ffmpeg_and_save_location`
- `test/unit`: **98 passed, 4 skipped**.
- Patch rebuilt as `20261024_gui_3_14_7_v374`. Still 138 files, because all 5 changed files were already in `FILES`. All match the tree.
  - Test-installed into a clean stock 3.14.7 copy (`932e9e1`). The installed copy passes all 14 tests in `test_config_paths.py`. `restore()` brings back the replaced stock files (`main_window.py`, `data.py` checked). Files the patch **adds** (for example `gui/utils/health_check.py`, `utils/config/path_norm.py`) stay after a restore. That's how the installer has always worked, and stock code never imports them.
- Not committed yet.

### Live test of the follow-up by the maintainer (2026-10-24, Windows GUI, `v374`)

- Same setup: private key path saved **with quotes**. Ran the same DRM scrape.
- **1 video downloaded, 0 failed**, and the status bar now shows **"Key: manual" in green**, with "Auth ✓" and "Config ✓". The false "Key: CDM?" warning is gone.

---

## PR #10: fix(prompts): keep model selector prompts visible and stdout intact

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/10
- **Upstream issues:** datawhores/OF-Scraper#551, datawhores/OF-Scraper#581
- **Size:** 3 files, +102 / -36
- **Verdict:** ✅ **Implement as is**, and add both files to the patch. One optional extra (see below).
- **Scope:** the **terminal (CLI) model selector** only. The GUI has its own model selector page and doesn't use these prompts.

### The problem, in plain words

In the terminal model selector ("Which models do you want to scrape"):

1. **Range select (Alt+B) looked frozen.** It rebuilt the list by calling `_get_choices()`, which calls `get_models_from_prompt()` (`managers/model.py:373-390`). That starts with `setfilter()`, the interactive **filter menu**. All of this ran inside `stdout.nostdout()`, so the menu was invisible. The keys the user typed for the range went into a menu they couldn't see. The "Range Select / Range Deselect" choice and the number prompt were hidden too.
2. **The filter menu (Alt+X) had the same problem.** `model_funct` also ran `_get_choices()` inside `nostdout()` (`prompt_helpers.py:120-121`).
3. **`nostdout()` broke on any error.** It had a bare `except:` that **yielded a second time**. Inside a `contextmanager`, that turns any exception in the body, including Ctrl+C in a prompt, into `RuntimeError: generator didn't stop after throw()`. And `sys.stdout` stayed pointed at devnull, so the rest of the session printed nothing.

### What the PR changes

- `prompts/utils/prompt_helpers.py`:
  - `model_funct` (Alt+X): no `nostdout()` around `_get_choices()`, so the filter menu shows.
  - `model_select_funct` (Alt+B): no `nostdout()`, so the select/deselect choice and the number prompt show.
  - `_select_helper`: numbers against **the list already on screen** (`prompt.content_control._raw_choices`) instead of re-running the filter menu.
- `utils/context/stdout.py`: `nostdout()` restores stdout in a `finally` and closes the devnull file (the old code never closed it). `lowstdout()` reuses `nostdout()`.
- Adds `test/unit/test_model_selector.py` (4 tests).

### What I checked

| Check | Result |
|---|---|
| The claims | ✅ True (see the code references above) |
| Applies cleanly on the current tree (PRs #2–#9 in) | ✅ |
| New tests **without** the fix | ❌ 3 failed, 1 passed, as the PR says |
| New tests with the fix | ✅ 4 passed |
| `test/unit` on a clean copy of HEAD + PR | ✅ 43 passed, 4 skipped (without PRs #2–#9) |
| **Extra: a real InquirerPy `FuzzyPrompt`** (the PR's tests use simple stand-ins) | ✅ `_raw_choices` holds `Choice` objects. With #1 ticked by hand, range select "3-4" → #1, #3, #4; then range deselect "1,4" → #3. The filter menu was never reopened |
| Both files same as stock 3.14.7? | ✅ identical |
| In the GUI patch? | ❌ Neither is in `FILES` |

### Why it's worth implementing

- Two upstream issues report the selector "hanging". This fixes the cause.
- The `nostdout()` fix stops one Ctrl+C from silencing the whole session.

### Small changes I'd make

1. **Add `prompts/utils/prompt_helpers.py` and `utils/context/stdout.py` to the patch's `FILES`** (138 → 140). No code changes.

### Optional extra (the follow-up noted under PR #6)

- `nostdout()` opens devnull with the default encoding, which is cp1252 in strict mode on Windows. Printing an emoji inside it raises `UnicodeEncodeError`, even though the output is thrown away. This PR rewrites those exact lines, so `open(os.devnull, "w", encoding="utf-8")` is a one-word addition here: devnull can always take UTF-8.

### Minor (not worth changing)

- The new test file has `import sys` twice.

### Implementation (done 2026-10-24)

- The maintainer chose "ship + devnull utf-8".
- Applied from the git root with `git apply -p1`.
- **Extra (devnull UTF-8):** `nostdout()` opens devnull with `encoding="utf-8"` (`utils/context/stdout.py`). This also closes the follow-up noted under PR #6.
  - New test `test_nostdout_accepts_any_character`. Under a non-UTF-8 locale (`LC_ALL=en_GB.iso885915`, which acts like Windows cp1252), it **fails** on the PR as submitted and passes with the change. Under this machine's normal UTF-8 locale it passes either way.
- **Shipping:** `prompts/utils/prompt_helpers.py` (after `utils/auth/utils/prompt.py`) and `utils/context/stdout.py` (after `utils/paths/common.py`) added to `FILES`. `FILE_COUNT` is now 140.
- `test/unit`: **103 passed, 4 skipped**.
- Patch rebuilt as `20261024_gui_3_14_7_v375` with `rebuild_patch_zip.py --sync-root`:
  - All 140 payload files match the tree.
  - Test-installed into a clean stock 3.14.7 copy (`932e9e1`):
    - Real InquirerPy range select / deselect works.
    - `test_model_selector.py` passes 5/5 under the latin-9 locale.
  - After `restore()`, both files are stock again, and the same tests fail (4 failed, 1 passed).
- Not committed yet.
- **To try it:** run `ofscraper` in a terminal (not `--gui`) and open the model selector. Press **Alt+B**. The "Range Select / Range Deselect" choice should appear, then the number prompt, with no hidden filter menu in between.

---

## PR #11: fix(models): don't drop to the main menu after 'Yes Update Selection'

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/11
- **Upstream issue:** datawhores/OF-Scraper#560
- **Size:** 3 files, +44 / -2
- **Verdict:** ✅ **Implement as is**, and add `utils/args/mutators/user.py` to the patch
- **Scope:** the **terminal (CLI)** menu only. The GUI uses the daemon/GUI branch (`managers/model.py:121-124`) and never shows this prompt.

### The problem, in plain words

In the terminal app, on a second scrape in the same session, you're asked whether to keep the previous model selection. Choosing **"Yes Update Selection"** should show the model list again. Instead you're dropped back to the main menu.

Why:
- With no `--username`, the value is an empty list. Click gives `()` for a `multiple=True` option, and `StringSplitParse` turns that into `[]`.
- "Yes Update Selection" calls `settings.resetUserSelect()` (`model.py:137-140`), which set it to **`None`** (`utils/args/mutators/user.py:27`).
- `_select_models_scraper` then runs `"ALL" in usernames` (`model.py:286`). With `None`, that raises `TypeError`, the menu catches it, and you're back at the main menu.

### What the PR changes

- `utils/args/mutators/user.py`: `resetUserSelect()` sets `args.usernames = []`, the same as the CLI default.
- `managers/model.py`: `usernames = settings.get_settings().usernames or []`, a guard in case `None` comes from somewhere else (for example `commands/check.py:527` sets it to `None`).
- Adds `test/unit/test_update_selection.py` (2 tests).

### What I checked

| Check | Result |
|---|---|
| The claim | ✅ True |
| Applies cleanly on the current tree (PRs #2–#10 in) | ✅ |
| New tests **without** the fix | ❌ 2 failed, with the exact `TypeError: argument of type 'NoneType' is not iterable` at `model.py:285` |
| New tests with the fix | ✅ 2 passed |
| `test/unit` on a clean copy of HEAD + PR | ✅ 41 passed, 4 skipped (without PRs #2–#10) |
| **Extra: real reset path through settings** | Before: startup `[]` → after `resetUserSelect()` **`None`** → `TypeError`. With the PR: `[]` → `[]` → `"ALL" in usernames` is `False`, so the model list opens |
| Other readers of `usernames` | `retriver.py:30` treats `None` and `[]` the same. `individual.py:30` behaves better with `[]` (with `None` it built `{None}`) |
| `managers/model.py` | Already in `FILES` |
| `utils/args/mutators/user.py` | Not in `FILES`. Same as pip stock (the installed copy) |

### Why it's worth implementing

- A one-word fix for a menu choice that never worked on a second run, plus a guard against the same crash from other paths.

### Small changes I'd make

1. **Add `utils/args/mutators/user.py` to the patch's `FILES`** (140 → 141). No code changes.

### Note

- Commit `932e9e1` ("OF-Scraper-3.14.7 released") already includes the GUI work, so "same as `932e9e1`" doesn't always mean "same as pip stock". For files the patch didn't ship before, I compare against the installed copy, which is pip stock for those files.

### Implementation (done 2026-10-24)

- The maintainer chose "implement + ship".
- Applied from the git root with `git apply -p1`, unchanged.
- `utils/args/mutators/user.py` added to `FILES` (after `utils/args/parse/groups/program.py`). `FILE_COUNT` is now 141.
- `test/unit`: **105 passed, 4 skipped**.
- Patch rebuilt as `20261024_gui_3_14_7_v376` with `rebuild_patch_zip.py --sync-root`:
  - All 141 payload files match the tree.
  - Test-installed into a clean copy (`932e9e1`). The real reset path gives `[]`, with no `TypeError`.
  - After `restore()`, `user.py` is pip stock again, and the same path gives `None` → `TypeError`.
- Not committed yet.
- **To try it:**
  1. Run `ofscraper` in a terminal (not `--gui`) and scrape once.
  2. Pick the scrape action again from the main menu.
  3. At the "reset username" prompt, choose **"Yes Update Selection"**. The model list should open instead of the main menu.

### Live test by the maintainer (2026-10-24, Windows terminal, `v376`)

- First scrape: 934 downloads, 0 failed. The app returned to the main menu as normal.
- Second scrape in the same session: **Perform Action(s)** → same action → "Do you want to reset username info" → **"Yes Update Selection"**. ✅ **The model selector opened** (before the fix: back to the main menu).

---

## PR #12: fix(paid): warn when a Purchases scan stops early

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/12
- **Upstream issue (related):** datawhores/OF-Scraper#600
- **Size:** 2 files, +111 / -7
- **Verdict:** ✅ **Implement, but only with the change below.** ⚠️ As submitted, it **logs the login cookie and signing headers** in a warning whenever a Purchases request fails with an HTTP error.

### The problem, in plain words

When the Purchases scan (`data/api/paid.py`, `scrape_paid` and `scrape_all_paid`) hit an HTTP error, an unexpected reply, or an exception, it stopped. It said so only in a **debug** or **info** line. A run could finish with no purchased content and nothing on screen to explain why.

### What the PR changes

- The 3 early-stop cases in both scans now log a **warning** that names the model (or "all models"), the offset and the reason, ending with "Purchases may be incomplete."
- Scan behavior is unchanged: it still stops at the same points.
- Adds `test/unit/test_paid_scan_warnings.py` (8 tests).

### What I checked

| Check | Result |
|---|---|
| Applies cleanly on the current tree (PRs #2–#11 in) | ✅ |
| New tests **without** the fix | ❌ 6 failed, 2 passed, as the PR says |
| New tests with the fix | ✅ 8 passed |
| How HTTP errors reach this code | The session raises for any non-2xx except 404 (`sessionmanager.py:660-670`) and retries with `reraise=True` (`:632-636`). So a 403/429/5xx arrives as the original **`aiohttp.ClientResponseError`** in the `except` branch. Only a 404 reaches the "not 2xx" branch |
| ⚠️ **What `{E!r}` prints for that error** (local test server, aiohttp 3.13.3) | `repr()` includes `RequestInfo(... headers=<CIMultiDictProxy('x-bc': ..., 'sign': ..., 'Cookie': 'sess=...; auth_id=...')>)`. **All 3 fake secrets appeared.** `str(E)` is only `403, message='Forbidden', url='...'` |
| Does the current code leak? | No. `log.traceback_(E)` formats with `%s` (that is, `str`), and `traceback.format_exc()` ends with `str(E)` too. Only the PR's new `!r` adds the headers |
| `data/api/paid.py` in the GUI patch? | ✅ Already in `FILES` |

### Why it's worth implementing (with the fix)

- "Purchased finished with nothing and no reason" is a real support problem. A clear warning with the HTTP status points straight at the cause: expired login, rate limit, or server error.

### Required change

1. **Log `{type(E).__name__}: {E}` instead of `{E!r}`** in both `except` blocks. That keeps the useful part (`ClientResponseError: 403, message='Forbidden', url='...'`) without the request headers. The type name also helps when an exception's message is empty, like a bare `TimeoutError()`.
   - New test `test_http_error_warning_does_not_leak_request_headers` (per-model and all-models). It builds a real `ClientResponseError` whose request headers contain `SECRET`. It **fails on the PR as submitted** (the warning contains `SECRET`) and passes with the change.

### Scratch test results

- PR + change: `test_paid_scan_warnings.py` 10 passed; `test/unit` 49 passed, 4 skipped (clean copy of HEAD, without PRs #2–#11).

### Implementation (done 2026-10-24)

- The maintainer chose "implement with fix".
- Applied from the git root with `git apply -p1`.
- **Required change:** both `except` warnings use `{type(E).__name__}: {E}`. No `!r` is left in `paid.py`. The file is byte-identical to the version tested in the scratch copy.
- **Extra test:** `test_http_error_warning_does_not_leak_request_headers` (2 cases).
- `test/unit`: **115 passed, 4 skipped**.
- Patch rebuilt as `20261024_gui_3_14_7_v377` with `rebuild_patch_zip.py --sync-root`. Still 141 files, and all match the tree.
  - Test-installed into a clean copy (`932e9e1`): `test_paid_scan_warnings.py` 10/10 pass.
  - After `restore()`: 8 failed, 2 passed (no warnings in the old code).
- Not committed yet.
- **To see it live:** this only shows when a Purchases scan fails, which can't be forced safely. On a normal run, nothing changes. If a run ever finishes with missing purchased content, look for a yellow "Purchased scan for <model> stopped at offset N: HTTP ..." warning.



---

## PR #13: feat(paid): skip --excluded-username models during --scrape-paid

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/13
- **Upstream issue:** datawhores/OF-Scraper#474
- **Size:** 4 files, +188 / -1
- **Verdict:** ✅ **Implement as is**, and add the 3 code files to the patch
- **Type:** a small **feature**, not a bug fix. It only changes anything when `--scrape-paid` and `--excluded-username` are used together. Today that combination silently ignores the exclusion.

### The problem, in plain words

`--scrape-paid` downloads everything you've bought from **every** model. `--excluded-username` (`-eu`) is meant to leave models out, but it was only applied to the normal model list (`filters/models/other.py` `otherFilters`), never to the scrape-paid path. So you couldn't skip one model during a scrape-paid run.

### What the PR changes

- `filters/models/other.py`: new `is_excluded_username(username)`. It ignores case: the option's callback already lowercases its values, and the model's name is lowercased here.
- `data/posts/post.py` `process_all_paid`: right after the username is known, including the **recorded name of a deleted model**, it skips excluded models with a warning ("Skipping bob_2: excluded by --excluded-username"). That happens **before** any table creation or post/media writes. Both download and metadata scrape-paid runs go through here, and skipped models aren't counted in the totals.
- `utils/args/parse/arguments/user_select.py`: the `-eu` help text mentions scrape-paid.
- Adds `test/unit/test_scrape_paid_excluded_username.py` (9 tests).

### What I checked

| Check | Result |
|---|---|
| The claim (`-eu` ignored by scrape-paid) | ✅ True. `process_all_paid` (`post.py:317-394`) never looks at `excluded_username` |
| Applies cleanly on the current tree (PRs #2–#12 in) | ✅ |
| New tests **without** the change | ❌ 6 failed, 3 passed, as the PR says |
| New tests with the change | ✅ 9 passed |
| `test/unit` on a clean copy of HEAD + PR | ✅ 48 passed, 4 skipped (without PRs #2–#12) |
| **Extra: real `-eu` parsing** (`UsernameParse`) | `-eu "Bob,carol"` → `['carol', 'bob']`; `-eu bob -eu CAROL` → `['bob', 'carol']`; no `-eu` → `[]`. Matching `bob`/`Carol` works, `alice` isn't matched |
| Effect on the GUI | None by default. The GUI has a scrape-paid checkbox (`workflow.py:2597`) but never sets `excluded_username`, so only someone starting the GUI with `-eu` on the command line would see it |
| The 3 code files: same as pip stock? | ✅ identical to the installed copy |
| In the GUI patch? | ❌ None of them is in `FILES` |

### Why it's worth implementing

- It closes a real gap with a check that's small, placed early and covered by tests. Nothing changes unless both options are used together.

### Small changes I'd make

1. **Add `data/posts/post.py`, `filters/models/other.py` and `utils/args/parse/arguments/user_select.py` to the patch's `FILES`** (141 → 144). No code changes.

### Notes (not blockers)

- The model's profile is still looked up before the skip, because the username comes from it. That's one extra API call per excluded model.
- A deleted model with no recorded name only has the placeholder name, so it can't be matched. The tests pin this on purpose.

### Implementation (done 2026-10-24)

- The maintainer chose "implement + ship".
- Applied from the git root with `git apply -p1`, unchanged.
- Added to `FILES`:
  - `data/posts/post.py` (after `data/api/paid.py`)
  - `filters/models/other.py` (after `filters/media/filters.py`)
  - `utils/args/parse/arguments/user_select.py` (after `utils/args/mutators/user.py`)
- `FILE_COUNT` is now 144.
- `test/unit`: **124 passed, 4 skipped**.
- Patch rebuilt as `20261024_gui_3_14_7_v378` with `rebuild_patch_zip.py --sync-root`:
  - All 144 payload files match the tree.
  - Test-installed into a clean copy (`932e9e1`). The new tests pass 9/9, and `ofscraper --help` shows the new `-eu` help text.
  - After `restore()`, all 3 files are pip stock again, and the tests are back to 6 failed, 3 passed.
- Not committed yet.
- **To try it:** `ofscraper --scrape-paid -eu <a model you've bought from> -a download`. That model should show "Skipping <name>_<id>: excluded by --excluded-username", get no downloads, and not appear in the totals.

---

## PR #14: fix(metadata): stop passing mediatype to get_hash

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/14
- **Size:** 2 files, +61 / -4
- **Verdict:** ✅ **Implement as is**, and add `commands/metadata/manager.py` to the patch

### The problem, in plain words

The **metadata** command updates the database to match files already on disk. With hashing turned on (`advanced_options.remove_hash_match`), `_metadata_hash_helper` called `hash.get_hash(path, mediatype=...)` when the planned file existed. But `get_hash()` takes only the file (`utils/hash.py:18-20`), so Python raised `TypeError`.

That error happens while building the arguments for `mark_media_as_downloaded` (`commands/metadata/manager.py:63-71`), so **the database row is never updated**. `metadata()` catches it (`:38-46`) and reports the media as **"skipped"**, with the reason only in debug lines.

The other branch of the same helper (`:137`) already calls `get_hash()` correctly.

### What the PR changes

- Removes the extra `mediatype=` argument (one line).
- Adds `test/unit/test_metadata_hash.py` (3 tests).

### What I checked

| Check | Result |
|---|---|
| The claim | ✅ True |
| Other `get_hash()` callers | ✅ Correct: the download path goes through `commands/scraper/actions/utils/general.py:24-31`, passing only the file |
| Applies cleanly on the current tree (PRs #2–#13 in) | ✅ |
| New test **without** the fix | ❌ 1 failed (`TypeError: get_hash() got an unexpected keyword argument 'mediatype'`), 2 passed, as the PR says |
| New tests with the fix | ✅ 3 passed |
| `test/unit` on a clean copy of HEAD + PR | ✅ 42 passed, 4 skipped (without PRs #2–#13) |
| Who's affected | Only metadata runs with hashing on. Your config has `"remove_hash_match": null`, so you're not affected |
| `commands/metadata/manager.py` same as pip stock? | ✅ identical to the installed copy |
| In the GUI patch? | ❌ No, it isn't in `FILES` |

### Why it's worth implementing

- A one-line fix for a crash that silently stops the metadata command from doing its job when hashing is on.

### Small changes I'd make

1. **Add `commands/metadata/manager.py` to the patch's `FILES`** (144 → 145). No code changes.

### Implementation (done 2026-10-24)

- The maintainer chose "implement + ship".
- Applied from the git root with `git apply -p1`, unchanged.
- `commands/metadata/manager.py` added to `FILES` (after `commands/check.py`). `FILE_COUNT` is now 145.
- `test/unit`: **127 passed, 4 skipped**.
- Patch rebuilt as `20261024_gui_3_14_7_v379` with `rebuild_patch_zip.py --sync-root`:
  - All 145 payload files match the tree.
  - Test-installed into a clean copy (`932e9e1`): `test_metadata_hash.py` 3/3.
  - After `restore()`, `manager.py` is pip stock again, and the test fails as before (1 failed, 2 passed).
- Not committed yet.
- **To try it (optional):** it only matters with hashing on.
  1. Set `advanced_options.remove_hash_match` to `true` in the config.
  2. Run the metadata command on a model you've already downloaded, for example `ofscraper metadata -u <model> -o Pinned --metadata update` (`metadata` is a subcommand; the modes are `check`, `update`, `complete`).
  3. Items should be updated, not reported as "skipped".
  4. Set `remove_hash_match` back to `null` afterwards if you don't want hashing.

---

## PR #15: fix(profile): skip the profile area for deleted accounts

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/15
- **Size:** 2 files, +57 / -0
- **Verdict:** ✅ **Implement as is**. `data/posts/post.py` has been in the patch since `v378`, so only a rebuild is needed.

### The problem, in plain words

When the Profile area is scraped for an account that **no longer exists**, the profile API returns 404. The app then returns only a placeholder, `{"username": <deleted-model placeholder>}` (`data/api/profile.py:46-47, 73-74`). `process_profile` passed that to `parse_profile`, which reads `profile["name"]` and raises **`KeyError: 'name'`**.

The `except` in `process_profile` caught it and returned nothing, so the **result was already right**, but a full **traceback** was logged for every deleted account. That looks like a crash and hides real problems in the logs.

### What the PR changes

- `data/posts/post.py` `process_profile`: if the profile is the placeholder, log "Skipping profile for <name>: the account no longer exists" (info level) and return no posts. A deleted account has no avatar or header to download.
- Adds `test/unit/test_profile_deleted_model.py` (2 tests: deleted → skipped without a traceback; a normal profile still gives its avatar post).

### What I checked

| Check | Result |
|---|---|
| The claim | ✅ True (code references above) |
| Behavior change | Only logging. The returned value (`[]`, `API`) is the same as before |
| Applies cleanly on the current tree (PRs #2–#14 in, including PR #13's change to the same file) | ✅ |
| New tests **without** the fix | ❌ 1 failed (a traceback was logged), 1 passed, as the PR says |
| New tests with the fix | ✅ 2 passed |
| `test/unit` on a clean copy of HEAD + PR | ✅ 41 passed, 4 skipped (without PRs #2–#14) |
| `data/posts/post.py` in the GUI patch? | ✅ Yes, since `v378` (PR #13) |

### Why it's worth implementing

- It removes a misleading traceback for an ordinary case: deleted accounts you once subscribed to or bought from. It's tiny and covered by tests.

### Small changes I'd make

- None. It just needs a patch rebuild (`v380`, still 145 files).

### Implementation (done 2026-10-24)

- The maintainer chose "implement + rebuild".
- Applied from the git root with `git apply -p1`, unchanged. It sits next to PR #13's change in the same file.
- `test/unit`: **129 passed, 4 skipped**.
- Patch rebuilt as `20261024_gui_3_14_7_v380` with `rebuild_patch_zip.py --sync-root`:
  - Still 145 files, and all match the tree.
  - Test-installed into a clean copy (`932e9e1`). The PR #15 tests and the PR #13 tests all pass (11/11), since both change `post.py`.
  - After `restore()`, `post.py` is pip stock again, and the PR #15 test fails as before.
- Not committed yet.
- **To see it live:** scrape the Profile area (`-o Profile`) for a model whose account was deleted. That's usually one that shows up as `modeldeleted` in Purchased. The log should show "Skipping profile for <name>: the account no longer exists" instead of a `KeyError: 'name'` traceback.
- **Live test:** not possible. The maintainer has no deleted accounts to test with (2026-10-24). The unit tests cover it.

---

## PR #16: fix(models): keep deleted-account placeholders out of the normal scrape

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/16
- **Size:** 3 files, +51 / -3
- **Verdict:** ✅ **Implement as is**, and add `classes/of/models.py` to the patch

### The problem, in plain words

When `--scrape-paid` finds content from an account that was deleted, `add_models` creates a **placeholder model** for it: `Model({"username": "modeldeleted_<id>", "id": "modeldeleted_<id>"})`, with no avatar or header (`managers/model.py:208-216`). That placeholder stays in the model list.

If the same run then does a normal scrape with **`--username ALL`**, the placeholders are selected like real models. The first thing the normal pass reads is `.avatar`, and `Model.avatar` was `self._model["avatar"]`, which raises **`KeyError: 'avatar'`** for each deleted account.

### What the PR changes

- `managers/model.py` `_apply_filters`: drops models whose name starts with the deleted-model placeholder **before** the normal filters run. That's the same rule `add_models` uses to recognize them (`:189`). They stay in the store, so the paid pass can still use them.
- `classes/of/models.py`: `avatar` and `header` use `.get(...)`, so they return `None` when missing, like the other properties.
- Adds `test/unit/test_paid_placeholder_models.py` (2 tests).

### What I checked

| Check | Result |
|---|---|
| The claim | ✅ True (code references above) |
| Code that reads `.avatar` copes with `None` | ✅ `commands/utils/command.py:102,132` (guarded by `and avatar`), `commands/scraper/scraper.py:92` and `commands/metadata/metadata.py:145` (only passed along) |
| GUI | Also calls `_apply_filters` (`gui/main_window.py:392`), but on a freshly fetched list that never has placeholders, so no change |
| Applies cleanly on the current tree (PRs #2–#15 in) | ✅ |
| New tests **without** the fix | ❌ 2 failed (`KeyError: 'avatar'`), as the PR says |
| New tests with the fix | ✅ 2 passed |
| `test/unit` on a clean copy of HEAD + PR | ✅ 41 passed, 4 skipped (without PRs #2–#15) |
| `managers/model.py` | Already in `FILES` |
| `classes/of/models.py` | Not in `FILES`. Same as pip stock |

### Why it's worth implementing

- `--scrape-paid --username ALL` is a common "get everything" command. With any deleted account among your purchases, the normal pass hit errors for each one.

### Small changes I'd make

1. **Add `classes/of/models.py` to the patch's `FILES`** (145 → 146). No code changes.

### Note

- A real account whose username happens to start with `modeldeleted` would also be left out. That's very unlikely, and it's the same rule `add_models` already uses.

### Implementation (done 2026-10-24)

- The maintainer chose "implement + ship".
- Applied from the git root with `git apply -p1`, unchanged. It sits next to PR #11's change in `managers/model.py`.
- `classes/of/models.py` added to `FILES` (after `classes/of/base.py`). `FILE_COUNT` is now 146.
- `test/unit`: **131 passed, 4 skipped**.
- Patch rebuilt as `20261024_gui_3_14_7_v381` with `rebuild_patch_zip.py --sync-root`:
  - All 146 payload files match the tree.
  - Test-installed into a clean copy (`932e9e1`). The PR #16 tests and the PR #11 tests pass (4/4), since both change `managers/model.py`.
  - After `restore()`, `models.py` is pip stock again, and the PR #16 tests fail as before (2 failed).
- Not committed yet.
- **Live test:** not possible. Like PR #15, it needs a deleted account among the maintainer's purchases.

---

## PR #17: fix(messages): keep pages that end a scan and stop re-paginating chunk 0

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/17
- **Upstream issues (related):** datawhores/OF-Scraper#638, #600. Same fix as upstream PR datawhores/OF-Scraper#654.
- **Size:** 2 files, +154 / -15
- **Verdict:** ✅ **Implement, with a one-character fix** for an edge case the PR introduces with `--before`

### The problem, in plain words

On repeat runs, messages are fetched in **chunks** that run at the same time. Each chunk is a slice of the messages already in the database ("cached"), and the API returns pages of messages **older than** a given message ID.

1. **A page was dropped at the end of each chunk.** When a chunk (not the last one) found all its cached messages, it stopped **before yielding** the page that contained them (`messages.py:329-330`). The next chunk starts **below** this chunk's oldest message, so the newer messages on that page were never returned.
2. **Chunk 1 re-scanned chunk 0.** Chunk 1 started at `anchor_id`. Without `--before`, that's the first cached message newer than *now*, which is almost always `None`, meaning "start at the newest". So chunk 1 re-read all of chunk 0. That wasted requests, and happened to hide bug 1 for chunk 0 (but not for later chunks).

### What the PR changes (`data/api/messages.py`)

- `get_tasks`: chunk 0 starts at the anchor only when `--before` is set (otherwise at the newest). **Every later chunk** starts at the previous chunk's oldest message.
- `scrape_messages`: the "page crosses the `--after` date" check runs first and keeps the in-range messages. A finished non-last chunk now **yields its final page** before stopping.
- Adds `test/unit/test_messages_pagination.py` (7 tests).

### What I checked

| Check | Result |
|---|---|
| Both claims | ✅ True (code references above) |
| Applies cleanly on the current tree (PRs #2–#16 in) | ✅ |
| New tests **without** the fix | ❌ 3 failed, 4 passed, as the PR says |
| New tests with the fix | ✅ 7 passed |
| `test/unit` on a clean copy of HEAD + PR | ✅ 46 passed, 4 skipped (without PRs #2–#16) |
| `data/api/messages.py` in the GUI patch? | ✅ Already in `FILES` |

**Full-flow simulation.** The PR's tests check one worker at a time. This simulation uses the real `get_split_array` → `get_tasks` → `process_tasks`, with all chunks running at once against a fake chats API (newest first, `?id=X` returns older messages, 10 per page, 25 cached messages per chunk):

| Scenario | Old: returned / requests | PR (+ fix below): returned / requests |
|---|---|---|
| 100 cached, nothing new | **85/100** / 14 | **100/100** / 12 |
| 100 cached + 7 new | **95/107** / 16 | **107/107** / 13 |
| 300 cached (12 chunks) | **245/300** / 38 | **300/300** / 36 |
| 1 cached message deleted on the server | 85/99 / 14 | 99/99 / 12, and the deleted one is still flagged as deleted |
| `--after 50` | 41/51 / 9 | 51/51 / 7 |
| `--before 70` | 61/70 (+30 outside the range) / 13 | 70/70 / 8 |

The old code **loses roughly 1 in 7 messages** on repeat runs, and the PR fixes that with fewer requests. The lost messages are already in the database, so they mostly matter when their media still needs downloading: a newly unlocked PPV, or a download that failed before.

### Required change (an edge case the PR introduces)

1. **The anchor must be strictly newer than `--before`.** `get_split_array` picks `anchor_id` as the first cached message with `created_at >= before`. Before the PR, chunk 0 never used it. With the PR, chunk 0 **starts** there, and the API returns only messages *older* than the anchor. So a message stamped **exactly** at the `before` time is skipped, even though the range filter right below includes it (`<= before`).
   - Worse, that message is in chunk 0's expected list, so the "ghost" check decides it was deleted on the server and **marks it deleted in the database**. The simulation confirmed it: the PR as submitted marked real message #70 deleted with `--before 70`, and the fixed version marked nothing.
   - **Fix:** `>= before` becomes `> before` in `get_split_array`, with a comment.
   - Extra test: `test_anchor_is_strictly_newer_than_before`. It **fails** on the PR as submitted and passes with the fix.
   - This is rare in practice, since `--before` is usually a date and a message has to land on that exact second. But the result is wrong data in the database, so it's worth the 1-character fix.

### Scratch test results

- PR + fix: `test_messages_pagination.py` 8 passed; `test/unit` 47 passed, 4 skipped (without PRs #2–#16).

### Implementation (done 2026-10-24)

- The maintainer chose "implement with fix".
- Applied from the git root with `git apply -p1`.
- **Required change:** `get_split_array`'s anchor uses `> before`, with a comment explaining why. The file is byte-identical to the version tested in the scratch copy.
- **Extra test:** `test_anchor_is_strictly_newer_than_before`.
- `test/unit`: **139 passed, 4 skipped**.
- Patch rebuilt as `20261024_gui_3_14_7_v382` with `rebuild_patch_zip.py --sync-root`:
  - Still 146 files, and all match the tree.
  - Test-installed into a clean copy (`932e9e1`):
    - The full-flow simulation returns every message in all scenarios, marks nothing wrongly as deleted, and still flags a really deleted message.
    - `test_messages_pagination.py` passes 8/8.
  - After `restore()`, `messages.py` is the pre-patch copy again, and the simulation is back to 85/100.
- Not committed yet.
- **To check it live:** run a normal download that includes **Messages** for a model with a lot of messages you've scraped before. With verbose logging on, the final "Messages" count in the log should match the model's real message count. It should also not be lower than on the last run, unless messages were really deleted.

### Live test by the maintainer (2026-10-24, Linux, `v382`)

- **First try (GUI, normal repeat run):** this only scanned messages since the last scrape. 1 cached message was in range, so only **1 chunk** ran. That's correct (`Final count: 1`), but it doesn't exercise the fix, which only matters with several chunks. The GUI's "Rescrape everything" doesn't help either, because it also turns the cache off (`workflow.py:2646-2648`).
- **Real test (CLI):** `ofscraper -u <model> -o Messages -a download --after 2000`
  - `Messages Cache 263 found`, `Pagination Density: 50 items per task (Total: 263)`, so 6 chunks.
  - `Messages Final count: 256 post(s)`. **Every cached message came back except 7**, and those 7 were flagged as ghosts (2 + 2 + 3).
  - Checked against the database (opened read-only) and the log's "Final ids":
    - **None of the 7 flagged messages was returned by any worker**, so no message was flagged while it still existed.
    - Their positions in the cache are 2, 42, 83, 85, 96, 100 and 120 of 263. They're spread through chunks 0–2, not systematically at chunk edges.
    - 6 of the 7 were paid (PPV) messages from 2023–2025, which creators often unsend.
    - Every other cached message was returned (0 missing without a flag).
  - 0 downloads, because everything was already downloaded.
- **Not possible to compare:** the old code on the same full scan. Earlier runs were incremental, so no older log mentions these IDs.
- **Note:** `messages.is_deleted` is informational only. `get_deleted_messages_ids` (`db/operations_/messages.py:276`) is never called, so a flagged message isn't hidden or skipped, and its files and download record are untouched.

---

## PR #18: fix(daemon): stop on SIGTERM instead of waiting for SIGKILL

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/18
- **Upstream issue:** datawhores/OF-Scraper#644
- **Size:** 3 files, +85 / -1
- **Verdict:** ✅ **Implement, with one fix** for a pre-existing bug that stops the PR from shutting down cleanly
- **Scope:** only the **command-line daemon** (`ofscraper --daemon N` without `--gui`). It does **not** change this repo's Docker image or the GUI. Those always run `ofscraper --gui` (`docker/entrypoint.sh:45`), which goes straight to `launch_gui` (`managers/manager.py:52-65`) and never reaches `daemon_process`. It helps people who run the CLI daemon in **upstream's Docker image** (which `exec`s ofscraper as PID 1), under systemd, or in a terminal.

### The problem, in plain words

1. **SIGTERM ignored as PID 1.** In a container, the main process is PID 1. Linux ignores signals sent to PID 1 unless the process installed a handler, and Python installs none for SIGTERM. So `docker stop` did nothing until Docker gave up and sent SIGKILL. On a normal host, SIGTERM killed the process instantly, with no cleanup.
2. **Ctrl+C hung.** The scheduler thread (`set_schedule`) was a **non-daemon** thread that never ends. After Ctrl+C, the interpreter waited for it forever.

### What the PR changes

- `utils/context/exit.py`: new `sigterm_as_keyboard_interrupt()`, which makes SIGTERM raise `KeyboardInterrupt` (main thread only). `daemon_process` calls it first.
- `commands/scraper/scraper.py`: the scheduler thread becomes `daemon=True`. It only queues jobs, and the main thread runs them.
- Adds `test/unit/test_signals.py` (2 POSIX-only tests).

### What I checked

| Check | Result |
|---|---|
| Applies cleanly on the current tree (PRs #2–#17 in) | ✅ |
| New tests **without** the fix | ❌ 2 failed, as the PR says |
| New tests with the fix | ✅ 2 passed |
| `test/unit` on a clean copy of HEAD + PR | ✅ 41 passed, 4 skipped (without PRs #2–#17) |

**Live signal test.** This runs the **real `daemon_process`** with a 60-minute interval. Only login, model sync and the scrape are stubbed. After the first (stubbed) run, the main thread waits in `jobqueue.get()`, and then a signal is sent. "PID 1" means run inside its own PID namespace (`unshare -rpf --mount-proc`), the same as a container.

| Case | Old code | PR as submitted | PR + fix below |
|---|---|---|---|
| Ctrl+C (SIGINT) in a terminal | ❌ **hangs forever** | exits in 5.3 s, but **rc=1 with a `ValueError`** | ✅ **clean shutdown, rc=0**, 5.3 s |
| SIGTERM on a normal host | killed instantly (rc=143), no cleanup | exits in 5.3 s, rc=1, `ValueError` | ✅ clean, rc=0 |
| SIGTERM as **PID 1** (container) | ❌ **ignored, still running after 15 s** (needs SIGKILL) | exits in 5.3 s, rc=1, `ValueError` | ✅ clean, rc=0 |

The 5.3 s comes from the existing `worker_thread.join(timeout=5)` in the shutdown path. That's inside Docker's default 10 s grace period.

### Required change (a pre-existing bug the PR exposes)

1. **Take `jobqueue.get()` out of the `try`/`finally` in `daemon_process`'s loop.** The loop was:

   ```python
   try:
       job_func = jobqueue.get()   # the daemon waits here between runs
       job_func()
   except Exception: ...
   finally:
       jobqueue.task_done()
   ```

   A signal almost always arrives while the loop waits in `get()`. Then `finally` calls `task_done()` for an item that was never taken, which raises **`ValueError: task_done() called too many times`** and **replaces the `KeyboardInterrupt`**. So shutdown goes through the generic `except Exception` branch and ends with a traceback and exit code 1, instead of the normal Ctrl+C cleanup.
   - With `get()` before the `try`, `task_done()` only runs for a job that was actually taken.
   - New test: `test_daemon_process_shuts_down_cleanly_on_sigterm` (POSIX only, about 6 s). It runs the real `daemon_process` in a child process, sends SIGTERM, and requires "clean shutdown", exit code 0, and no `task_done` error. It **fails on the PR as submitted** and passes with the change.

### Small changes I'd make

2. **Add `utils/context/exit.py` to the patch's `FILES`** (146 → 147). It's the same as pip stock. `commands/scraper/scraper.py` is already in `FILES`.

### Note

- PRs #23–#25 are about **this repo's** Docker setup and GUI shutdown on SIGTERM. They don't overlap with this PR's files.

### Decision (2026-10-24): parked until PRs #23–#25

- The maintainer's point: this repo's Docker image only ever runs the GUI, so a fix for a CLI daemon in Docker needs a way to **run the CLI in Docker** first. Otherwise it should be skipped, because the upstream image isn't this repo's concern.
- **Plan:** when PRs #23–#25 (which also edit `docker/entrypoint.sh` and `docker-compose.yml`) are reviewed:
  - add a **`MODE=gui|cli`** option to the entrypoint and compose.
  - **`gui`** (default) keeps today's behavior: Xvfb, VNC, noVNC and the GUI restart loop.
  - **`cli`** skips the display stack and **`exec`s `ofscraper` with the user's args as PID 1**, so `docker stop`'s SIGTERM goes straight to it.
  - Then apply PR #18 **with the `jobqueue.get()` fix** and its test, and ship `utils/context/exit.py` in the patch.
- The tested versions are saved in the session scratchpad (`parked/pr18_scraper_fix.py`, `parked/pr18_test_signals_fix.py`). They can be regenerated from the PR diff plus the change described above if the scratchpad is gone.
- **Noted for later:** without Docker, patch users running `ofscraper --daemon N` in a terminal still have the Ctrl+C hang (old code), until this lands.

---

## PR #19: fix(download): prevent filename collisions at the final move

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/19
- **Upstream issue:** datawhores/OF-Scraper#635
- **Size:** 8 files, +716 / -21 (about 500 of those lines are tests)
- **Verdict:** ⚠️ **Needs a decision.** It fixes real silent data loss, but changes what happens when the **same** media is downloaded again. It also **conflicts** with PRs #8 and #9, which are already applied, and needs a manual merge.

### The problem, in plain words

If the file-name template gives two **different** media the same name (for example `{date}-{text}.{ext}` for several photos in one post), `moveHelper` kept whichever file was **larger** and **deleted the other**. Both were still counted as downloaded, so the lost one was never retried.

### What the PR changes

- `commands/scraper/actions/utils/paths.py` `moveHelper`:
  - **Reserves** the target name by creating it exclusively (`O_EXCL`), which works across threads and processes, then replaces it with the download.
  - If the name is taken: identical content means "already there" and the download is dropped. **Any other file is never touched**, and the download goes to `name_<media_id>`, then `name_<media_id>_2`, and so on.
  - Handles moves across drives with a staged copy, stale staging files, Windows sharing errors, and case rules.
  - Returns the final path.
- `main_download.py` / `alt_download.py`: use the returned path for dates, the DB record, size, hash, scripts and plugins.
- `commands/metadata/manager.py`: in `--metadata update`, a media's **recorded** file is kept if it still exists, instead of re-pointing the record at the template name.
- New setting `file_options.filename_collision`: `"media_id"` (**default**) or `"overwrite"` (the old behavior). There's also env `OFSC_FILENAME_COLLISION_DEFAULT`.
- Adds `test/unit/test_filename_collisions.py` (28 tests).

### What I checked

| Check | Result |
|---|---|
| Applies on the current tree? | ❌ **No.** `paths.py` conflicts with PR #8 (new `_resolve` helpers right after `moveHelper`). `utils/config/data.py` conflicts with PR #9 (`get_TempDir` now strips quotes). Both can be merged by hand |
| On a clean HEAD copy: new tests without the change | ❌ 28 errors (the new functions don't exist) |
| On a clean HEAD copy: new tests with the change | ✅ 26 passed, 2 skipped (Windows only). `test/unit` 65 passed, 6 skipped |
| Description vs code | ⚠️ The description says each name is "checked against the model's **database**". The code **never reads the database**. It only checks the file system and compares content, and a test says so on purpose ("without interpreting database ownership"). The "stops trusting a file several media were recorded at" claim isn't in the code either: update mode simply prefers the recorded file if it exists |
| Who hits the original bug? | Mostly **command-line users with a template that has no unique token**. The GUI **requires** `{filename}`, `{media_id}` or `{original_filename}` (`gui/utils/config_validation.py:34-37, 138-141`). Truncation keeps the extension and a trailing `_<digits>` and cuts the end of the name, so templates with the token early on (like the maintainer's `{date}-{filename}-{text}.{ext}`) stay unique |

**What `moveHelper` does now** (scratch test, default `media_id` mode):

| Case | Old behavior | PR |
|---|---|---|
| A) **Two different media**, same name | larger kept, **other deleted**, both counted | ✅ both kept (`pic.mp4`, `pic_222.mp4`) |
| B) Same media downloaded again, **identical** bytes | replaced (same content) | ✅ one file |
| C) **Same media** downloaded again, **different** bytes | larger one replaces the old file | ⚠️ old file **stays** at `pic.mp4`, new one saved as **`pic_111.mp4`**, a **duplicate** of the same media |

**When case C happens:** `--force-all` re-downloads where the bytes differ, for example DRM videos after an ffmpeg upgrade or PR #3's `pssh` cleanup, or **re-downloading to replace a broken or truncated file**. In that last case the broken file keeps the normal name and the good copy gets the suffix.

### Options

1. **Implement as is (+ merge the conflicts).** It fixes A by default, and accepts C (duplicates on some re-downloads).
2. **Implement, but default to `"overwrite"`** (old behavior), with `"media_id"` as an opt-in setting. Nothing changes for anyone unless they turn it on. GUI users are already protected from A by the required unique token.
3. **Implement + an ownership check.** Before the move, look up this media's **recorded** file (`prev_download_media_data`). If a candidate name **is this media's own earlier file**, replace it (old "larger wins" rule) instead of adding a suffix. That fixes C while keeping A.
   - It needs care for old data where two media were already recorded at one file. In that case it shouldn't be treated as "own".
   - It's more work: around 30–50 lines plus tests, and it changes the PR's deliberate design.
4. **Skip.** The GUI already prevents the common cause.

### Follow-up question: reposts and "allow duplicates" (2026-10-24)

The maintainer asked how this affects people who keep duplicates of reposted content. Simulated with the real code (the allow-duplicates rename step from `main_download.py:314-318`, then `moveHelper`), old vs PR:

| Repost case | Allow duplicates | Old | PR #19 |
|---|---|---|---|
| Same media in 2 posts, same folder | ON | 2 files (`pic`, `pic(1)`) | same |
| Both copies check the name at the same moment | ON | 1 file | same (a pre-existing race in the rename step) |
| New media ID, identical bytes | ON | 2 files | same |
| New media ID, re-encoded | ON | 2 files | same |
| New media ID, identical bytes | OFF | 1 file | same |
| New media ID, re-encoded | OFF | **1 file** (larger kept, other deleted, both counted) | **2 files** (`pic`, `pic_222`) |

- With allow-duplicates **on**, the app picks `name(1).ext` **before** `moveHelper` (also `alt_download.py:428-433` for DRM). So the PR never sees a clash, and behavior is unchanged.
- With it **off**, identical reposts still end up as one file, as before. Only genuinely different files that share a name now keep both. That's the PR's purpose.
- The maintainer's `dir_format` contains `{post_id}`, so reposts in different posts go to different folders and never clash by name.
- The only remaining concern is case C above: re-downloading the **same** media with different bytes.

### Implementation (done 2026-10-24)

- The maintainer chose **"old behavior by default"**, after checking that reposts and "allow duplicates" aren't affected (see above).
- **Merge:**
  - Applied with `git apply -p1` for the 6 files that apply cleanly.
  - `commands/scraper/actions/utils/paths.py` and `utils/config/data.py` were merged with `git merge-file`: base = HEAD, ours = current tree (PRs #8/#9), theirs = HEAD + PR #19.
  - Both merged **with no conflicts**. PR #8's `_resolve`/`addGlobalDir`/`setDirectoriesDate` code is byte-for-byte unchanged. `get_TempDir` keeps PR #9's quote stripping.
- **Change 1 (default):** `OFSC_FILENAME_COLLISION_DEFAULT` defaults to **`"overwrite"`**, with the comment updated to explain both modes and the re-download caveat of `"media_id"`. With no setting, `moveHelper` behaves exactly like before (larger file wins).
- **Change 2 (metadata):** `_metadata_recorded_file` only applies when `filename_collision` is `"media_id"`. In `"overwrite"` mode, `--metadata update` behaves exactly as before.
- **Extra tests** in `test/unit/test_filename_collisions.py`:
  - `test_default_is_the_old_overwrite_behaviour`
  - `test_metadata_update_ignores_recorded_file_in_overwrite_mode`
- **Small differences that do apply in either mode** (all more accurate than before):
  - The DB **size** is now the size of the file on disk, not the size the API reported.
  - DRM downloads hash the **final** file.
  - Dates, scripts and plugins get the final path. In `"overwrite"` mode that's the same path as before.
- `test/unit`: **167 passed, 6 skipped**.
- Checked end to end with the maintainer's real config (no `filename_collision` key): the mode is `overwrite`, and two media with one name end up as one file holding the larger one, the same as before. `config.json` was **not modified**.
- Patch rebuilt as `20261024_gui_3_14_7_v383` with `rebuild_patch_zip.py --sync-root`:
  - Still 146 files, and all match the tree.
  - Test-installed into a clean copy (`932e9e1`): the tests for PRs #19, #8, #14 and #9 pass on the installed copy (52 passed, 2 Windows-only skipped).
  - `restore()` brings back the pre-patch `paths.py`.
- Not committed yet.
- **To use the new mode:** add `"filename_collision": "media_id"` under `file_options` in `config.json`. It isn't in the GUI's Configuration dialog yet.
- **Note:** when the app next rewrites `config.json` (`auto_update_config`), it adds `"filename_collision": "overwrite"` under `file_options`, which makes the setting visible.

---

## PR #20: fix(daemon): only mark a job done after taking it from the queue

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/20
- **Upstream issue (follow-up):** datawhores/OF-Scraper#644
- **Size:** 4 files, +192 / -2. It **contains all of PR #18** ("Depends on #18") plus one more commit.
- **Verdict:** ✅ **Implement this instead of #18.** It's PR #18 plus exactly the `jobqueue.get()` fix found during the #18 review, with better tests.
- **Status:** ⏸️ **Parked together with #18** (see the #18 decision): to be applied with a Docker CLI mode at PRs #23–#25.

### What it adds on top of PR #18

- `daemon_process`: `job_func = jobqueue.get()` moves **before** the `try`, so `task_done()` only runs for a job that was taken. This is the same fix proposed under PR #18.
- `test/unit/test_daemon_shutdown.py` (3 tests):
  - an idle interrupt shuts down without the `task_done` error,
  - an interrupt **during** a job still marks it done,
  - real SIGTERM while idle (subprocess).
  - They stub `set_schedule`, so they don't wait on the 5 s thread join.
- Its `set_schedule` stub accepts keyword arguments, so it keeps working once PR #21 (SIGUSR1 wake-up, which passes `wakeup=`) is merged.

### What I checked

| Check | Result |
|---|---|
| Applies cleanly on the current tree (PRs #2–#19 in) | ✅ |
| Its 5 tests (`test_daemon_shutdown.py` + `test_signals.py`) without the change | ❌ 5 failed |
| With the change | ✅ 5 passed (about 3 s) |
| `daemon_process` compared with the parked "#18 + fix" | ✅ **Identical code**, comments aside |
| Real `daemon_process` signal checks (same harness as #18) | ✅ Ctrl+C, SIGTERM on host, and SIGTERM as **PID 1**: all **clean shutdowns, rc=0** (5.3 s each) |

### Plan when un-parked

- Apply **PR #20** instead of PR #18 plus the parked files. Its tests replace `test_daemon_process_shuts_down_cleanly_on_sigterm`, which was slower and covered less.
- Ship `utils/context/exit.py` (add it to `FILES`).
- PR #21 (SIGUSR1) builds on this, so review it in the same group.
- **Update after reviewing PR #21:** #21 contains #20 (and so #18). If #21 is accepted, apply **#21 alone** instead of #20.

---

## PR #21: feat(daemon): trigger an idle scraping pass with SIGUSR1

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/21
- **Upstream issue:** datawhores/OF-Scraper#645
- **Size:** 7 files, +494 / -10. It **contains PR #20, and so PR #18** ("Depends on #20").
- **Verdict:** ✅ **Implement.** A small, well-tested feature that also makes shutdown faster.
- **Status:** ⏸️ **Parked with #18/#20.** It only affects the command-line daemon (`ofscraper --daemon N`), so it goes in with the Docker CLI mode at PRs #23–#25.

### What it does, in plain words

While the CLI daemon is **idle** between runs, sending it **SIGUSR1** starts the next scraping run right away, instead of waiting for the interval:
- `kill -USR1 <pid>`
- `docker kill --signal=USR1 <container>` (in a CLI-mode container)

A signal while a run is in progress is ignored. After the triggered run, the normal interval starts again.

### What the PR changes (on top of #20)

- `commands/scraper/utils/schedule.py`:
  - New `DaemonWakeup`. The signal handler only sets a flag, and the scheduler thread does the work.
  - `set_schedule(..., wakeup=)` checks the flag every 0.1 s (it was every `daemon/5` seconds, at least 1 s) and stops when `wakeup.stopped` is set. It cancels the pending scheduled run before queuing the triggered one, so there's no double run.
- `commands/scraper/scraper.py`: installs the handler in `daemon_process`, sets `stopped` on shutdown, and restores the previous handler in `finally`.
- On platforms without SIGUSR1 (Windows): no handler, and nothing changes.
- Tests:
  - `test_daemon_wakeup.py` (5 tests, including a real-process signal lifecycle)
  - the `test_daemon_shutdown.py` / `test_signals.py` from #18/#20
  - a helper, `test/unit/daemon_signal_probe.py`

### What I checked

| Check | Result |
|---|---|
| Applies cleanly on the current tree (PRs #2–#19 in) | ✅ |
| Its daemon tests (wakeup + shutdown + signals) | ✅ 13 passed |
| `test/unit` on a clean copy of HEAD + PR | ✅ 52 passed, 4 skipped |

**Real `daemon_process`, 60-minute interval.** Only login, model sync and the scrape are stubbed; each stubbed run takes 2 s.

| Step | Result |
|---|---|
| USR1 while idle | ✅ run 2 queued right away; log line "SIGUSR1 received while idle" |
| USR1 while run 2 is busy | ✅ ignored (no extra run) |
| Two USR1 back-to-back while idle | ✅ exactly **one** run 3 (the signals merge) |
| SIGTERM afterwards | ✅ clean shutdown, rc=0 |

**Timed runs without signals** (`--daemon 0.1`, i.e. every 6 s): the PR starts runs about 6 s after the previous one ends, the same as the old code. Old code on SIGTERM: rc=143 (killed, no cleanup). PR: clean, rc=0.

**Shutdown speed:** Ctrl+C, SIGTERM on the host, and SIGTERM as **PID 1** all exit cleanly in **0.3 s**, compared with 5.3 s for #18/#20 alone. The scheduler thread now ends by itself, so `worker_thread.join(timeout=5)` doesn't wait.

**Note:** the setup jobs queued before each run (logger reset, start values, model sync, `--before` update) took about 3.4 s in the test. A USR1 sent during that time counts as "busy" and is ignored, which is correct.

### Patch

- `commands/scraper/utils/schedule.py` and `utils/context/exit.py` aren't in `FILES` (both are the same as pip stock). `commands/scraper/scraper.py` is. When un-parked, add both (146 → 148).

### Plan when un-parked

- Apply **PR #21** on its own. It already contains #18 and #20, so their parked versions aren't needed.
- Document SIGUSR1 next to the Docker CLI mode, for example `docker kill --signal=USR1 <container>` to scrape now.

---

## PR #22: feat(recovery): mark old filename collisions for re-download

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/22
- **Upstream issue (follow-up):** datawhores/OF-Scraper#635
- **Size:** 10 files, +1077 / -21. It **contains all of PR #19** ("Depends on #19").
- **Verdict:** ✅ **Implement and ship, but add documentation.** The PR's description promises docs, but none are in the diff, and the tool isn't reachable from any menu.

### What's new compared with #19

Compared file by file: 8 of the 10 files are **exactly PR #19's changes**, which are already applied (with our `overwrite` default). Only 2 files are new:

- `ofscraper/commands/recover_collisions.py` (156 lines): a **standalone, offline** command, not wired into the `ofscraper` CLI or GUI.

  ```
  python -m ofscraper.commands.recover_collisions <model's user_data.db>            # preview (read-only)
  python -m ofscraper.commands.recover_collisions <model's user_data.db> --apply    # reset flags
  python -m ofscraper.commands.recover_collisions <db> --undo <undo file> [--apply] # restore flags
  ```

  - It groups the `medias` rows of one model's database by **recorded path**, or by **file identity** (device + inode) when the file exists. A group with **more than one distinct media** is a suspected loss: the old `moveHelper` kept one file and deleted the others.
  - `--apply` sets `downloaded = 0` for those media in one transaction, so the next normal scrape downloads them again. It doesn't touch files or any other column.
  - Before committing, it writes an **undo file** (`user_data.db.collision-undo-<id>.json`) listing the changed rows. `--undo` restores only rows that are still pending.
  - The same media in two posts is **not** a collision, since the grouping is by distinct media. Relative recorded paths need `--path-root`.
- `test/unit/test_collision_recovery.py`: 11 tests (rollback, undo, case rules, WAL mode, etc.).

### What I checked

| Check | Result |
|---|---|
| New files apply cleanly on the current tree (PRs #2–#19 in) | ✅ |
| `test_collision_recovery.py` | ✅ 20 passed, 2 skipped (Windows only); this includes the #19 tests it re-ships |
| `test/unit` with it | ✅ 187 passed, 8 skipped |

**Preview on copies of the maintainer's 4 model databases** (read-only, on copies, so the real databases weren't touched):

| Model | Groups | Media it would mark |
|---|---|---|
| 113370628, 168143417, 175612582 | 0 | 0 |
| 442464 (<model>) | 3 | 10 |

The 3 groups in one model all come from an **old library location and an old template without a unique token**: recorded under `~/Photos/OnlyFans/<model>/...`, which no longer exists. The current save location is `~/Data/ofscraper`.

- **Group 3 (6 media):** `Profile/Images/header_05-16-2017.jpeg`, with **3 different recorded sizes** (245,862 ×3, 3,342,761 ×2, 240,556). So **3 different header pictures** shared one name, and at least 2 were lost. This is a real collision.
- **Groups 1 and 2 (2 media each):** `Posts/Images/09-11-2017-01_PM_5.jpeg` and `..._3.jpeg`. Two media IDs in different posts on the same day, with **identical recorded sizes**. Almost certainly the **same picture posted twice**, so nothing was lost. Recovery would re-download them harmlessly.

### Things to know (for the docs)

- **It only helps if the filename template now gives those media different names.** That means a unique token (`{filename}`, `{media_id}`, `{original_filename}`), or `filename_collision: "media_id"`. Otherwise the re-download collides the same way again. The maintainer's current template contains `{filename}`, so it's fine.
- **False positives are possible:**
  - identical reposts (as in groups 1 and 2), which only cost a re-download;
  - **hard-linked** files: if a dedup tool replaced duplicates with hard links, different media really do share one file identity. Always look at the preview first.
- It works on **one model's database at a time**: `~/.config/ofscraper/<profile>/.data/<model_id>/user_data.db`.
- Run it while ofscraper **isn't running**. `--apply` takes a write lock.
- For a uv-tool install, use that install's Python, for example `~/.local/share/uv/tools/ofscraper/bin/python -m ofscraper.commands.recover_collisions ...`.

### Small changes I'd make

1. **Ship it:** add `commands/recover_collisions.py` to `FILES` (146 → 147).
2. **Document it** in `gui/help/GUI_HELP.md`: what it does, the preview, apply and undo commands, where the databases are, and the cautions above.

### Implementation (done 2026-10-24)

- The maintainer chose "ship + document".
- Only the 2 new files were applied (`git apply -p1 --include`). The other 8 are PR #19, which was already merged (with the `overwrite` default).
- `commands/recover_collisions.py` added to `FILES` (after `commands/metadata/manager.py`). `FILE_COUNT` is now 147.
- **Docs** (`gui/help/GUI_HELP.md`):
  - New **Troubleshooting → "Recovering files lost to old filename collisions"** section (anchor `troubleshooting-collisions`, also in the TOC). It covers: close OF-Scraper first, where the per-model databases are, preview / apply / undo commands, using the same Python as the install (uv path on Linux), the template must now give distinct names, and checking the preview for false positives (identical reposts, hard links, `--path-root`).
  - New **File Options** entry for `file_options.filename_collision` (config.json only): `overwrite` (default) vs `media_id`, and the re-download caveat. PR #19 had left this undocumented.
- **Documented commands tested** on a copy of the maintainer's <model> database:
  - preview: 10 to mark, nothing changed;
  - `--apply`: 10 rows reset, undo file written;
  - `--undo` preview: 10 to restore;
  - `--undo --apply`: all 10 restored.
  - The real database was never opened for writing (its modification time is unchanged), and the copies were deleted afterwards.
- `test/unit`: **187 passed, 8 skipped**.
- Patch rebuilt as `20261024_gui_3_14_7_v384` with `rebuild_patch_zip.py --sync-root`:
  - All 147 payload files match the tree.
  - Test-installed into a clean copy (`932e9e1`): `python -m ofscraper.commands.recover_collisions --help` works from the installed copy, and `test_collision_recovery.py` passes (20 passed, 2 skipped).
- Not committed yet.
- **Optional for the maintainer:** <model> has 3 lost profile headers (plus 2 harmless repost pairs). After installing `v384`, close OF-Scraper and run the preview, then `--apply`, on `~/.config/ofscraper/main_profile/.data/442464/user_data.db`. The next scrape of <model> downloads those 10 images into the current library.

### Live run by the maintainer (2026-10-24, Linux, `v384`)

- Preview: 3 groups, `media_to_mark: 10`. `--apply`: `rows_marked: 10`, undo file written next to the database.
- Then `ofscraper -u <model> -o Timeline,Profile -a download --after 2000`: **4 downloads, 0 failed** (3.29 MB).
  - All **4 Timeline images** came back into the current library (`~/Data/ofscraper/<model>/Free/Posts/<post_id>/`), with distinct names from the current template.
  - Content check (sha256): they are **2 identical pairs**. `PM_3` in posts 542362 and 542438 is the same picture, and so is `PM_5` in posts 542362 and 542446. So groups 1 and 2 really were the **same picture posted twice**, as the identical recorded sizes suggested. Nothing had been lost there; the tool just re-downloaded them.
  - The **6 profile header** media were **not** re-downloaded. The Profile area only offers the model's **current** avatar and header, and the 3 old 2017 headers are no longer on the site. They stay `downloaded = 0`, which does no harm. This was predicted before the run.
- **Takeaway for the docs (added in `v385`):** recovery can only bring back media the site still offers. Old profile pictures, deleted posts and expired content can't come back. The preview helps tell real losses (different sizes) from reposts (identical sizes).

---

## PR #23: fix(docker): copy the GUI patches from the repo root

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/23
- **Size:** 2 files (`docker/Dockerfile`, `docker-compose.yml`), +5 / -6
- **Verdict:** ✅ **Implement as is.** Docker files aren't part of the GUI patch, so no patch rebuild is needed.

### The problem, in plain words

The Dockerfile copies each version's patch from its version folder (`docker/Dockerfile:60-63`):
`COPY OF-Scraper-3.12.9/patch_ofscraper_3.12.9_gui.py ./`, and the same for 3.14.3, 3.14.5 and 3.14.7.

But `OF-Scraper-3.12.9/`, `3.14.3/` and `3.14.5/` **don't contain** a patch file, not in git and not on the maintainer's disk. Only the **repo root** has all four, plus `OF-Scraper-3.14.7/` has a copy. So `docker compose build` fails on **every** checkout, including the maintainer's.

### What the PR changes

- `COPY patch_ofscraper_*_gui.py ./`, copying all four from the repo root (the build context is `.`, per `docker-compose.yml`).
- Comments in the Dockerfile and compose file now say the patches live in the repo root.

### What I checked

| Check | Result |
|---|---|
| Patch files tracked in git | root: 3.12.9, 3.14.3, 3.14.5, 3.14.7; plus `OF-Scraper-3.14.7/patch_ofscraper_3.14.7_gui.py`. The other version folders have none |
| **Old COPY lines** (`FROM scratch` test image, build context = the git-tracked files, like a fresh clone) | ❌ build fails: `"/OF-Scraper-3.12.9/patch_ofscraper_3.12.9_gui.py": not found` |
| **New COPY line**, same context | ✅ builds, and copies all 4 files, each identical to the repo-root file |
| Which copy is used | The **root** copy. That's the one `rebuild_patch_zip.py --sync-root` keeps up to date, so Docker builds always get the latest patch |

### Note

- A full image build (Ubuntu + Qt + pip) wasn't run here. Only the changed `COPY` step was tested. The PR author reports a full build and a GUI reachable over noVNC.
- **Process note (my mistake):** after the test I ran `docker builder prune -f --filter until=10m`, which removes build cache **older** than 10 minutes, not newer. Images, containers and volumes aren't affected by prune and were checked to be intact (`hello-world`, `ghcr.io/dockur/windows:5.14`, container `WinBoat`). Some older **build cache** may have been removed, which only makes a future `docker build` slower. There was no ofscraper image on this machine.

### Part of the Docker group

- PRs **#24** (entrypoint: pass `docker stop` to the GUI) and **#25** (GUI: quit cleanly on SIGTERM) come next.
- The planned **Docker CLI mode** (`MODE=gui|cli`) and the parked daemon PRs (#18/#20 → **#21**) are also planned here.

### Implementation (done 2026-10-24)

- The maintainer chose "apply now".
- Applied from the git root with `git apply -p1`, unchanged: `docker/Dockerfile` (one `COPY patch_ofscraper_*_gui.py ./`, updated comment) and `docker-compose.yml` (comment).
- No patch rebuild, because these files aren't in the GUI patch. The patch stays at `v385`.
- Not committed yet.
- **To try it:** `docker compose build` from the repo root should now get past the COPY step, and log `Applied GUI patch: 20261024_gui_3_14_7_v385`.

---

## PR #24: fix(docker): pass docker stop on to the GUI instead of waiting for SIGKILL

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/24
- **Size:** 2 files (`docker/entrypoint.sh`, `docker-compose.yml`), +43 / -7
- **Verdict:** ✅ **Implement, with a small fix** for a stop that arrives during startup. Docker files only, so no patch rebuild.

### The problem, in plain words

- `docker/entrypoint.sh` is **PID 1** in the container, and bash as PID 1 **ignores SIGTERM** unless it has a `trap`. So `docker stop` did nothing: the restart loop kept going, the GUI never got a signal, and after the grace period Docker **SIGKILLed** everything, possibly mid-download or mid-database-write.
- The restart log always said `code 0`, because `EXIT_CODE=$?` ran after `wait ... || true`.

### What the PR changes

- `trap stop_container TERM INT`: sets `STOPPING=1` and forwards SIGTERM to the GUI. The loop keeps `wait`ing until the GUI has really exited, then **exits instead of restarting**.
- The xdotool "maximize window" step runs in the background, because `--sync` could block forever if the GUI dies first.
- Logs the GUI's **real** exit code.
- The restart pause is interruptible (`sleep &` + `wait`).
- `docker-compose.yml`: `stop_grace_period: 30s` (the default is 10 s), so a cancelling scrape has time to finish.

### What I checked

Tested the **real `entrypoint.sh`** running as **PID 1** (`unshare -rpfm --mount-proc`), with stand-ins for Xvfb, fluxbox, x11vnc, websockify, xdotool and the GUI. The fake GUI either **dies on SIGTERM** (like the GUI today), **exits cleanly** (like after PR #25), or **crashes** (exit 3, to test restarts). In the test copies only, the X lock-file cleanup line was pointed at the test folder, so the real `/tmp` wasn't touched.

| Case | Old entrypoint | PR as submitted | PR + fix |
|---|---|---|---|
| `docker stop` with a running GUI that dies on SIGTERM | ❌ **ignored**, still running after 15 s (Docker would SIGKILL) | ✅ 0.3 s, logged `code 143` | ✅ same |
| `docker stop`, GUI exits cleanly | ❌ ignored | ✅ 0.5 s, `code 0` | ✅ same |
| GUI crashed (exit 3), stop during the restart pause | (n/a) | ✅ 0.3 s, real `code 3` logged | ✅ same |
| **Stop during startup** (before the GUI is launched) | ❌ ignored | ❌ **hangs**: the trap had no PID, then the loop **started the GUI anyway** and waited on it | ✅ stops without starting the GUI (2.3 s at 0.5 s in; 0.3 s at ~2.5 s in) |

These match the PR author's container measurements (main: 30 s + SIGKILL; PR: 0.3 s / exit 143; PR + #25: about 0.5 s / exit 0).

### Required change

1. **Handle a stop that arrives before the GUI exists.** In the restart loop:
   - **before** launching: `if STOPPING=1 → log "stop requested before the GUI started" and exit 0`;
   - **right after** `GUI_PID=$!`: `if STOPPING=1 → kill -TERM "$GUI_PID"`. This covers a signal that lands between the check and the launch.

### Notes

- On its own, PR #24 delivers SIGTERM to the GUI, but the GUI then dies through Python's default action (instant, no cleanup, exit 143). **PR #25** makes the GUI cancel the scrape and exit cleanly.
- The planned **Docker CLI mode** will build on this entrypoint: `MODE=cli` would skip the display stack and the restart loop.

### Implementation (done 2026-10-24)

- The maintainer chose "implement with fix".
- Applied from the git root with `git apply -p1`: `docker/entrypoint.sh` and `docker-compose.yml` (`stop_grace_period: 30s`).
- **Required change:** in the restart loop, exit before launching if a stop was already requested, and forward SIGTERM right after `GUI_PID=$!` if one arrived during the launch. `bash -n` is clean.
- The repo's `entrypoint.sh` is identical to the tested version, apart from the test-only `/tmp` lock-file line.
- No patch rebuild (the patch stays at `v385`). Not committed yet.
- **To try it in Docker:** `docker compose up -d --build`, then `docker compose stop`. It should return within a second or two instead of 10–30 s. `logging/gui-docker.log` shows "stop requested" and "ofscraper exited (code 143) — stopping" (code 0 once PR #25 is in).

---

## PR #25: fix(gui): cancel the scrape and quit cleanly on SIGTERM

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/25
- **Size:** 3 files, +203 / -0
- **Verdict:** ✅ **Implement as is**, and ship the new `gui/utils/shutdown.py` in the patch. It pairs with PR #24 (Docker passes the signal on), but also helps `kill` and systemd outside Docker.

### The problem, in plain words

The GUI had no SIGTERM handler, so Python's default action killed it **instantly** (exit 143). A running scrape was cut off mid-download or mid-database-write. With PR #24 in place, `docker stop` now reaches the GUI, so this is what happens next.

### What the PR changes

- New `ofscraper/gui/utils/shutdown.py`, installed from `launch_gui` (`gui/app.py`) once the main window exists. On SIGTERM it:
  1. hands off to the Qt main thread (`QTimer.singleShot(0, ...)`), without touching Qt inside the signal handler;
  2. if a scrape is running, calls the **same `GUIWorkflow._on_cancel_scrape`** as the Cancel button (a cooperative cancel, then the existing forced stop after 5 s), and sets `_daemon_stop`;
  3. waits up to **20 s** for the scraper thread;
  4. closes all windows like a user would (`closeAllWindows()`), with `app.quit()` as a fallback 2 s later. The author found that quitting the loop with the window still open crashed in Qt teardown.
- A **second** SIGTERM closes immediately.
- A 250 ms no-op timer keeps the handler responsive while Qt's C++ event loop runs.
- Adds `test/unit/test_gui_shutdown.py` (3 tests, POSIX only, skipped without PyQt6).

### What I checked

| Check | Result |
|---|---|
| Applies cleanly on the current tree | ✅ |
| Attributes it relies on exist | ✅ `MainWindow.workflow` (`main_window.py:88`), `GUIWorkflow._scraper_thread`, `_daemon_stop`, `_on_cancel_scrape` (`workflow.py:1999, 2006, 2175`) |
| Could closing the window be blocked? | No. `MainWindow` has **no `closeEvent`** (no "quit while scraping?" dialog), and nothing calls `setQuitOnLastWindowClosed(False)`, so closing all windows ends the app |
| Timing | The forced stop comes after **5 s** (`_CANCEL_FORCE_GRACE_SECONDS`). The PR waits up to 20 s, plus a 2 s fallback. The scraper thread is a **daemon** thread (it can't hold the process at exit). Docker's new `stop_grace_period` is **30 s**. All of these fit |
| Its 3 tests, with real **PyQt6 6.11** (installed in the scratch venv only), offscreen | ✅ 3 passed |
| `test/unit` with PyQt6 available | ✅ 190 passed, 8 skipped |

**End to end, beyond the PR's tests.** Its tests use a stand-in workflow and a non-GUI `QCoreApplication`. This run uses a **real `QApplication`, a real window and the real `GUIWorkflow`**, with a fake scraper thread, and a real SIGTERM from outside:

| Scraper behavior | Result |
|---|---|
| Honors the real cancel event (`_gui_cancel_event`) | ✅ finishes its current item, window closed, **exit 0 in 1.3 s** |
| Ignores cancel (stuck) | ✅ the existing forced stop injects `KeyboardInterrupt` after 5 s, window closed, **exit 0 in 5.8 s** |

No segfault in either case. Without the PR, the GUI dies instantly with 143. That's the entrypoint test's "dies on SIGTERM" case under PR #24.

### Related bug (from the system analysis, not this PR)

- `ensure_gui_host()` (`gui/utils/host_callbacks.py:151`) always raises `UnboundLocalError`, because of a missing `global`. `_on_cancel_scrape` catches it and falls back to a plain status message, so **cancel still works** through `_gui_cancel_event` and the forced stop.
- But the scraper's **between-actions** cancel check (`commands/scraper/scraper.py:133`) never runs, and the "cancelling" phase signal is never sent. Fixing that one line would make Cancel, and so SIGTERM, a bit more cooperative.

### Small changes I'd make

1. **Add `gui/utils/shutdown.py` to the patch's `FILES`** (147 → 148). `gui/app.py` is already in `FILES`.

### Implementation (done 2026-10-24)

- The maintainer chose "implement + ship", **and** to fix the `ensure_gui_host()` bug in the same rebuild.
- PR #25 applied from the git root with `git apply -p1`, unchanged. `gui/utils/shutdown.py` added to `FILES` (after `gui/utils/host_callbacks.py`). `FILE_COUNT` is now 148.
- **`ensure_gui_host()` fix** (`gui/utils/host_callbacks.py:152`): added `global _current_host`. New `test/unit/test_host_callbacks.py` (2 tests). Both **fail without the fix** with `UnboundLocalError`.
  - **What it actually changes**, after checking every caller:
    - In GUI mode, `GUIScraperManager` **overrides** `_execute_user_action` (`gui/utils/workflow.py:1617-1633`). So `scraper.py:124-191` (the between-actions cancel check and the per-model events) only runs in the **CLI**, where the host is the no-op one anyway. There's no change there, and no doubled badge events (the GUI has its own `_emit_model_badge_*`).
    - The GUI's own host calls now work:
      - **status messages** that were silently missing: "Scraping complete", "Run #N complete. Next in …", "Daemon stopped", "Scraping cancelled", "Processing <model>…";
      - **phase** updates: running, cancelling, complete, daemon, ready.
    - Today, `get_host()` returned the no-op host without raising, so even the `except` fallbacks never ran.
  - **Consistency:** the new phases match what `StatusStrip._on_scraping_finished` already does (complete / daemon / cancelling → ready). The cancel flag is cleared when each scrape starts (`workflow.py:2403`), so a leftover Cancel can't cancel the next run.
  - **Qt check:** `GUIWorkflow._on_cancel_scrape()` now emits phase `cancelling` plus the status. Before the fix, only the fallback status was emitted.
- `test/unit` (with PyQt6 in the scratch venv): **192 passed, 8 skipped**.
- Patch rebuilt as `20261024_gui_3_14_7_v386` with `rebuild_patch_zip.py --sync-root`:
  - All 148 payload files match the tree.
  - Test-installed into a clean copy (`932e9e1`): `test_gui_shutdown.py` + `test_host_callbacks.py` pass 5/5 on the installed copy, and the real-window SIGTERM run gives a clean exit, **rc=0 in 1.0 s**.
- Not committed yet.
- **To try it:**
  - **Outside Docker:** start a scrape in the GUI, then `kill <gui pid>` (SIGTERM). The log shows "Stop requested — cancelling the current scrape before exit", and the app closes within a few seconds.
  - **In Docker** (with PR #24): `docker compose stop`. `gui-docker.log` shows "ofscraper exited (code 0) — stopping".
  - Also visible now: the status bar shows "Scraping complete", and when you press Cancel the phase badge switches to **Cancelling**.

---

## Docker CLI mode + PR #21 (with #18 and #20) — done 2026-10-24

Decided at PR #18: a CLI-daemon fix only makes sense for Docker if the image can **run the CLI**. Built after PRs #23–#25.

### PR #21 (contains #18 and #20)

- Applied from the git root with `git apply -p1`, unchanged: `commands/scraper/scraper.py`, `commands/scraper/utils/schedule.py`, `utils/context/exit.py`, plus tests (`test_daemon_wakeup.py`, `test_daemon_shutdown.py`, `test_signals.py`, `daemon_signal_probe.py`).
- `commands/scraper/utils/schedule.py` and `utils/context/exit.py` added to `FILES` (148 → 150). `scraper.py` was already in it.
- The parked `pr18_*` files aren't needed. #21 already has the `jobqueue.get()` fix, with better tests.
- **On the tree:** the 13 daemon tests pass. Real `daemon_process`: Ctrl+C on the host and SIGTERM as PID 1 both shut down cleanly (rc=0, 0.3–0.5 s). SIGUSR1 while idle starts a run, and while busy it's ignored.

### Docker `MODE=cli` (new; `docker/entrypoint.sh`, `docker-compose.yml`)

- **`MODE=gui`** (default): unchanged. Xvfb, fluxbox, x11vnc, noVNC, then the GUI restart loop (with PR #24's stop handling).
- **`MODE=cli`**: after the shared setup (trap, config folders), skips the whole display stack and runs `python -m ofscraper` with:
  - the **container command arguments** (`docker compose run --rm ... ofscraper-gui <args>`), or else **`CLI_ARGS`** (split into words like `GUI_ARGS`).
  - **Not a terminal** (`up -d`): the CLI runs as a child of the entrypoint (PID 1).
    - The traps forward **SIGTERM** (`docker stop`) and **SIGUSR1** (`docker kill --signal=USR1`: run now).
    - A stop that arrives before the CLI starts exits without starting it.
    - The container exits with the **CLI's exit code**.
  - **A terminal** (`docker compose run`): `exec`s the CLI in the foreground, so the interactive menus can read the terminal.
  - **No arguments and no terminal:** a clear message, exit code 2.
- `docker-compose.yml`: `MODE=gui` and `CLI_ARGS=` with comments: meant for `--daemon` runs, because `restart: unless-stopped` would restart a one-shot run, so use `docker compose run --rm` for those. Also how to stop and how to trigger a run with USR1. The YAML parses, and `docker compose config` is OK.
- **Docs:**
  - README → Docker → new **"Running the CLI instead of the GUI (MODE=cli)"** section (plus a TOC entry, and the two entrypoint description lines updated);
  - `GUI_HELP.md` → Docker notes: `docker compose stop` is now clean, and a `MODE=cli` bullet.

### Tests (real `entrypoint.sh` as PID 1 via `unshare`, stand-ins for the display tools; the real `/tmp` untouched)

| Case | Result |
|---|---|
| `MODE=cli`, `CLI_ARGS` daemon (real `daemon_process`, 60 min) → USR1 → `docker stop` | Arguments arrive exactly. **USR1 started run 2**, which with a 60-min interval only the signal can do. Stop: **clean, exit 0, 0.3 s** |
| Arguments as the container command | Used instead of `CLI_ARGS` |
| One-shot run that exits 5 | Container exits **5** |
| No arguments, no terminal | The message, exit **2** |
| Interactive (a real pty via `script`) | Runs in the foreground, `tty=yes` |
| `MODE` unset / `MODE=gui` | Unchanged: normal stop 0.3 s (code 143 with a GUI that dies; 0.5 s / code 0 with a clean GUI); a stop during startup exits without starting the GUI |

- **Patch** rebuilt as `20261024_gui_3_14_7_v387` (150 files, all matching the tree).
  - **Installed copy** (`932e9e1` + `v387`): all 13 daemon tests pass. The real daemon through the CLI-mode entrypoint: USR1 run, then a **clean stop, exit 0, 0.3 s**. `restore()` works.
  - Note: the first run of the installed-copy tests gave 2 failures. The cause was my test-folder layout: the probe script is found at `<root>/test/unit/`. With the right layout, all 13 pass.
- `test/unit`: **205 passed, 8 skipped**.
- **Not done:** a full Docker image build and run. Optional, and slow.
- Not committed yet.

---

## PR #26: test: repair the legacy suite and retire tests for removed code

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/26
- **Size:** 38 files, +3553 / -3181. Tests, `pyproject.toml` and `uv.lock` only; **nothing ships in the GUI patch**.
- **Verdict:** ✅ **Implement, with a small fix:** isolate the tests from the real config folder.

### The problem, in plain words

A plain `pytest` (from `OF-Scraper-3.14.7/`) stopped with **collection errors**. All the older test modules outside `test/unit` import modules that moved or no longer exist, and they use `pytest-check`, which wasn't in the `test` extra. On our current tree that's **45 errors**; the PR says 23 on `main`. Separately, `uv.lock` was out of date with `pyproject.toml` (`uv lock --check` fails, and the `gui` extra was never locked; finding #5 of the system analysis).

### What the PR changes

- **Repairs** the older tests in place: today's import paths, defaults read through `of_env.getattr`, `config=` passed as a keyword. A new `test/conftest.py` clears `sys.argv` and imports the entry module first, for every test.
- **Moves** 175 tests for code that no longer exists into `test/legacy/`, with a `README.md` listing each one and why. `addopts` gains `--ignore=test/legacy`.
- `pyproject.toml`: adds `pytest-check~=2.3` to the `test` extra. `uv.lock` re-locked.
- ⚠️ **Not in the PR's file list:** the diff also **deletes 6 committed `.pyc` files** in `Available Plugins/live_stream_monitor/__pycache__/`. Their `.py` sources are tracked next to them, so they're just leftover build output. Harmless cleanup, but unrelated. They're binary deletions, so `git apply` can't apply them (a `git rm` would).

### What I checked

| Check | Result |
|---|---|
| Applies on the current tree (test and packaging files) | ✅. The `.pyc` deletions don't apply as a patch (see above) |
| Plain `pytest`, current tree | ❌ **45 collection errors** |
| Plain `pytest` with the PR | **438 passed, 4 failed**, 8 skipped |
| The 4 failures | `test/general/config_test.py`: `test_dirformat`, `test_fileformat`, `test_textlength`, `test_ffmpeg`. They call getters with `config=None`, which reads **the real `~/.config/ofscraper/config.json` of whoever runs the tests**. The maintainer's config has a custom directory format, file format, Text Length 10 and an ffmpeg path, so the tests fail. They'd pass on a machine with the default config |
| Did the runs change the maintainer's config? | **No.** `config.json` was last changed at 04:18, hours before (most likely the app adding `filename_collision` on first run of `v383`+). It's still the maintainer's settings |
| `test/unit` with the PR | ✅ 205 passed, 8 skipped (unchanged by the new shared conftest) |
| `uv lock --check`: current lock / PR lock | ❌ out of date / ✅ up to date |
| What the PR's lock changes | **Only additions:** `pyqt6`, `pyqt6-qt6`, `pyqt6-sip`, `pyqt6-webengine`, `pyqt6-webengine-qt6`, `pytest-check`. No version changes and no removals |

### Required change

1. **Run the tests against a throwaway home folder.** The config is found at `Path.home() / ".config/ofscraper"` unless `--config` is given (`utils/paths/common.py:55-77`). In `test/conftest.py`, before importing ofscraper, set `HOME` (and `USERPROFILE` on Windows) to a `tempfile.mkdtemp()` folder that's removed at exit.
   - Tests then always see the default config, and they **can never read or rewrite** a developer's real config, profiles or databases.
   - With this: plain `pytest` gives **442 passed, 8 skipped, 0 failed**, and `test/unit` gives 205 passed. The real `config.json` was confirmed untouched, and the temporary folders cleaned up.

### Optional

2. Also remove the 6 stray `.pyc` files (`git rm` of `Available Plugins/live_stream_monitor/__pycache__/`), and maybe add a `.gitignore` with `__pycache__/`.

### Implementation (done 2026-10-24)

- The maintainer chose "implement with fix" and "remove the `.pyc` files".
- Applied the test, `pyproject.toml` and `uv.lock` changes from the git root (`git apply -p1 --include='OF-Scraper-3.14.7/*'`).
- **Required change:** `test/conftest.py` sets `HOME` / `USERPROFILE` to a temporary folder (removed at exit) before importing ofscraper.
- **`.pyc` cleanup:**
  - Removed the 6 compiled files in `Available Plugins/live_stream_monitor/__pycache__/` (plain `rm`, not staged; the `.py` sources stay). They were the only tracked bytecode in the repo.
  - Added a **root `.gitignore`** with `__pycache__/` and `*.pyc` (there was none at the root).
- **Results on the real tree:**
  - plain `pytest`: **442 passed, 8 skipped** (was 45 collection errors);
  - `test/unit`: 205 passed, 8 skipped;
  - `uv lock --check`: ✅;
  - the maintainer's `config.json` was untouched.
- No patch rebuild (nothing here ships; the patch stays at `v387`). Not committed yet.
- System analysis findings now resolved: #5 (stale `uv.lock` / missing `gui` extra) and #7 ("legacy suites have 23 collection errors").


## PR #27: ci: run the tests in the OF-Scraper-3.14.7 project with uv

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/27
- **Size:** 39 files, +3570 / -3190. But **38 of the 39 files are PR #26** (it's built on top of it). Compared file by file, those 38 are identical to #26, which is already applied.
- **Only new file:** `.github/workflows/codecov.yml`. Nothing ships in the GUI patch.
- **Verdict:** ✅ **Implement** (just the workflow file), with one optional one-word change.

### The problem, in plain words

The `codecov` GitHub workflow has failed on every push since May without running a single test. It runs `poetry install` at the repo root, but there's no `pyproject.toml` there: the project lives in `OF-Scraper-3.14.7/` and uses uv, not Poetry. It also measured coverage of `src`, a folder that doesn't exist (system analysis, open item).

### What the PR changes (workflow only)

- Runs every step from `OF-Scraper-3.14.7/`.
- Installs uv and Python with `astral-sh/setup-uv@v6` (instead of setup-python + Poetry).
- Tests **Python 3.11 and 3.12** (a matrix; one failing doesn't cancel the other). These are the versions the README supports.
- `uv sync --frozen --extra test`, then `uv run --frozen pytest --cov=ofscraper ...`.
- Codecov upload points at `OF-Scraper-3.14.7/coverage.xml` and doesn't fail the job (it may need a `CODECOV_TOKEN` secret).

### What I checked

| Check | Result |
|---|---|
| The 38 shared files vs #26 | Identical, already in the tree |
| The job's exact steps on a clean copy of our tree, **Python 3.11.15** | ✅ `uv sync` OK; **439 passed, 9 skipped**; `coverage.xml` written (≈17% line coverage) |
| Same, **Python 3.12.13** | ✅ **439 passed, 9 skipped**; `coverage.xml` written |
| Why 439/9 and not 442/8 like a local run | CI installs only the `test` extra, not `gui`, so `test_gui_shutdown.py` (3 tests) is skipped: "could not import PyQt6". Expected |
| Upload path | `uses:` steps run from the repo root (the `working-directory` default only applies to `run:` steps), so `OF-Scraper-3.14.7/coverage.xml` is right |
| The real config | Not used: the #26 conftest points `HOME` at a temp folder. The `mkdir /home/runner/.config/...` step is now unneeded but harmless |
| Overlap with #28 | #28 doesn't touch the workflow. It changes `pyproject.toml` / `uv.lock`; the CI would then test those (3.13+ could be added to the matrix later) |
| On GitHub itself | Not run (can't from here). Runs on the next push / PR once committed |

### Optional change

1. **`--frozen` → `--locked`** in the `uv sync` step. `--frozen` installs from `uv.lock` without checking it still matches `pyproject.toml`. That's how the lock went stale before (fixed in #26). `--locked` fails the job with "The lockfile needs to be updated" instead.
   - Tested on the scratch copy: `--locked` passes on the current lock; after adding a dependency to `pyproject.toml` without re-locking, `--locked` fails while `--frozen` still passes (exit 0).

### Notes (not blockers)

- `codecov/codecov-action@v3` is old (newer versions are v4/v5, which want a token). With `fail_ci_if_error: false`, an upload problem only shows a warning; the tests still decide pass/fail.
- GUI tests could also run in CI with `--extra gui` plus `QT_QPA_PLATFORM=offscreen`, but PyQt6 on the runner may need extra system libraries. Left out.

### Implementation (done 2026-10-24)

- The maintainer chose "apply with `--locked`".
- Applied only the `.github/workflows/codecov.yml` part of the PR (from the git root, `git apply -p1`); the other 38 files are #26, already in.
- **Change:** `uv sync --frozen --extra test` → `uv sync --locked --extra test`, so CI fails if `uv.lock` is out of date. The test step keeps `uv run --frozen` (the lock was already checked one step before).
- Checks: the workflow parses as YAML; `uv lock --check` passes on the real tree; the job's steps passed on Python 3.11 and 3.12 (439 passed, 9 skipped, `coverage.xml` written).
- Not run on GitHub yet (it runs on the next push / PR). No patch rebuild (still `v387`). Not committed yet.
- System analysis item resolved: "`codecov.yml` uses Poetry and `--cov=src`".

## PR #28: chore: support Python 3.15 for source installs

- **Link:** https://github.com/cjb900/OF-Scraper-GUI/pull/28
- **Size:** 24 files, +2081 / -685 (most of it `uv.lock`).
- **Verdict:** ✅ **Implement, with 2 required changes:** re-lock on top of #26, and add 2 files to the patch.

### The problem, in plain words

Installed from this repo's source, the project only allows Python 3.11–3.13 (`requires-python <3.14`), and in practice only 3.11/3.12 work: some pinned packages have no wheels for newer Pythons. This machine's own Python is 3.14.7. Newer Pythons also warn about (and will later reject) some code patterns used here.

**What it doesn't change:** the patch install (PyPI's ofscraper 3.14.7 keeps its own `<3.14` limit and old pins) and the Docker image (`pip install ofscraper==3.14.7` on Python 3.12). The README's "3.11 or 3.12" rule is about those, so it stays true.

### What the PR changes

- **Dependencies** (`pyproject.toml`): `requires-python` → `<3.16`; lxml 5.1 → 6.1, pywidevine 1.8 → 1.9 (with protobuf 4 → 6), pycryptodome 3.20 → 3.23, uvloop 0.21 → 0.23, coverage 7.4 → 7.15. `async-property` is removed.
  - The lock also moves some indirect packages: **aiohttp 3.13 → 3.14, multidict 6 → 7**, yarl, propcache, and a few small ones.
- **Code:**
  - 15 invalid escape sequences fixed in 8 files (`"\["` → `"\\["`, etc.). The strings' values don't change.
  - `cert.py`: drops the deprecated `ssl.OP_NO_*` flags (`minimum_version` already does that job). The TLS handshake stays the same.
  - `async-property` is replaced by an in-repo `utils/async_cached_property.py` with the same behaviour.
  - New `system.new_event_loop()` (uvloop on Linux), used where the CLI makes event loops. The uvloop *policy* is set only below 3.14.
  - `_httpx_funct`: `build_request()` + `send()` instead of `request()` (same thing, minus a deprecation warning for per-request cookies).
  - Leaks: `cache.get()` closes the worker thread's diskcache connection; shutdown closes log file handlers.
- **Tests:** 4 new files in `test/unit` (17 tests).

### What I checked

| Check | Result |
|---|---|
| Applies on our tree | ✅ all code, test and `pyproject.toml` hunks. ❌ `uv.lock` conflicts with #26's lock (the PR says so) |
| Re-lock | Took the PR's `uv.lock` and ran `uv lock` with our `pyproject.toml`: **only `pytest-check` is added**, nothing else moves. `uv lock --check` ✅ |
| Full suite, CI steps (`uv sync --locked --extra test`, `pytest`), **Python 3.11.15** | ✅ **456 passed, 9 skipped** |
| Same, **3.12.13** | ✅ 456 passed, 9 skipped |
| Same, **3.13.14** (the PR didn't test it) | ✅ 456 passed, 9 skipped |
| Same, **3.14.7** (this machine's Python; the PR didn't test it) | ✅ 456 passed, 9 skipped |
| **3.15** | ⚠️ Not testable here: uv only offers **3.15.0 beta 2**, where `faust-cchardet` crashes (SIGSEGV) while building, before any test runs. Likely the old beta (the author used 3.15.1). Not confirmed |
| Compile the package with warnings as errors | ✅ 0 warnings with the PR (3.11–3.14). Without it: **fails, 8 warnings**. So the check is real |
| The 4 new fix tests on our current code | ❌ all 4 fail (httpx cookies, cache connection, log files closed, no deprecated SSL flags); the `async_cached_property` tests can't load (module missing). ✅ all pass with the PR |
| ClientHello comparison tests (raw socket, httpx, aiohttp) | ✅ pass with and without the PR, as designed: they prove the TLS handshake didn't change |
| `async_cached_property` vs the old package | Same model: cache and locks stored on the instance, so `copy.copy` / `deepcopy` of media objects behave as before. All uses are plain `await obj.prop` |
| `_httpx_funct` | Our session is a plain `httpx.Client` (no `request()` override). Callers pass `url, params, cookies, headers, json, data, timeout, follow_redirects`, which `build_request()`/`send()` accept |
| pywidevine 1.9 | Our code uses `Cdm.from_device`, `open`, `get_license_challenge`, `parse_license`, `get_keys`, `close`, `Device`, `PSSH`; the PR author's live DRM download on 1.9 worked (25/25). Not live-tested here |
| `test/unit` with `-W error` on 3.14 (the PR's extra claim) | ⚠️ 2 failures, **not from #28**: `ResourceWarning`s from test code added with #19/#22 (`open(r).read()` without close at `test_filename_collisions.py:231`; `with sqlite3.connect(...)` in `test_collision_recovery.py`, which commits but doesn't close). The shipped code uses `closing(...)` correctly |

### Patch impact (important)

4 of the changed files **already ship** in the GUI patch: `classes/of/media.py`, `commands/check.py`, `commands/scraper/actions/utils/log.py`, `managers/sessionmanager/sessionmanager.py`. The patch installs over PyPI's ofscraper, which doesn't have the new pieces they need:
- `media.py` now imports `ofscraper.utils.async_cached_property` → that **new file must be added to `FILES`**.
- `check.py` now calls `system.new_event_loop()` → **`utils/system/system.py` must be added to `FILES`**. Our `system.py` is otherwise identical to PyPI's, so shipping it is safe; on 3.11/3.12 its behaviour doesn't change.
- `sessionmanager.py`'s `build_request()`/`send()` works on PyPI's httpx 0.28.1.
- The other changed files don't ship; patch users keep PyPI's versions, which is fine on 3.11/3.12.

### Required changes

1. **Re-lock on top of #26:** use the PR's `uv.lock`, then `uv lock` (adds only `pytest-check`).
2. **Patch:** add `utils/async_cached_property.py` and `utils/system/system.py` to `FILES` (150 → 152), rebuild as `v388`, and test-install into a clean copy.

### Optional

3. Add `"3.13"` and `"3.14"` to the CI matrix (both pass here). 3.15 can be added once the runner's uv offers a final 3.15.
4. Fix the 2 test-only leaks (`with open(...)`, `closing(sqlite3.connect(...))`) so `test/unit` passes with `-W error`.

### Implementation (done 2026-10-24)

- The maintainer chose "implement with fixes", plus both extras (CI 3.13/3.14, test leak fixes).
- Applied the code, test and `pyproject.toml` hunks from the git root (`git apply -p1 --exclude=…/uv.lock`).
- **Required change 1, lock:** the PR's `uv.lock` re-locked with our `pyproject.toml` → only `pytest-check 2.10.1` added. `uv lock --check` ✅.
- **Required change 2, patch:** `utils/async_cached_property.py` and `utils/system/system.py` added to `FILES` (150 → 152); rebuilt as **`v388`**.
- **Extra, CI:** matrix is now `["3.11", "3.12", "3.13", "3.14"]` (`.github/workflows/codecov.yml`).
- **Extra, test leaks (test code only):**
  - `test_collision_recovery.py`: `with sqlite3.connect(x) as conn:` → `with closing(sqlite3.connect(x)) as conn, conn:` (still commits, now also closes);
  - `test_filename_collisions.py:231`: `open(r, "rb").read()` → `pathlib.Path(r).read_bytes()`.
- **Results on the real tree:**
  - usual venv (old deps + PyQt6): **459 passed, 8 skipped**;
  - Python 3.14.7 + new lock: **456 passed, 9 skipped**;
  - `test/unit -W error` on 3.14: **219 passed** (was 2 failures before the leak fixes).
- **Patch checks:**
  - all 152 payload files match the tree; root copy identical;
  - test-installed into a clean `932e9e1` copy (rc 0, `PATCH_ID` v388);
  - **ran the installed copy on PyPI's own environment** (Python 3.12, lxml 5.1.1, pywidevine 1.8.0, async-property 0.2.2): the changed modules import, `media.py` uses the in-repo `async_cached_property` (3 concurrent awaits → getter runs once), `system.new_event_loop()` gives uvloop, `_httpx_funct` sends per-request cookies and leaves the client jar empty, `ofscraper --help` works;
  - `restore()` put back every original file (restored `media.py` imports `async_property` again).
- **Found while testing, not changed (same as before the PR):**
  - `copy.deepcopy` of an object fails after **concurrent** awaits of a cached property (the shared lock gets tied to the event loop). The old `async-property` fails in exactly the same case, so it isn't a regression.
  - `restore()` doesn't delete files the patch added (now also `utils/async_cached_property.py`). That's how it has always worked; the leftovers are harmless.
- Not tested: Python 3.15 (only beta 2 available here), a live DRM download on the new pywidevine 1.9 (source installs only; patch users keep 1.8). Not committed yet.

---

## Manual test run (2026-10-25, patch `v389`)

The maintainer worked through the checklist page. Results:

| Result | Tests |
|---|---|
| ✅ Pass | #10 (terminal selector), #13 (`--scrape-paid` skips excluded models), #14 (metadata + hashing), #23 (Docker build applies v389), #24/#25 Docker GUI stop (see note), #3 gyan.dev ffmpeg, #4 (Windows, pipx, Python 3.11.6, manual URL download), GUI help, GUI text length |
| ⏭️ Skip | #2, #8, #12, #19 (no matching media or no easy way to test), #27 (not pushed yet), #28 (decision: **only the patch install matters**, not source installs) |
| ❌ Problem | #25 GUI stop, daemon USR1 (#18/#20/#21), Docker CLI mode |

### Why the Problems happened

- **#25 and daemon: the test commands were wrong, not the code.** `ofscraper/utils/system/system.py:57-62` (`setName()`, called from `main/open/load.py:68`) renames the process to `OF-Scraper` with `setproctitle`. That replaces the whole command line, so `pgrep -f "ofscraper --gui"` and `pgrep -f "ofscraper --daemon"` match nothing:
  - `pkill -TERM -f "ofscraper --gui"` sent no signal at all (pkill is silent when nothing matches);
  - `kill -USR1 $(pgrep -f "ofscraper --daemon")` became `kill -USR1` with no PID → `kill: not enough arguments`.
  - Checked here: a process renamed with `setproctitle("OF-Scraper")` is found by `pgrep -ax OF-Scraper` and not by `pgrep -f "ofscraper --gui"`.
  - Correct commands: `pgrep -ax OF-Scraper` to get the PID, then `kill -TERM <pid>` / `kill -USR1 <pid>`. Don't use `pkill -USR1 -x OF-Scraper` when a GUI is also open, because USR1 would hit it too.
- **Docker CLI mode:** the note says there's no web page in CLI mode. That's expected (CLI mode has no display or noVNC). The check happens in `docker logs -f ofscraper-gui`, which the checklist didn't say clearly. Still needs a re-run.
- **Docker GUI stop (marked pass):** `docker stop` took 11 s. With `stop_grace_period: 30s` that should be a clean exit, but 11 s is also what a 10 s timeout + SIGKILL looks like if the server's compose file is an older copy. To confirm: `docker inspect -f '{{.State.ExitCode}}' ofscraper-gui` (`137` = killed) and the `— stopping` line in `gui-docker.log`.

### Other things the results showed

- The #4 log shows `0.96 MB` in the per-model line but `1.01 MB` in the global totals for the same 1,009,594-byte file. This is the known size-unit mismatch (one uses MiB, one uses MB).
- In the same log, the `fresh download for media` line (`main_download._fresh_data_handler_main:416`) prints the CDN path without hiding it, while the other lines show `{hidden}`. The signature and policy are still hidden. Minor.
- Feature requests (not bugs): a GUI option to exclude models from "Scrape entire paid page" (#13), and a way to run metadata mode with hashing from the GUI (#14). The GUI has the paid-page checkbox (`gui/pages/area_selector_page.py:269`) and the `remove_hash_match` setting, but no exclude list and no metadata action.

### Re-test with the corrected commands (2026-10-25)

- **Daemon USR1 / stop (#18/#20/#21): ✅ pass** on the maintainer's machine.
- **#25 GUI stop: ✅ works.** It was marked Problem because of the crash-log folder, but the logs show a clean stop:
  - main log (`main_profile_2026-10-25/ofscraper_main_profile_2026-10-25_04.08.32.log`): `04:09:50 [GUI] Stop requested — cancelling the current scrape before exit` → `runner() exited` → `04:09:51 [GUI] Scraper stopped — quitting`. The scrape stopped and the window closed within about 1 s.
  - The "new entries" in `gui_crash_logs/faulthandler.log` aren't crashes. `gui/utils/crash_diagnostics.py:179` calls `faulthandler.dump_traceback_later(300, repeat=True)`, which writes every thread's stack **every 5 minutes for as long as the GUI is open** (`Timeout (0:05:00)!`). That GUI session had been open since 04:35 UTC, so it wrote 42 dumps. The last one was at 08:05:53 UTC, before the scrape even started. No new session header or `Fatal Python error` appeared after the stop. The file is now 9.5 MB and never gets trimmed.
  - **Small bug found:** `gui/utils/shutdown.py:59` calls `workflow._on_cancel_scrape()` directly. That skips `table_page._enter_cancelling_ui()` (`gui/pages/table_page.py:110-112`), the only place that sets `_cancelling`. So `_on_scraping_finished` saves a SIGTERM-cancelled run as `status="ok"` instead of `"cancelled"` (log: `Scrape history recorded: ok models=1 dl=0 duration=1m 19s`). `dl=0` is because no summary is built for a cancelled run; the Cancel button gives the same count.
- **Docker CLI mode: USR1 ✅; stop not proven on the server, but works here.**
  - The attached logs (`OF-Scraper-3.14.7/Logs/`) are OF-Scraper's own log files. They show `08:26:05 SIGUSR1 received while idle: starting the next daemon pass`, then a full run, then idle (`Next run at …`).
  - `ofscraper exited (code 0)` is printed by `docker/entrypoint.sh` to stdout only, so it can only appear in `docker logs`, never in those files. On a stop, the daemon goes through `run.main()` → `forcedShutDown()`, which prints `handling force closing of script` to the console and writes nothing to the log file.
  - Reproduced here with the **real `docker/entrypoint.sh` (MODE=cli)** around the **real daemon loop** (`test/unit/daemon_signal_probe.py` with network stubs, run through `run.main()`): run 1 → idle → USR1 → run 2 → idle → SIGTERM → `stop requested` → `handling force closing of script` → `ofscraper exited (code 0)`; entrypoint rc 0, **3.2 s** (the 3 s is the `time.sleep(3)` in `forcedShutDown`).
  - Still to confirm on the server: `docker logs --tail 5 ofscraper-gui` and `docker inspect -f '{{.State.ExitCode}}' ofscraper-gui` after a stop.

### Follow-up fixes (patch `v390`, 2026-10-25)

The maintainer chose all three follow-ups.

1. **History status after a stop.**
   - New signal `app_signals.stop_cancel_requested` (`gui/signals.py`).
   - `gui/utils/shutdown.py` sends it just before `workflow._on_cancel_scrape()`.
   - `TablePage._on_stop_cancel_requested` (`gui/pages/table_page.py`) calls `_enter_cancelling_ui()` unless the page is already cancelling.
   - Result: the run is saved as `cancelled`, and the table shows "Cancelling…" while it stops.
2. **Hang-log size** (`gui/utils/crash_diagnostics.py`).
   - The 5-minute stack dumps stay.
   - New `trim_fault_log()`: when the file is over `FAULT_LOG_MAX_BYTES` (5 MB), it is copied to `faulthandler.log.1` and truncated in place. This works because faulthandler keeps the file open in append mode. A `===== trimmed … =====` header is then written at the top.
   - It runs at startup and from a daemon thread `fault-log-trim` every 300 s.
3. **Daemon stop in the log.** `daemon_process()` (`commands/scraper/scraper.py`) logs `Stop requested: shutting down the daemon` (warning level) when it gets `KeyboardInterrupt`. That covers Ctrl+C, and SIGTERM through `sigterm_as_keyboard_interrupt`.

**Tests:**
- New tests:
  - `test_gui_shutdown.py`: the signal comes before the cancel; the table page enters Cancelling only once;
  - `test_fault_log_trim.py` (3 tests): a small file is left alone; a big file is moved aside at startup; an open file is trimmed in place, and the next faulthandler dump lands in the fresh file with no gap of zero bytes;
  - `test_daemon_shutdown.py::test_stop_is_written_to_the_log`.
- All 6 fail on the old code (the 3 trim tests because `trim_fault_log` doesn't exist there).
- Full suite: **465 passed, 8 skipped** (was 459).
- `docker/entrypoint.sh` (MODE=cli) around the real daemon loop: SIGTERM while idle → `Stop requested: shutting down the daemon` → `ofscraper exited (code 0)` in 3.2 s.
- `install_crash_diagnostics()` with a 6 MB log: moved to `.1`, fresh file started, trim thread running.

**Patch checks:** rebuilt as `v390`; all 152 payload files match the tree; root copy identical; test-installed into a clean `932e9e1` copy (rc 0, `PATCH_ID` v390, the 5 changed files match); `restore()` put back all 152 files.

**Not checked:** the stop line reaching the real log file. The file is written by a standard `QueueListener` thread, and `forcedShutDown()` waits 3 s before exiting, so it should be written. Not committed yet.

---

## Plan: two GUI feature requests (2026-10-25, not started)

**Maintainer's decisions (2026-10-25):** Feature 1 is a **new action** (not an Areas-page checkbox). Metadata **includes Complete mode, with a confirmation**. **Metadata is built first.**

From the maintainer's notes in the manual test run: "an option in the GUI to scrape all paid content with a model exclusion option" (#13) and "metadata with hashing available within the GUI" (#14).

GUI flow today (`gui/main_window.py:1267-1272`): **Action page → Areas page → Models page → Table (Start)**. "Scrape individual posts by URL" is the one action that skips Areas and Models.

### Feature 1: Download all purchased content, with an exclude list

#### What exists today
- The Areas page has "Scrape entire paid page" (`gui/pages/area_selector_page.py:269`). In the GUI it is **limited to the models you picked**. `workflow.py:3102-3221` replaces `process_paid_dict` with a faster version that makes 1 API call and then only processes `self._selected_models`.
- So the GUI can't do what the CLI's `--scrape-paid` does: everything you've bought from **every** creator, including expired and deleted accounts that can't be picked on the Models page.
- The CLI side already honours exclusions. PR #13 made `process_all_paid()` (`data/posts/post.py:323-358`) skip `--excluded-username` names, and that check runs after deleted-model names are resolved.

#### Proposed design
1. **New action** on the Action page: "Download all purchased content (all creators)", internal name `{"paid_all"}`.
   - Like the URL action, it **skips the Areas and Models pages**, because there's nothing to pick.
   - An inline panel on the Action page (the same pattern as the message-filter panel for check mode, `action_page.py:291-332`) holds:
     - an **Exclude creators** box: comma-separated names, with a "Pick…" button that opens a checklist of known models (subscriptions plus names already in the database), and autocomplete;
     - the media-type checkboxes (Images / Videos / Audios), so the run follows the same filter as a normal scrape.
   - Next goes straight to the Table page with Start enabled.
2. **Workflow** (`gui/utils/workflow.py`): a new `_set_paid_all_args()` next to `_set_manual_url_args` / `_set_check_args`. It sets:
   - `args.scrape_paid = True`, `args.usernames = []`, `args.download_area = set()`, `args.actions = ["download"]`;
   - `args.excluded_username = [lower-cased names]`.
   `GUIScraperManager.run_action` (`workflow.py:1622-1631`) already returns False for a paid-only run with no areas, so `runner()` only does `scrape_paid_all()`.
3. **Use the fast GUI path for all creators**, not the stock one. Extend `_filtered_process_paid_dict` with an "all creators" mode:
   - it loops over every `model_id` in `get_all_paid_posts()` instead of only the selected models;
   - **usernames:** use the known name when the id is in the loaded subscription list, and only call `profile.scrape_profile()` for unknown ids. That call is what makes the stock path slow (about 60+ profile calls);
   - **deleted accounts** get the same handling as `process_all_paid`: the recorded name from the database, or `DELETED_MODEL_PLACEHOLDER_<id>`. To avoid two copies of that logic, move it from `post.py:340-353` into a small helper, `resolve_paid_username(model_id)`, and call it from both places. `post.py` is already in the patch;
   - skip excluded names with `is_excluded_username()` (from #13) and the same warning;
   - keep the live table rows (`_load_models_from_db([...], media_ids=...)`) by passing a small stand-in with `.id` / `.name` for creators that aren't in the model list.
4. **The existing Areas-page checkbox** stays as it is. Its text and tooltip change to say "for the models you select". The help page gets a line pointing to the new action.
5. **Remember settings:** save the exclude list in the GUI settings (as the Areas page does, `area_selector_page.py:748`). Record `paid_all` and the exclude list in the scrape-history snapshot, so "Re-run" works (`gui/utils/scrape_history.py`, `apply_entry_to_pages`).
6. **Daemon:** allowed. The same daemon loop works because the args are rebuilt on each run.

#### Risks / notes
- On big accounts, the first run of this mode still makes 1 profile call per creator not on the subscription list. The log should say so ("Looking up 23 creators not in your subscription list…").
- `excluded_username` also filters the normal model list. Here that's only what we want, because this action has no model list. The arg must be **reset** for other actions, or it would leak into the next normal scrape. `_baseline_args` (`workflow.py:2560-2580`) is where per-run args get restored.

#### Tests
- `_set_paid_all_args` sets the same `scrape_paid` / `excluded_username` values the CLI parser gives for `--scrape-paid -eu "Bob,carol"` (compare with `UsernameParse`).
- The all-creators mode, with a stubbed `get_all_paid_posts`, processes every creator except excluded ones (case ignored). A deleted-account name can be excluded. Known ids make no `scrape_profile` call.
- `resolve_paid_username` gives the same results as the old inline code (the existing #13 tests keep passing).
- `excluded_username` is cleared when the next run is a normal scrape.
- An offscreen widget test: the new action exists, its panel shows only for that action, and Next goes to the Table page.

---

### Feature 2: Metadata mode in the GUI

#### What exists today
- The GUI has no metadata action. `ACTION_CHOICES` (`action_page.py:26-33`) is download / like / unlike / combos / URL, plus four check modes.
- The CLI runs `ofscraper metadata -md {check|update|complete} [--mark-stray-locked] …` (`utils/args/parse/group_bundles/metadata.py:40-95`). `manager.pick()` sends `command == "metadata"` to `commands/metadata/metadata.py:process_selected_areas()` → `metadata()` → `prepare()` → `process_users_metadata_normal` / `metadata_user_first`. With `scrape_paid` it also runs `metadata_paid_all()`.
- Hashing is a config setting, `remove_hash_match` (Config dialog → Advanced, `config_dialog.py:947`). `settings.py:184` copies it into `settings.hash`, and `_metadata_hash_helper` (`commands/metadata/manager.py:163`) reads it. PR #14 fixed the crash there.

#### Proposed design
1. **New action** "Update metadata from files on disk (no downloads)" → `{"metadata"}`, with an inline panel on the Action page:
   - **Mode** (radio buttons, plain-language labels):
     - *Update*, the default: "Mark files already on disk as downloaded and refresh info from the API";
     - *Check*: "Refresh info from the API only";
     - *Complete*: "Mark everything in the chosen areas as downloaded". This one gets a **confirmation dialog**, because it changes download status for media that may not be on disk.
   - **Mark unmatched media as locked** (`--mark-stray-locked`), off by default.
   - **Check file hashes this run**. It starts with the config value of `remove_hash_match`, applies to this run only, and doesn't change the config. Tooltip: slower, reads every matching file.
2. **Areas and Models pages work as normal.** On the Areas page, controls that don't apply to metadata are hidden while this action is selected: text download options, Discord, quality, and "allow duplicate downloads". "Scrape entire paid page" stays, because the CLI supports `metadata --scrape-paid`.
3. **Workflow:**
   - New `_set_metadata_args()`: `args.command = "metadata"`, `args.metadata = mode`, `args.mark_stray = bool`, `args.download_area = set(areas)`, `args.usernames = [selected]`, `args.actions = []`, `args.gui = True`, `args.no_rich = True`.
   - After `settings.update_settings()`, set `settings.get_settings().hash` to the checkbox value.
   - **First implementation step:** build the args the CLI would make for `ofscraper metadata -md update --username x --posts timeline`, diff them against the GUI's, and match them exactly.
4. **Running it:** a new one-shot `_run_metadata_mode()`, called from `_run_scraper_thread` like `_run_check_mode()` (`workflow.py:2933-2936`). No daemon loop. It calls `metadata.process_selected_areas()` with the GUI's live-display stubs and logging already installed. **No changes to `commands/metadata/metadata.py`**, which isn't in the patch.
5. **Afterwards:**
   - reload the table from the database for the selected models (`_load_models_from_db`), so the Downloaded column shows the new status;
   - print the metadata stats summary (`stats_manager`, activity `"metadata"`) to the GUI console;
   - save a history entry with action `metadata` and the mode;
   - emit `scraping_finished`.
6. **Progress and cancel:**
   - metadata uses `progress_updater.metadata` tasks, which the GUI's progress hooks don't map yet. The first version shows an indeterminate bar plus per-model status lines. A real bar can come later;
   - cancel goes through `_gui_cancel_event`. The metadata loop doesn't check it, so cancel falls back to the existing force-stop after the grace period. To check during implementation: can a cancel check be added between models without editing `metadata.py`, for example by wrapping `MetadataCommandManager._execute_metadata_action_on_user`, the way `GUIScraperManager` wraps `_execute_user_action`?

#### Risks / notes
- *Complete* mode can wrongly mark media as downloaded. That's why it has the confirmation, and *Update* is the default.
- Metadata settings (`command = "metadata"`) must not leak into the next download run. Reset `command`, `metadata` and `mark_stray` along with the other per-run args, and restore `settings.hash` from the config.

#### Tests
- `_set_metadata_args` matches the CLI parser's namespace for the same options (all 3 modes, with and without `--mark-stray-locked` and `--scrape-paid`).
- The hash checkbox sets `settings.hash` for the run, and the next run reads the config value again.
- `_run_metadata_mode` with `process_selected_areas` stubbed: the table reloads, history records `metadata`, and `scraping_finished` fires, including when it raises.
- Complete mode asks for confirmation, and saying No doesn't start the run.
- An offscreen widget test for the new action panel. Areas-page controls hide and show again.
- Manual: metadata *update* with hashing on, for one model with files on disk. Those files should show as downloaded in the table (the same check as the #14 item in the checklist).

---

### Files and patch impact
- Changed: `gui/pages/action_page.py`, `gui/utils/workflow.py`, `gui/pages/area_selector_page.py`, `gui/main_window.py` (page routing), `gui/utils/scrape_history.py`, `gui/help/GUI_HELP.md`, `data/posts/post.py` (helper only). All are already in the patch. No new files are needed in the patch, unless the "Pick creators" dialog goes in its own file (`gui/dialogs/creator_picker_dialog.py`, which would make 153 files).
- Base CLI behaviour doesn't change, except that `resolve_paid_username` is moved out of `process_all_paid` without changing what it does.

### Suggested order
1. Feature 2 (metadata) first. It's self-contained, reuses the normal Areas/Models flow, and has no API cost.
2. Feature 1 second (more workflow code, plus the username-lookup speed-up).

Each one becomes its own patch version and checklist item.

### Feature 2 implemented: metadata action (patch `v391`, 2026-10-25)

**What changed:**
- `gui/pages/action_page.py`:
  - new choice "Update metadata from files on disk (no downloads)" → `{"metadata"}`;
  - a panel under it with mode radios (Update is the default), "Mark unmatched media as locked", and "Check file hashes this run" (starts from `config_data.get_hash()`);
  - Next sends `metadata_options_changed` before `action_selected`.
- `gui/signals.py`: `metadata_options_changed = pyqtSignal(dict)`.
- `gui/pages/area_selector_page.py`:
  - with the metadata action, the areas box is titled "Metadata Areas";
  - Post Text, the Discord row, Advanced Scrape Options and Daemon Mode are hidden, with daemon and Discord unticked;
  - "Scrape entire paid page" stays.
- `gui/utils/workflow.py`:
  - `_on_metadata_options` stores the options;
  - `_apply_metadata_args` runs at the end of `_set_args` and turns the args into the CLI's metadata args: `command="metadata"`, `metadata=mode`, `mark_stray`, `anon=False`, `actions=[]`, `action=None`, `posts=areas`. `scrape_paid` becomes the mode or None, because metadata's `--scrape-paid` takes a mode;
  - **the normal path now restores `args.command`** to the value parsed at launch (`_launch_command`) and clears `metadata` / `mark_stray`. Before, nothing ever reset `command`, so a metadata run would have leaked into the next download;
  - `_run_metadata_mode()` is a one-shot run from `_run_scraper_thread`, like check mode. For the length of the run:
    - it replaces `config_data.get_hash`, because `settings.update_args()` rebuilds settings from the config mid-run (`settings.py:45-49, 184`);
    - it wraps `MetadataCommandManager._data_helper` to check `_gui_cancel_event` before each model and to post "Metadata (mode): name (n of N)". `command.py:37-40` re-raises `KeyboardInterrupt`, so cancel stops cleanly.
    Then it calls `metadata.process_selected_areas()` (no change to `commands/metadata/metadata.py`), restores everything, and reloads the table with `_load_models_from_db`;
  - `_confirm_metadata_complete()` runs in `_start_scraping`: Complete mode shows a Yes/No (default No); No means nothing starts.
- `gui/utils/scrape_history.py`: the snapshot stores `metadata` options, and Re-run restores them. Complete still asks again.
- `gui/help/GUI_HELP.md`: new "Update metadata" section (`#action-metadata`), plus a line in Select Action.

**Found while building:**
- **CLI bug (base tool, not changed):** `-ms` is defined twice in the metadata command: `--mark-stray-locked` (`group_bundles/metadata.py:75`) and `--mass-msg`. Click keeps the last one, so **`ofscraper metadata -ms` sets `mass_msg`, and mark-stray never turns on**. `--mark-stray-locked` / `--mark-stray` work. It was checked with the real parser: `-md check -ms` → `mark_stray False`; `--mark-stray-locked` → `True`. The GUI sets `args.mark_stray` directly, so it isn't affected.

**Tests:** `test/unit/test_gui_metadata_action.py`, 13 tests:
- GUI args equal the real CLI parser's for `-md update`, `-md check --mark-stray-locked`, and `-md complete --scrape-paid complete` (run in a subprocess, isolated HOME);
- a download after metadata gets `command`, `metadata`, `mark_stray`, `scrape_paid` and `actions` back;
- the hash choice is in effect during the run and the config reader is restored after;
- cancel stops before the 2nd model, with no table reload;
- a finished run reloads the table;
- the Complete confirm, for Yes / No / other modes;
- the Action-page panel and the signal order;
- the Areas page hides and shows the right sections;
- history keeps the options;
- `_run_scraper_thread` goes to metadata and emits `scraping_finished`.

All 13 **fail on v390** and pass now. Full suite: **478 passed, 8 skipped**. Both pages were rendered offscreen and checked, and a leftover divider line was fixed.

**Patch checks:** `v391`; 152 payload files match the tree; root copy identical; test-installed into a clean `932e9e1` copy (rc 0, the 6 changed files match); `restore()` put back all 152.

**Not tested here:** a live metadata run against the API, and the real progress display. Metadata's own progress bars aren't mapped to the GUI, so the GUI shows status lines only. Manual check: metadata *Update* with hashing on, for one model with files on disk. They should show as downloaded in the table afterwards.

### Feature 1 implemented: all purchased content + exclude list (patch `v392`, 2026-10-25)

**What changed:**
- `gui/pages/action_page.py`: new choice "Download all purchased content (all creators)" → `{"paid_all"}`. Its panel has:
  - **Exclude creators** (comma-separated; `@` and case are ignored, duplicates dropped);
  - **Pick…**, a searchable checklist of loaded subscriptions plus `paid_all_known_creators` from earlier runs. If none are known, it explains how to get names;
  - Images / Videos / Audios.
  The exclude list and media types are saved in `gui_settings.json` (`paid_all_excluded`, `paid_all_media_types`). Next sends `paid_all_options_changed`, then `action_selected`.
- `gui/main_window.py`: `{"paid_all"}` goes straight to the Table page (no sidebar) and calls `table_page.start_paid_all_run()`.
- `gui/pages/table_page.py`: `start_paid_all_run()` clears the table, log and progress, then calls `workflow.start_paid_all()`. Start Scraping and History Re-run with this action go the same way, so **Areas-page settings are never read** for it.
- `gui/utils/workflow.py`:
  - `start_paid_all()` / `_reset_paid_all_state()`: `_scrape_paid=True`, and clears models, areas, `_advanced` (rescrape / delete DB / delete files), daemon and date range. This runs before `_start_scraping`, because the confirm and disk-space dialogs read this state.
  - `_set_paid_all_args()`:
    - `actions=["download"]`, no areas or posts, `usernames=[]`, `scrape_paid=True`;
    - `excluded_username` = the box + any `-eu` from launch;
    - media types; baseline `after` / cache / dupes / quality; `before=None`; daemon off.
    `GUIScraperManager.run_action` is already False for a paid-only run, so `runner()` only does `scrape_paid_all()`.
  - **Every `_set_args` call now resets `args.excluded_username`** to the launch value, so the exclude list can't hide models in later runs. `_on_action_selected` turns `_scrape_paid` off when leaving this action.
  - The GUI's fast `process_paid_dict` replacement has an all-creators mode. The new `_paid_all_targets()` loops over every id from the single `get_all_paid_posts()` call:
    - subscription names come from `all_subs` with no API call;
    - other ids go through `post.resolve_paid_username()` (deleted → recorded name or `modeldeleted_<id>`), and a failed lookup skips that creator with a warning;
    - excluded names are skipped with the CLI's warning text.
    The processed creators go to `_paid_all_models` (used for the table reload) and are remembered for Pick… (`_remember_paid_all_creators`).
  - Each run resets `_scrape_paid_media_ids`. It was never cleared before, so paid rows from earlier runs kept showing on later paid runs.
- `data/posts/post.py`: the deleted-account name logic moved from `process_all_paid` into `resolve_paid_username(model_id)`, with no change in behaviour. The 9 tests from #13 still pass.
- `gui/utils/scrape_history.py`: the snapshot stores `paid_all` options, and Re-run restores them without needing models.
- `gui/help/GUI_HELP.md`: new section `#action-paid-all`. The "Scrape entire paid page" help and tooltip now say "for the models you select" and point to the new action.

**Decisions:**
- **No daemon for this action yet.** Starting from the Action page means there's no daemon control. The plan said "allowed", but it would have needed its own interval and controls on the panel. The CLI `--daemon --scrape-paid` covers it for now.
- No date filter: paid content isn't date-filtered in the GUI anyway.

**Tests:** `test/unit/test_gui_paid_all_action.py`, 10 tests:
- the GUI args match the real CLI parser for `--scrape-paid -eu "Bob,carol" --action download`;
- leftover rescrape / delete / daemon / dates / models don't apply, in the args or in the start confirm summary;
- the exclude list and `scrape_paid` don't carry into the next download;
- `_paid_all_targets`: names subscriptions with no lookup, looks up the others, skips excluded names ignoring case (including a `modeldeleted_` name), and skips a creator whose lookup fails;
- creator names are remembered and merged;
- **the real run loop** with the paid API, scraper and DB stubbed: every creator is processed, the table reloads with all of them, the replacement is removed after the run, and the names are saved;
- Action-page parsing, signal order, saving and reloading;
- History snapshot and Re-run.

All 10 **fail on v391**. Full suite: **488 passed, 8 skipped**. The panel and the Pick… dialog were rendered offscreen and checked.

**Patch checks:** `v392`; 152 payload files match the tree; root copy identical; test-installed into a clean `932e9e1` copy (rc 0, the 9 changed files match); `restore()` put back all 152.

**Not tested here:** a live run against the API, including how long the username lookups take for many expired creators. That's for the manual checklist.

**Daemon:** decided 2026-10-25 not to add one for this action (CLI `--daemon --scrape-paid` covers it).

### Extra tests for v390–v392 (2026-10-25, tests only, no patch change)

- `test_gui_paid_all_action.py`: paid media ids reset per run; `process_paid_dict` / `process_user` put back after a stop or an error; `resolve_paid_username` (normal, known deleted, deleted without name, unknown deleted); `MainWindow._on_action_selected` routing; `TablePage.start_paid_all_run` and the `_on_start_scraping` redirect (and not while busy); Pick… dialog (typed names kept, ticks, case-insensitive search, Cancel, no-names message).
- `test_gui_metadata_action.py`: `_start_scraping` stops when Complete mode is declined; History re-run restores the metadata options onto a real Areas page.
- `test_gui_help_links.py`: every `#link` in `GUI_HELP.md` has an anchor; both new actions are linked.
- Mutation check: removing the media-id reset, the `process_paid_dict` restore, the Complete confirm, or the case-insensitive search each makes its test fail.
- Full suite: 504 passed, 8 skipped. Test files are not in the patch payload, so no rebuild.

### CLI `-ms` clash fixed (patch `v393`, 2026-10-25)

- **Bug (upstream 3.14.7):** in `ofscraper metadata`, `-ms` was the short flag of both `--mark-stray-locked` and `--mass-skip` (`-mm/-ms`). Click lets the later one win, so `metadata -ms` set `mass_msg=False` and left `mark_stray=False`.
- **Fix:** `--mark-stray-locked` / `--mark-stray` now use short `-msl` (`utils/args/parse/group_bundles/metadata.py`). `-ms` keeps meaning `--mass-skip`, as in every other command, so nothing that worked before changes.
- **Tests:** new `test/unit/test_cli_flag_clashes.py` scans every command and subcommand for a flag used twice, and checks `-msl`, `--mark-stray-locked` and `-ms` in `metadata`. With the old `-ms` put back, it fails. `test_gui_metadata_action.py` now compares against `-msl`.
- **Second clash found (fixed in v394, below):** in the main command `-ps` is both `--promo-skip` (`-po/-ps`, `user_list.py`) and `--post-script` (`scripts.py`). Post-script wins, so `-ps` on its own errors with "requires an argument". Allow-listed in the clash test (`KNOWN`) until fixed.
- Full suite: 506 passed, 8 skipped. Patch `v393`: 153 payload files match the tree; root copy identical; test-installed into a clean `932e9e1` copy (rc 0, all 153 match); `restore()` put back every changed file (the 40 files the patch adds stay, as before).

### CLI `-ps` clash fixed (patch `v394`, 2026-10-25)

- **Bug (upstream 3.14.7):** `-po/-ps` (`--promo-only/--promo-skip`, `utils/args/parse/arguments/user_list.py`) and `-ps` (`--post-script`, `scripts.py`) shared `-ps`. Post-script won, so `-ps` for promo-skip never worked.
- **Fix:** promo is now `-po/-psk`. `-ps` stays `--post-script`, so nothing that worked before changes.
- **Tests:** the `KNOWN` allow-list is gone, so the clash scan now expects zero clashes in every command. New `test_promo_skip_and_post_script_flags` checks `-psk`, `--promo-skip`, `-po` and `-ps after.sh`. With the old flag put back, both tests fail.
- Full suite: 507 passed, 8 skipped. Patch `v394`: 154 payload files match the tree; root copy identical; test-installed into a clean `932e9e1` copy (rc 0, all 154 match); `restore()` put back every changed file.

### User test of v394: crash + Pick… (patch `v395`, 2026-10-25)

**Report:** "Download all purchased content is not fully working and crashing the GUI"; Pick… does nothing useful before the model list has been loaded.

**Evidence (`Logs/faulthandler.log`, `Logs/model_fetch_breadcrumbs.log`):**
- Session 18:01:38 (idle: Configuration, then Pick…). It crashed at 18:06:38. The "Timeout (0:05:00)!" dump began on thread 0x1fc54 (the `fault-log-trim` thread, in `pathlib.py`) and then "Windows fatal exception: access violation".
- Session 18:09:20: all-purchased run started 18:09:37, crashed 18:14:20, again inside the 5-minute dump. The stack shows `ssl.py line 2034523696`, a garbage line number, i.e. the dump read a frame that was being freed.
- Cause: `faulthandler.dump_traceback_later(..., repeat=True)` walks other threads' frames from its watchdog thread without stopping them, which is unsafe when they are running Python code. Older sessions mostly got away with it, with idle threads at dump time. The v390 trim thread used the same 300 s interval, so it was always mid-work at dump time, and even an idle GUI crashed.
- No GUI log for the 18:09 run was in `Logs/` (the four `ofscraper_main_profile_*` files there are from the 08:24 daemon test), so whether the run itself had other problems is unknown.

**Fix (`gui/utils/crash_diagnostics.py`):** `faulthandler.enable()` stays for real crashes. Periodic dumps only run when `OFSCRAPER_GUI_HANG_DUMP_SECONDS` is set (new `hang_dump_seconds()`). `_trim_fault_log_forever` and its thread were removed; `trim_fault_log()` still runs at startup. Help (`#troubleshooting-crash`) mentions the variable.

**Pick… (`gui/pages/action_page.py`):** with no known names it asks "Load your subscriptions?". Yes runs the Areas page's own background load (`area_page._start_model_load()`), the button shows "Loading…", a 250 ms timer waits for `_models_loading` to clear, then Pick… reopens. Load errors use the Areas page's existing "Unable to Load Models" dialog. If models are loaded but none exist, it shows the old message.

**Tests:** `test_fault_log_trim.py` checks no dumps and no trim thread by default, that the env var turns dumps on, and the env parsing (the default test fails with the old 300 s default). `test_gui_paid_all_action.py` covers the Pick… load: Yes / still loading / done reopens; No; failure; already loaded. Full suite: 516 passed, 8 skipped.

**Patch checks:** `v395`; 154 payload files match the tree; root copy identical; test-installed into a clean `932e9e1` copy (rc 0, all 154 match); `restore()` put back every changed file.

### User test of v395: wrong summary after all-purchased (patch `v396`, 2026-10-25)

**Report (screenshots `purchased.webp`, `purchased2.webp`):** no crash any more. The table has 640 rows, but the Final Stats Summary gives every one of the 17 creators "1 downloads total [1 videos …]", the global totals say 1 item / 234.35 MB, and the status bar says "Downloads: 1 / 1".

**Cause:** the downloader resets the download counters (`commands/scraper/actions/utils/globals.py`, `main_globals()` via `mainProcessVariableInit()`) for every creator. Normal GUI downloads save a per-model snapshot (`_record_per_model_download_stats`) before the next model starts, but the paid path never did. `build_pending_summary_payload()` for non-normal runs then read the counters once, at the end (the last creator, `modeldeleted_16692547`, 1 video), and the table's "legacy fallback" printed that for every model. This affects the older "Scrape entire paid page" option too.

**Fix (`gui/utils/workflow.py`, `gui/pages/table_page.py`):**
- The paid `process_user` wrapper records each creator's stats in its `finally` (paid creators run one at a time, so this is safe).
- New `_run_download_totals()` sums `_per_model_run_stats` for every summary branch; the payload carries `per_model` for paid runs too. For all-purchased, the summary's model list falls back to `_paid_all_models`.
- `_record_per_model_download_stats(..., nothing_downloaded=True)` records zeros. It's used for a creator or model with no media, where the counters still held the previous model's numbers (an older bug in the normal path).
- Table summary: when per-model stats exist but one model has none, it shows zeros instead of the global counters.

**Tests (`test_gui_paid_all_action.py`):** a full paid run with three creators (3 videos + 2 photos; 1 video + 1 failed; nothing) checks per-creator stats, zeros for the empty one, and summary totals 6 / 4 / 2 / 1 failed / 600 bytes. It fails with the recording removed. Plus a zeros-for-empty test. Full suite: 518 passed, 8 skipped.

**Patch checks:** `v396`; 154 payload files match the tree; root copy identical; test-installed into a clean `932e9e1` copy (rc 0, all 154 match); `restore()` put back every changed file.

### User test of "v396": still wrong summary, table stuck on one creator (patch `v397`, 2026-10-25)

**Report (screenshots `purchased3.webp` to `purchased6.webp`, log `Logs/ofscraper_main_profile_2026-10-25_19.32.41.log`):** the summary still gives every creator 1 video and the total is 1 item. While scraping, the table only ever showed `modeldeleted_16692547`.

**Summary:** the run was **not** v396. Every log line number matches the v395 `workflow.py` (e.g. `_run_scraper_thread:3547` "process_paid_dict patch applied"; v396 has it at 3564), so the v396 summary fix never ran. Nothing new to fix there; it needs a re-test on the new patch.

**Table cause:** the paid loop in `_filtered_process_paid_dict` calls `_load_models_from_db([creator], media_ids=…)` for each creator, and that always sent `data_replace`, so each creator wiped the one before.

**Fix (`gui/utils/workflow.py`):**
- `_load_models_from_db(..., append=False)`: with `append=True` it sends `data_loading_finished` (adds rows) instead of `data_replace`.
- The paid loop replaces for the first creator and appends for the rest. The table is already cleared when an all-purchased run starts.
- Each scrape's log now has `[GUI] patch <PATCH_ID>` just before the runner starts, so a log shows which patch made it.

**Tests (`test_gui_paid_all_action.py`):** a paid run through the real loop with three creators (DB and post classes stubbed) checks replace / append / append. A small real SQLite DB checks which signal `_load_models_from_db` sends. Both fail with the change removed. Full suite: 521 passed, 8 skipped.

**Patch checks:** `v397`; 154 payload files match the tree; root copy identical; test-installed into a clean `932e9e1` copy (rc 0, all 154 match).

**Mistake during checks:** `restore(backup_dir)` was called without `target_pkg`, so it restored into the default target, the local pipx install (`~/.local/share/pipx/venvs/ofscraper`, Python 3.12, which had v391). That put 154 files from `932e9e1` (patch v84) over v391. No copy of v391 exists. Fixed: the user re-patched that install with v397 (all 154 files match, GUI imports OK).

**User test of v397 (Windows):** the table fills per creator while scraping, and the summary is correct.

### Leftover fixes (patch `v398`, 2026-10-25)

1. **WebEngine remote debugging (`gui/app.py`, `gui/dialogs/auth_dialog.py`).** Every GUI start opened a Chromium remote-debugging port (9200–9299) with `--remote-allow-origins=*`, `--disable-web-security` and `--allow-running-insecure-content`. Any local program could drive the embedded login browser, and the same-origin policy was off while logged in to OnlyFans. Now:
   - `webengine_flags()` keeps only `--disable-blink-features=AutomationControlled --disable-features=StorageAccessAPI` by default. The `sys.argv` `--webEngineArgs` path uses the same string (it used to add the debug flags even when `QTWEBENGINE_CHROMIUM_FLAGS` was already set).
   - `OFSCRAPER_GUI_WEBENGINE_DEBUG=1` turns the port back on, with origins limited to `http://localhost:<port>` and `http://127.0.0.1:<port>`.
   - `_get_or_create_debug_port()` returns `None` when it's off. The CDP listener (init and Clear Session) only starts with a port. **DevTools ↗** shows "DevTools is off" with how to turn it on. GUI_HELP "Login in App Browser" documents this.
2. **Media link in logs (`main_download.py`).** "Downloading media with url …" and "fresh download for media …" logged `ele.url`. They now use `common_logs.get_url_log(ele)` like the other lines.
3. **Size units (`managers/stats.py`).** `DownloadStats.__str__` divided by 1024 but printed "MB", while GLOBAL RUN TOTALS uses `humanfriendly.format_size` (1000). The per-creator line now uses `format_size` too (1009594 bytes → 1.01 MB in both). `stats.py` is now in `FILES`, along with its existing `\\[` escape fix.
4. **`model_selector_dialog.py`** used `QWidget` without importing it. Nothing opens this dialog today.

**Tests:** new `test_gui_devtools_debug.py` (flags off by default, opt-in port, DevTools message, dialog builds), `test_download_stats_size.py`, and a scan in `test_url_log.py` for raw `{ele.url}` in the download managers. Each fails with its fix removed. Full suite: 529 passed, 8 skipped.

**Patch checks:** `v398`; 155 payload files match the tree; root copy identical; test-installed into a clean `932e9e1` copy (rc 0, all 155 match); `restore(backup, target_pkg=<test copy>)` put back every changed file; the local pipx install was checked unchanged.

**Not tested live:** logging in with the App Browser without `--disable-web-security`. It's on the checklist (`gui-login-devtools`).

**User test of v398 (Windows):** `gui-login-devtools` and `gui-size-units` pass. App Browser login still captures all four values. The user saw the whole GUI flash when the login browser opened.

### Login browser flash (patch `v399`, 2026-10-26)

**Problem:** on Windows, opening **Login in App Browser** made the whole GUI flash. `QWebEngineView` needs RHI (GPU) drawing, and Qt switches windows over to it the first time one appears.

**Check:** the user started the GUI with `$env:QT_WIDGETS_RHI="1"` and the flash was gone.

**Fix (`gui/app.py`):** `enable_rhi_widgets()` calls `os.environ.setdefault("QT_WIDGETS_RHI", "1")` on Windows only. `launch_gui()` calls it after the Docker block and before `QApplication(...)`. Setting `QT_WIDGETS_RHI=0` turns it off. Linux and macOS are unchanged because they weren't tested.

**Tests:** `test_gui_devtools_debug.py` checks Windows sets it, a user value wins, and Linux/macOS stay unset. It also checks the call comes before `QApplication(`. Each test fails with its line removed. Full suite: 534 passed, 8 skipped.

**Patch checks:** `v399`; 155 payload files match the tree; root copy identical; test-installed into a clean `932e9e1` copy (rc 0, 0 diffs); restore into the test copy OK; the local pipx install was checked unchanged.

**User test of v399:** `gui-login-flash` passes on Windows. On Linux the GUI still flashed, because v399 only set the variable on Windows. Running `QT_WIDGETS_RHI=1 ofscraper --gui` on Linux stopped it.

### Login browser flash on Linux (patch `v400`, 2026-10-26)

**Fix (`gui/app.py`):** `enable_rhi_widgets(platform, docker=False)` now sets `QT_WIDGETS_RHI=1` on Windows and Linux. `launch_gui()` calls `enable_rhi_widgets(docker=_is_docker())`, so Docker is left alone: it has no GPU and no in-app login. macOS is unchanged (untested). `QT_WIDGETS_RHI=0` still turns it off.

**Tests:** `test_gui_devtools_debug.py` now covers Windows, Linux, Docker, macOS and a user's own value. It still checks the call comes before `QApplication(`. Each test fails with its fix removed (Docker check, Linux check, `_is_docker()` argument). Full suite: 536 passed, 8 skipped.

**Patch checks:** `v400`; 155 payload files match the tree; root copy identical; test-installed into a clean `932e9e1` copy (rc 0, 0 diffs); restore into the test copy OK; the local pipx install was checked unchanged.

**User test of v400:** `gui-login-flash` passes on Windows and Linux.

### Re-analysis fixes (patch `v401`, 2026-10-26)

A fresh pass over the tree: pyflakes found no undefined names; logs, the login profile folders and network timeouts were checked. Three fixes:

1. **Manual key mode without CDM files (`keyhelpers.py`, `alt_download.py`, `download/utils/retries.py`).** The user's Docker logs from 2026-10-25 08:24 and 08:26 had 294 `IsADirectoryError: [Errno 21] Is a directory: '.'` lines. With Key Mode manual and a blank `private-key`, `pathlib.Path("")` is `.`, so every DRM video downloaded, failed at the key step and was retried. Now:
   - `manual_cdm_problem()` returns a plain message when `client-id` or `private-key` is blank or not a file.
   - `check_manual_cdm(ele)` runs in `alt_download` before the DRM download (manual mode only, and only when there's no cached key). It logs the message once at ERROR and raises `CdmFilesMissing`.
   - `CdmFilesMissing.no_retry = True`, and `download_retry` doesn't retry exceptions with `no_retry`. `key_helper_manual` also checks before reading the files.
   - `run.download` records the message as the failure reason, so the GUI failure list shows it too.
2. **CI skipped every GUI test (`.github/workflows/codecov.yml`).** CI installed only `--extra test`, so every GUI test file skipped itself (476 tests ran instead of about 550). The workflow now installs the Qt system libraries, uses `--extra test --extra gui`, sets `QT_QPA_PLATFORM: offscreen`, and has a "Check Qt loads" step so a broken Qt fails the job instead of skipping. I checked it in a clean `ubuntu:24.04` container (podman): Python 3.11 and 3.14 both give 547 passed, 9 skipped. A bare image needs `g++` for `faust-cchardet` on 3.14; GitHub's runner already has it.
3. **Download all purchased hid failed creators (`gui/utils/workflow.py`).** An error while preparing one creator went only to the debug log. It's now also a `log.warning` and a WARNING line in the GUI log; the other creators continue.

**Tests:** new `test_drm_cdm_check.py` (blank/missing paths, once-only log, other key modes, cached key, no retry, check before download), `test_ci_workflow.py`, and `test_a_failed_creator_is_reported_not_hidden` in `test_gui_paid_all_action.py`. Nine mutations, each caught. Full suite: 549 passed, 8 skipped.

**Patch checks:** `v401`; 156 payload files match the tree; root copy identical; test-installed into a clean `932e9e1` copy (rc 0, 0 diffs); restore into the test copy OK; the local pipx install was checked unchanged.

**Not changed (from the re-analysis):** two `drm_keydive.py` requests without a timeout, patch backups never pruned, and small cleanups (`.gitignore` `*.spec` line, empty `crypto`, unused `.gitmodules`, unused imports).

**Follow-up (patch `v402`, 2026-10-28).** The user's `drm-cdm-blank` run on Windows (log `Logs/ofscraper_main_profile_2026-10-28_00.21.08.log`) showed the fix working: one ERROR line from `check_manual_cdm`, no `Is a directory`, DRM videos skipped right away. But `run.download` also wrote the message plus a full traceback at debug level for each of the 21 DRM videos. It now skips the traceback when the error has `no_retry` (a known setup problem), keeping one short debug line per item. Two new tests in `test_drm_cdm_check.py` (no traceback for `CdmFilesMissing`; other errors keep theirs); the mutation that removes the check is caught. Full suite: 551 passed, 8 skipped. Patch checks as for v401 (156 files, 0 diffs, restore OK, local install unchanged). Manual test `drm-cdm-blank` passed on Linux with v402 (run with `OFSC_USE_WIV_CACHE_KEY=false` so saved keys are not used): 1 ERROR line, 21 DRM videos failed with one short line each, 0 tracebacks, 0 retries, 913 other files downloaded.
