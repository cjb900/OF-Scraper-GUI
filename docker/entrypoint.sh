#!/bin/bash
set -e

DISPLAY=:1
SCREEN="${SCREEN_WIDTH:-1600}x${SCREEN_HEIGHT:-900}x${SCREEN_DEPTH:-24}"
NOVNC_PORT="${NOVNC_PORT:-6699}"
VNC_PORT="${VNC_PORT:-5900}"
GUI_RESTART_DELAY="${GUI_RESTART_DELAY:-5}"
CONFIG_HOME="${OFSCRAPER_CONFIG_HOME:-/root/.config/ofscraper}"
LOG_DIR="${CONFIG_HOME}/logging"
CRASH_DIR="${CONFIG_HOME}/gui_crash_logs"
DEVICE_DIR="${CONFIG_HOME}/device"
LOG_FILE="${LOG_DIR}/gui-docker.log"

# ── Stop cleanly on docker stop ──────────────────────────────────────────────
# This script is PID 1, and PID 1 ignores SIGTERM unless it installs a handler,
# so without this trap `docker stop` waits out the grace period and SIGKILLs
# the GUI mid-download. Pass the signal on to the GUI, wait for it to finish,
# and don't restart it.
STOPPING=0
GUI_PID=""
stop_container() {
    STOPPING=1
    echo "[entrypoint] $(date -Is) stop requested — asking OF-Scraper to exit" | tee -a "${LOG_FILE}"
    if [ -n "${GUI_PID}" ]; then
        kill -TERM "${GUI_PID}" 2>/dev/null || true
    fi
}
trap stop_container TERM INT

# ── Persist dirs on the mounted config volume ────────────────────────────────
mkdir -p "${LOG_DIR}" "${CRASH_DIR}" "${DEVICE_DIR}"

# ── CLI mode: run ofscraper without the GUI, display or VNC ──────────────────
# MODE=cli runs `python -m ofscraper` with the container's command arguments,
# or CLI_ARGS if there are none. Meant for --daemon runs: a one-shot run exits
# and `restart: unless-stopped` would start it again, so use
# `docker compose run --rm` for those.
if [ "${MODE:-gui}" = "cli" ]; then
    if [ "$#" -eq 0 ] && [ -n "${CLI_ARGS:-}" ]; then
        # word-split like GUI_ARGS
        set -- ${CLI_ARGS}
    fi
    if [ -t 0 ]; then
        # Interactive (`docker compose run`): the CLI's menus need the
        # terminal, which a background process can't read from.
        echo "[entrypoint] CLI mode (interactive): ofscraper $*"
        exec python -m ofscraper "$@"
    fi
    if [ "$#" -eq 0 ]; then
        echo "[entrypoint] MODE=cli needs CLI_ARGS (e.g. --daemon 120 --username ALL --posts all --action download)," >&2
        echo "[entrypoint] or run it interactively: docker compose run --rm -e MODE=cli ofscraper-gui" >&2
        exit 2
    fi
    echo "[entrypoint] CLI mode: ofscraper $*"
    # Not exec: keep this script as PID 1 so docker stop (SIGTERM) and
    # `docker kill --signal=USR1` (daemon: start the next run now) reach the
    # CLI through the traps.
    trap '[ -n "${GUI_PID}" ] && kill -USR1 "${GUI_PID}" 2>/dev/null || true' USR1
    if [ "${STOPPING}" = 1 ]; then
        echo "[entrypoint] $(date -Is) stop requested before the CLI started — stopping"
        exit 0
    fi
    python -m ofscraper "$@" &
    GUI_PID=$!
    if [ "${STOPPING}" = 1 ]; then
        kill -TERM "${GUI_PID}" 2>/dev/null || true
    fi
    # A trapped signal interrupts `wait`; keep waiting until the CLI exits.
    EXIT_CODE=0
    wait "${GUI_PID}" || EXIT_CODE=$?
    while kill -0 "${GUI_PID}" 2>/dev/null; do
        EXIT_CODE=0
        wait "${GUI_PID}" || EXIT_CODE=$?
    done
    echo "[entrypoint] $(date -Is) ofscraper exited (code ${EXIT_CODE})"
    exit "${EXIT_CODE}"
fi

# ── Clean up stale Xvfb lock files from a previous container run ─────────────
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1

echo "[entrypoint] Starting virtual display ${SCREEN} on ${DISPLAY}"
Xvfb "${DISPLAY}" -screen 0 "${SCREEN}" &
XVFB_PID=$!

# Give Xvfb a moment to start
sleep 2

echo "[entrypoint] Starting window manager"
DISPLAY=${DISPLAY} fluxbox &>/dev/null &

echo "[entrypoint] Starting x11vnc on :${VNC_PORT}"
# -noxdamage: skip XDamage extension which is unreliable in Xvfb and causes missed repaints
# -wait 5:    poll every 5 ms instead of the 75 ms default for snappier input response
# -defer 0:   send screen updates immediately rather than batching them
x11vnc -display "${DISPLAY}" -nopw -forever -shared -rfbport "${VNC_PORT}" -xrandr \
       -noxdamage -wait 5 -defer 0 &>/dev/null &

echo "[entrypoint] Starting noVNC on port ${NOVNC_PORT}"
websockify --web=/usr/share/novnc "${NOVNC_PORT}" "localhost:${VNC_PORT}" &>/dev/null &

# Give noVNC a moment to bind the port before the GUI starts
sleep 1

# Build the ofscraper command — append GUI_ARGS if set
CMD_ARGS="--gui"
if [ -n "${GUI_ARGS:-}" ]; then
    CMD_ARGS="$CMD_ARGS $GUI_ARGS"
fi

echo "[entrypoint] Config:  ${CONFIG_HOME}"
echo "[entrypoint] CDM dir: ${DEVICE_DIR}  (put client_id.bin + private_key.pem here, or mount host keys)"
echo "[entrypoint] Logs:    ${LOG_FILE}"
echo "[entrypoint] Crash:   ${CRASH_DIR}"
echo "[entrypoint] noVNC:   http://<host>:${NOVNC_PORT}/"
echo "[entrypoint] Launching OF-Scraper GUI (auto-restart on exit): ofscraper ${CMD_ARGS}"

# Restart loop: if the GUI process dies (crash or quit), bring it back so the
# container remains usable over noVNC without a full docker compose restart.
while true; do
    # docker stop before the GUI (re)starts: nothing to wait for
    if [ "${STOPPING}" = 1 ]; then
        echo "[entrypoint] $(date -Is) stop requested before the GUI started — stopping" | tee -a "${LOG_FILE}"
        exit 0
    fi
    {
        echo "============================================================"
        echo "[entrypoint] $(date -Is) starting: ofscraper ${CMD_ARGS}"
        echo "============================================================"
    } >> "${LOG_FILE}"

    # nice -n -10: give the GUI higher CPU priority than QtWebEngine/Chromium subprocesses
    # stdout/stderr tee onto the mounted config volume for crash correlation with breadcrumbs.
    DISPLAY=${DISPLAY} nice -n -10 python -m ofscraper ${CMD_ARGS} >>"${LOG_FILE}" 2>&1 &
    GUI_PID=$!
    # a stop that arrived while the GUI was being launched had no PID to signal
    if [ "${STOPPING}" = 1 ]; then
        kill -TERM "${GUI_PID}" 2>/dev/null || true
    fi

    # Wait for the window to appear then maximize it to fill the virtual desktop.
    # In the background: --sync would block forever if the GUI exits first.
    (
        sleep 4
        DISPLAY=${DISPLAY} xdotool search --sync --onlyvisible --name "OF-Scraper" \
            windowactivate --sync %@ windowmaximize %@ || true
    ) &

    # A trapped signal interrupts `wait`; keep waiting while the GUI shuts down.
    EXIT_CODE=0
    wait "${GUI_PID}" || EXIT_CODE=$?
    while kill -0 "${GUI_PID}" 2>/dev/null; do
        EXIT_CODE=0
        wait "${GUI_PID}" || EXIT_CODE=$?
    done

    if [ "${STOPPING}" = 1 ]; then
        echo "[entrypoint] $(date -Is) ofscraper exited (code ${EXIT_CODE}) — stopping" | tee -a "${LOG_FILE}"
        exit 0
    fi
    echo "[entrypoint] $(date -Is) ofscraper exited (code ${EXIT_CODE}) — restarting in ${GUI_RESTART_DELAY}s..." \
        | tee -a "${LOG_FILE}"
    sleep "${GUI_RESTART_DELAY}" &
    wait $! || true
    if [ "${STOPPING}" = 1 ]; then
        exit 0
    fi
done