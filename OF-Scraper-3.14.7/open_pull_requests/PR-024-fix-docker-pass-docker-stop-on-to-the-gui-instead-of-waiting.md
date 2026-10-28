# PR #24: fix(docker): pass docker stop on to the GUI instead of waiting for SIGKILL

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/24
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/docker-graceful-stop` → `main`
- **Created:** 2026-10-23T03:10:15Z  ·  **Updated:** 2026-10-23T03:10:15Z
- **Draft:** False
- **Changes:** 2 files, +43 / -7

## Description

`docker stop` never stops the GUI cleanly. It always waits out the whole grace period and then SIGKILLs the container.

## Cause
`docker/entrypoint.sh` runs as PID 1 and installs no signal handler, and PID 1 ignores SIGTERM unless it has one. So the restart loop keeps running, the GUI never receives a signal, and Docker falls back to SIGKILL. Anything mid-download or mid-database-write is cut off.

Separately, the restart log always printed `code 0`, because `EXIT_CODE=$?` came after `wait ... || true`.

## Change
- **`trap` TERM/INT:** forward SIGTERM to the GUI, wait for it to exit, then stop instead of restarting it.
- **Window maximise:** the xdotool step now runs in the background, because `--sync` would block forever if the GUI exits before its window appears.
- **Exit code:** log the GUI's real exit code.
- **`docker-compose.yml`:** add `stop_grace_period: 30s`, so a cancel has time to finish. The default is 10s.

This PR only gets the signal to the GUI. On its own, the GUI then dies through Python's default SIGTERM action, which is instant but not clean. The companion PR ("cancel the scrape and quit cleanly on SIGTERM") makes it cancel cooperatively. The two are independent and merge cleanly together.

## Tested
All runs used the image built from `docker/Dockerfile` (3.14.7, patch v365) with `docker stop -t 30`.

| | Idle GUI | During a scrape |
|---|---|---|
| `main` | 30.3s, SIGKILL (137) | 30.4s, SIGKILL; 14 `.part` files left |
| this PR | 0.3s, GUI exit 143 | 0.3s, GUI exit 143; 1 `.part` left |
| this PR + GUI PR | 0.5s, GUI exit 0 (3/3 runs) | 1.6s, GUI exit 0; scrape cancelled cooperatively, 0 `.part` left |

In every run the database passed `integrity_check`, and every file it records as downloaded exists with the recorded size.

## Files changed

- `docker-compose.yml`
- `docker/entrypoint.sh`

## Code changes (full diff)

```diff
diff --git a/docker-compose.yml b/docker-compose.yml
index 15f54d3..510279e 100644
--- a/docker-compose.yml
+++ b/docker-compose.yml
@@ -71,6 +71,9 @@ services:
     # ports:  # Not used with network_mode: host — remove the above line to restore
     #   - "6699:6699"
     restart: unless-stopped
+    # docker stop asks OF-Scraper to cancel the current scrape and exit; give
+    # it time to finish in-flight work before Docker falls back to SIGKILL.
+    stop_grace_period: 30s
     ulimits:
       nofile:
         soft: 65536
diff --git a/docker/entrypoint.sh b/docker/entrypoint.sh
index 570f88e..3385e8f 100644
--- a/docker/entrypoint.sh
+++ b/docker/entrypoint.sh
@@ -12,6 +12,22 @@ CRASH_DIR="${CONFIG_HOME}/gui_crash_logs"
 DEVICE_DIR="${CONFIG_HOME}/device"
 LOG_FILE="${LOG_DIR}/gui-docker.log"
 
+# ── Stop cleanly on docker stop ──────────────────────────────────────────────
+# This script is PID 1, and PID 1 ignores SIGTERM unless it installs a handler,
+# so without this trap `docker stop` waits out the grace period and SIGKILLs
+# the GUI mid-download. Pass the signal on to the GUI, wait for it to finish,
+# and don't restart it.
+STOPPING=0
+GUI_PID=""
+stop_container() {
+    STOPPING=1
+    echo "[entrypoint] $(date -Is) stop requested — asking OF-Scraper to exit" | tee -a "${LOG_FILE}"
+    if [ -n "${GUI_PID}" ]; then
+        kill -TERM "${GUI_PID}" 2>/dev/null || true
+    fi
+}
+trap stop_container TERM INT
+
 # ── Persist dirs on the mounted config volume ────────────────────────────────
 mkdir -p "${LOG_DIR}" "${CRASH_DIR}" "${DEVICE_DIR}"
 
@@ -68,14 +84,31 @@ while true; do
     DISPLAY=${DISPLAY} nice -n -10 python -m ofscraper ${CMD_ARGS} >>"${LOG_FILE}" 2>&1 &
     GUI_PID=$!
 
-    # Wait for the window to appear then maximize it to fill the virtual desktop
-    sleep 4
-    DISPLAY=${DISPLAY} xdotool search --sync --onlyvisible --name "OF-Scraper" \
-        windowactivate --sync %@ windowmaximize %@ || true
+    # Wait for the window to appear then maximize it to fill the virtual desktop.
+    # In the background: --sync would block forever if the GUI exits first.
+    (
+        sleep 4
+        DISPLAY=${DISPLAY} xdotool search --sync --onlyvisible --name "OF-Scraper" \
+            windowactivate --sync %@ windowmaximize %@ || true
+    ) &
+
+    # A trapped signal interrupts `wait`; keep waiting while the GUI shuts down.
+    EXIT_CODE=0
+    wait "${GUI_PID}" || EXIT_CODE=$?
+    while kill -0 "${GUI_PID}" 2>/dev/null; do
+        EXIT_CODE=0
+        wait "${GUI_PID}" || EXIT_CODE=$?
+    done
 
-    wait "${GUI_PID}" || true
-    EXIT_CODE=$?
+    if [ "${STOPPING}" = 1 ]; then
+        echo "[entrypoint] $(date -Is) ofscraper exited (code ${EXIT_CODE}) — stopping" | tee -a "${LOG_FILE}"
+        exit 0
+    fi
     echo "[entrypoint] $(date -Is) ofscraper exited (code ${EXIT_CODE}) — restarting in ${GUI_RESTART_DELAY}s..." \
         | tee -a "${LOG_FILE}"
-    sleep "${GUI_RESTART_DELAY}"
+    sleep "${GUI_RESTART_DELAY}" &
+    wait $! || true
+    if [ "${STOPPING}" = 1 ]; then
+        exit 0
+    fi
 done
\ No newline at end of file
```
