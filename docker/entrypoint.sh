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

# ── Persist dirs on the mounted config volume ────────────────────────────────
mkdir -p "${LOG_DIR}" "${CRASH_DIR}" "${DEVICE_DIR}"

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
    {
        echo "============================================================"
        echo "[entrypoint] $(date -Is) starting: ofscraper ${CMD_ARGS}"
        echo "============================================================"
    } >> "${LOG_FILE}"

    # nice -n -10: give the GUI higher CPU priority than QtWebEngine/Chromium subprocesses
    # stdout/stderr tee onto the mounted config volume for crash correlation with breadcrumbs.
    DISPLAY=${DISPLAY} nice -n -10 python -m ofscraper ${CMD_ARGS} >>"${LOG_FILE}" 2>&1 &
    GUI_PID=$!

    # Wait for the window to appear then maximize it to fill the virtual desktop
    sleep 4
    DISPLAY=${DISPLAY} xdotool search --sync --onlyvisible --name "OF-Scraper" \
        windowactivate --sync %@ windowmaximize %@ || true

    wait "${GUI_PID}" || true
    EXIT_CODE=$?
    echo "[entrypoint] $(date -Is) ofscraper exited (code ${EXIT_CODE}) — restarting in ${GUI_RESTART_DELAY}s..." \
        | tee -a "${LOG_FILE}"
    sleep "${GUI_RESTART_DELAY}"
done