# OF-Scraper 3.14.7 + GUI: System Analysis

- **Date:** 2026-10-23
- **Commit analyzed:** `aa17b43` (branch `main`)
- **Scope:** the `OF-Scraper-3.14.7/` folder except `open_pull_requests/`
- No source files were changed during this analysis.

> **Correction (2026-10-23):** the git repository root is the parent folder `OF-Scraper-GUI/`, which also contains older versions (3.12.9, 3.14.3, 3.14.5), a `docker/` folder and an identical root-level copy of `patch_ofscraper_3.14.7_gui.py`. This report only covers `OF-Scraper-3.14.7/`.
>
> **Update (2026-10-23):** finding #4 is partly resolved. The patch was rebuilt as `20261023_gui_3_14_7_v366` from the current tree (see `PR_IMPLEMENTATION_PLAN.md`). `FILE_COUNT`, the stale `GUI_HELP.md` and the line-ending mismatch are fixed. The original `rebuild_patch_zip.py` has since been added to `OF-Scraper-3.14.7/` (not committed yet). `_build_patch.py` is still missing.

---

## What this is, in plain words

This folder is **OF-Scraper 3.14.7**, a Python command-line tool, plus a **PyQt6 desktop GUI** added on top of it.

- **The base tool** (`ofscraper/commands`, `data`, `db`, `managers`, `utils`) logs in with your cookies, calls the API, saves post data in SQLite and downloads media. That includes DRM media, through `pywidevine`.
- **The GUI** (`ofscraper/gui/`, about 66 files) is the newer part. You start it with `ofscraper --gui`.
- **The delivery method** is `patch_ofscraper_3.14.7_gui.py` (788 KB). It holds a zip of 132 files stored as base64 text. It finds your installed copy of ofscraper (pip, pipx or uv), backs up the files it will replace, and writes the new ones in. Running it with `--restore <backup dir>` puts the old files back.
- **Plugins:** `ofscraper/plugins/manager.py` loads plugins from `<config dir>/plugins/`. The two live-stream plugins in this tree (`live_stream_agora`, `live_stream_monitor`) are source code only. The patch doesn't ship them.

### How a run flows

1. `ofscraper/__main__.py` calls `ofscraper/main/open/load.py`, which reads settings and config, sets up logging and loads plugins.
2. `ofscraper/main/open/run.py` then starts either the command-line mode or the GUI.
3. In the GUI, `ofscraper/gui/utils/workflow.py` sets the same options a typed command would. It swaps the base tool's progress and live-display functions for GUI versions, then calls the normal `scraperManager.runner()`.

### Where to start reading code

| Area | Path |
|---|---|
| Startup | `ofscraper/main/open/load.py` |
| GUI app and window | `ofscraper/gui/app.py`, `ofscraper/gui/main_window.py` |
| GUI ↔ scraper bridge | `ofscraper/gui/utils/workflow.py` |
| Scrape loop | `ofscraper/commands/scraper/scraper.py` |
| Downloads | `ofscraper/commands/scraper/actions/download/` |
| Security helpers | `ofscraper/utils/hardening.py`, `ofscraper/utils/auth/cookie_allowlist.py` |
| Plugin loader | `ofscraper/plugins/manager.py` |
| Patch installer | `patch_ofscraper_3.14.7_gui.py` |

---

## Test results

| Check | Result |
|---|---|
| `pytest test/unit` (Python 3.12) | ✅ 39 passed, 4 skipped (Windows-only) |
| Older suites (`test/general`, `test/db`, `test/post`) | ❌ 23 errors while loading the tests (old imports, as the README warns) |
| *Update 2026-10-24 (PR #26):* plain `pytest` | ✅ 442 passed, 8 skipped. Repaired tests stay in place; 175 tests for removed code are in `test/legacy/` (ignored) |
| Syntax check of every module in `ofscraper/` | ✅ no errors |
| pyflakes | 157 warnings, 2 real bugs (below) |

How the tests were run: an isolated uv environment on Python 3.12 using `uv run --frozen --extra test python -m pytest test/unit -q`.

---

## Findings, most serious first

### 1. Bug: `ensure_gui_host()` fails every time it runs

- **Where:** `ofscraper/gui/utils/host_callbacks.py:151`
- **What:** the function assigns `_current_host` without a `global` line, so Python raises `UnboundLocalError`. This was reproduced directly.
- **Why nobody noticed:** all 4 callers (`main_window.py:1144`, `workflow.py:1839`, `workflow.py:2194`, `workflow.py:2464`) wrap it in `except Exception: pass`.
- **What breaks:**
  - The scraper never gets the GUI's callbacks, so `get_host()` always returns the do-nothing version.
  - The cancel check between actions in `ofscraper/commands/scraper/scraper.py:133` never fires.
  - Each model's "started" and "result" signals (`scraper.py:191`) and the "running" and "cancelling" phase signals are never sent.
- **Fix:** add `global _current_host` as the first line of `ensure_gui_host`.
- **Correction and status (2026-10-24):** in **GUI mode**, `GUIScraperManager` overrides `_execute_user_action` (`gui/utils/workflow.py:1617-1633`), so the cancel check at `scraper.py:133` and the per-model signals at `scraper.py:124/191` aren't used there. Cancel works through `_gui_cancel_event` and the forced stop. The real effect of the bug was **missing status messages and phase updates** (complete, daemon, stopped, cancelled, cancelling). **Fixed in patch `v386`** (see `PR_IMPLEMENTATION_PLAN.md`, PR #25).

### 2. Security: the GUI's built-in browser accepts outside control

- **Where:** `ofscraper/gui/app.py:7-18` and `ofscraper/gui/app.py:333-338`
- **What:** the embedded browser is started with:
  - `--remote-debugging-port` set to a random port from 9200 to 9299
  - `--remote-allow-origins=*`
  - `--disable-web-security`
- **Why it matters:**
  - Any program on the computer can connect to that port with no password. It can then control the browser that holds your OnlyFans login cookies.
  - The `*` removes the origin check that normally blocks such connections.
  - `--disable-web-security` turns off same-origin protection, which normally stops one website from reading another site's data, inside that same browser.
- **Fix:** turn these on only for the auth flow that needs them, and set an exact origin instead of `*`.

### 3. Bug in code that seems unused: missing `QWidget` import

- **Where:** `ofscraper/gui/dialogs/model_selector_dialog.py:101` and `:154`
- **What:** the file uses `QWidget` but never imports it, so opening the dialog would crash with `NameError`.
- **Note:** nothing in the codebase imports this dialog, so it can probably be deleted.

### 4. The patch file is out of sync with the source tree

- `FILE_COUNT = 87`, but the patch contains 132 files, so it prints the wrong number.
- The copy of `gui/help/GUI_HELP.md` inside the patch is older than the one in the tree. The tree has the "About & text size" section and the patch doesn't.
- The payload files use Windows line endings (CRLF) and the tree uses Linux ones (LF). Apart from that, all 131 other files match exactly.
- The tools that build the patch (`_build_patch.py`, `rebuild_patch_zip.py`) aren't in this repo. Neither are `AGENTS.md` and `UI_IMPROVEMENTS.md`, which `README.md` links to.

### 5. Build and CI setup has drifted

- `uv.lock:1110` lists only `dev, docs, ffmpeg, test`. It has no `gui` extra, so `uv run --extra gui` fails.
  - **Resolved (2026-10-24, PR #26):** `uv.lock` re-locked. The `gui` extra (PyQt6) and `pytest-check` were added, with no existing pins changed. `uv lock --check` passes.
- `.github/workflows/codecov.yml` still installs with Poetry and measures coverage with `--cov=src`. No CI workflow runs `test/unit`, which the README calls the CI gate.
  - **Resolved (2026-10-24, PR #27):** the workflow now runs from `OF-Scraper-3.14.7/` with uv (`uv sync --locked --extra test`, so a stale lock fails CI) on Python 3.11 and 3.12, runs the whole suite including `test/unit`, and measures `--cov=ofscraper`.
- The project requires Python `>=3.11,<3.14`. On 3.13, the pinned `lxml~=5.1.0` has to be compiled from source and fails without the libxml2/libxslt headers. In practice, source installs work on 3.11 and 3.12 only. (This machine's system Python is 3.14.7, which is outside the range.)
  - **Resolved (2026-10-24, PR #28):** `requires-python` is now `<3.16` with newer pins (lxml 6.1, pywidevine 1.9, uvloop 0.23, …). The full suite passes from source on 3.11, 3.12, 3.13 and 3.14.7; 3.15 is untested here. The patch install and Docker image still follow PyPI's `<3.14` limit.

### 6. Code health

- There are 541 `except Exception: pass` blocks in `ofscraper/gui/`, 80 of them in `workflow.py`. That pattern is how bug #1 stayed hidden.
- Some files are very large: `ofscraper/gui/dialogs/auth_dialog.py` has 8,631 lines and `ofscraper/gui/utils/workflow.py` has 4,055.
- `workflow.py` uses `ctypes` (`_raise_in_thread`) to force-stop the scrape thread. That's a last-resort tool and can leave things half-finished.

### 7. Minor issues

- `ofscraper/utils/hardening.py` trusts any `*.cloudfront.net` host. Anyone can rent a CloudFront address, so this check is loose.
- `ofscraper/plugins/manager.py:548` and `:565` build pip commands as text with `shell=True`, so a path containing `"` would break them.
- The repo root has an empty file named `crypto`.
- `.gitmodules` points three submodules at the same docs repo, and none of them are checked out.
- The `*.spec # ...` line in `.gitignore` has a comment on the same line, so git reads the whole line as the pattern and it matches nothing.

---

## Suggested next steps

1. Fix the one-line `global` bug in finding #1.
2. Lock down the browser debugging flags in finding #2.
3. Rebuild the patch from the current tree, and commit the build tools.
4. Run `uv lock` so the lock file includes the `gui` extra, and update `codecov.yml` to run `pytest test/unit`. *(Done: PR #26 and PR #27.)*
