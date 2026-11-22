#!/bin/bash
set -e

DISPLAY=:1
SCREEN_WIDTH="${SCREEN_WIDTH:-1920}"
SCREEN_HEIGHT="${SCREEN_HEIGHT:-1080}"
SCREEN_DEPTH="${SCREEN_DEPTH:-24}"
SCREEN="${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}"
NOVNC_PORT="${NOVNC_PORT:-6699}"
VNC_PORT="${VNC_PORT:-5900}"
GUI_RESTART_DELAY="${GUI_RESTART_DELAY:-5}"
# OF-Scraper runs as root and always reads ~/.config/ofscraper
CONFIG_HOME="/root/.config/ofscraper"
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

# Split an options string the way a shell command line is read: quotes keep a
# value with spaces together and nothing is glob-expanded (as with
# ONLYFANS_GUI_ARGS / FANSLY_GUI_ARGS). Fills the array named by $1.
split_args() {
    local -n _out="$1"
    _out=()
    local item
    while IFS= read -r -d '' item; do
        _out+=("$item")
    done < <(python3 -I -c 'import shlex, sys
for a in shlex.split(sys.argv[1]):
    sys.stdout.write(a + "\0")' "$2")
}

# ── Warn when downloads would land outside every volume ──────────────────────
# A site whose Save Location isn't on a mounted folder writes into the
# container's own layer: the scrape works, and the files are gone when the
# container is recreated.
check_save_locations() {
    python3 -I - "${CONFIG_HOME}" <<'PY' || true
import json, os, sys

home = sys.argv[1]

def mounts():
    # mount point -> True when it keeps files after the container is
    # recreated. A tmpfs mounted from its own root (--tmpfs, compose tmpfs:)
    # doesn't; a bind mount of a host folder does, even from a host tmpfs.
    found = {}
    with open("/proc/self/mountinfo") as f:
        for line in f:
            left, _, right = line.partition(" - ")
            fields = left.split()
            root, point = fields[3], fields[4].replace("\\040", " ")
            found[point] = not (right.split()[0] == "tmpfs" and root == "/")
    return found

def save_location(path, site):
    default = os.path.join("/root/Data/ofscraper", site)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        return None
    data = data.get("config") or data
    value = (data.get("file_options") or {}).get("save_location") or data.get("save_location")
    return os.path.expanduser(value) if value else default

table = mounts()
for site, path in (("OnlyFans", os.path.join(home, "config.json")),
                   ("Fansly", os.path.join(home, "fansly", "config.json"))):
    where = save_location(path, site)
    if not where:
        continue
    real = os.path.realpath(where)
    point = max((m for m in table if real == m or real.startswith(m.rstrip("/") + "/")), key=len, default="/")
    if point == "/" or not table.get(point, False):
        print(f"[entrypoint] WARNING: {site} saves to {where}, which is not on a mounted volume. "
              "Downloads there are lost when the container is recreated: mount that folder, or set "
              f"{site}'s Save Location (Configuration > File Options) to a mounted folder.")
PY
}

# ── CLI mode: run ofscraper without the GUI, display or VNC ──────────────────
# MODE=cli runs `python -m ofscraper` with the container's command arguments,
# or CLI_ARGS if there are none. Meant for --daemon runs: a one-shot run exits
# and `restart: unless-stopped` would start it again, so use
# `docker compose run --rm` for those.
if [ "${MODE:-gui}" = "cli" ]; then
    if [ "$#" -eq 0 ] && [ -n "${CLI_ARGS:-}" ]; then
        split_args CLI_ARRAY "${CLI_ARGS}"
        set -- "${CLI_ARRAY[@]}"
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
    check_save_locations
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

# ── Clean up stale X lock files from a previous container run ────────────────
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1

# TigerVNC's Xvnc is the virtual display and the VNC server in one.
# SCREEN_WIDTH x SCREEN_HEIGHT is only the starting size: noVNC (resize=remote)
# and VNC viewers set to "resize remote session" change it to fit their window.
# -localhost=0 keeps raw VNC reachable on VNC_PORT. With VNC_PASSWORD set, both
# noVNC and raw VNC ask for it; without it there is no password.
VNC_SECURITY=(-SecurityTypes None)
if [ -n "${VNC_PASSWORD:-}" ]; then
    PASSWORD_FILE=/tmp/.vncpasswd
    VNCPASSWD="$(command -v tigervncpasswd || command -v vncpasswd || true)"
    if [ -z "${VNCPASSWD}" ]; then
        echo "[entrypoint] VNC_PASSWORD is set but vncpasswd isn't installed; refusing to start without the password" >&2
        exit 1
    fi
    (umask 077; printf '%s\n' "${VNC_PASSWORD}" | "${VNCPASSWD}" -f > "${PASSWORD_FILE}")
    VNC_SECURITY=(-SecurityTypes VncAuth -PasswordFile "${PASSWORD_FILE}")
    if [ "${#VNC_PASSWORD}" -gt 8 ]; then
        echo "[entrypoint] Note: VNC uses only the first 8 characters of VNC_PASSWORD"
    fi
    echo "[entrypoint] VNC password: on"
else
    echo "[entrypoint] VNC password: off (set VNC_PASSWORD to require one)"
fi
echo "[entrypoint] Starting virtual display + VNC server ${SCREEN} on ${DISPLAY}, VNC port ${VNC_PORT}"
Xtigervnc "${DISPLAY}" -geometry "${SCREEN_WIDTH}x${SCREEN_HEIGHT}" \
    -depth "${SCREEN_DEPTH}" -rfbport "${VNC_PORT}" -localhost=0 \
    "${VNC_SECURITY[@]}" -AlwaysShared -AcceptSetDesktopSize=1 \
    -desktop "OF-Scraper" &>/dev/null &

# Wait until the display accepts clients (up to 15 s) instead of a fixed sleep
for _ in $(seq 1 30); do
    [ -S /tmp/.X11-unix/X1 ] && break
    sleep 0.5
done
if [ ! -S /tmp/.X11-unix/X1 ]; then
    echo "[entrypoint] WARNING: the virtual display didn't start within 15 s" >&2
fi

echo "[entrypoint] Starting window manager"
DISPLAY=${DISPLAY} fluxbox &>/dev/null &

echo "[entrypoint] Starting noVNC on port ${NOVNC_PORT}"
websockify --web=/usr/share/novnc "${NOVNC_PORT}" "localhost:${VNC_PORT}" &>/dev/null &

# Wait for noVNC to accept connections (up to 10 s)
for _ in $(seq 1 20); do
    (exec 3<>"/dev/tcp/127.0.0.1/${NOVNC_PORT}") 2>/dev/null && break
    sleep 0.5
done

# Build the ofscraper command — append GUI_ARGS if set
split_args GUI_ARRAY "${GUI_ARGS:-}"
CMD_ARGS=(--gui "${GUI_ARRAY[@]}")

check_save_locations

echo "[entrypoint] Config:  ${CONFIG_HOME}"
echo "[entrypoint] CDM dir: ${DEVICE_DIR}  (put client_id.bin + private_key.pem here, or mount host keys)"
echo "[entrypoint] Logs:    ${LOG_FILE}"
echo "[entrypoint] Crash:   ${CRASH_DIR}"
echo "[entrypoint] noVNC:   http://<host>:${NOVNC_PORT}/"
echo "[entrypoint] Launching OF-Scraper GUI (auto-restart on exit): ofscraper ${CMD_ARGS[*]}"
if [ -n "${ONLYFANS_GUI_ARGS:-}" ]; then
    echo "[entrypoint] OnlyFans start-up: ${ONLYFANS_GUI_ARGS}"
fi
if [ -n "${FANSLY_GUI_ARGS:-}" ]; then
    echo "[entrypoint] Fansly start-up:   ${FANSLY_GUI_ARGS}"
fi

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
        echo "[entrypoint] $(date -Is) starting: ofscraper ${CMD_ARGS[*]}"
        echo "============================================================"
    } >> "${LOG_FILE}"

    # stdout/stderr go to the mounted config volume for crash correlation with breadcrumbs.
    DISPLAY=${DISPLAY} python -m ofscraper "${CMD_ARGS[@]}" >>"${LOG_FILE}" 2>&1 &
    GUI_PID=$!
    # a stop that arrived while the GUI was being launched had no PID to signal
    if [ "${STOPPING}" = 1 ]; then
        kill -TERM "${GUI_PID}" 2>/dev/null || true
    fi

    # Wait for the window to appear, then maximize it. Fluxbox keeps a maximized
    # window filling the screen when noVNC resizes the desktop.
    # In the background: --sync would block forever if the GUI exits first.
    (
        sleep 4
        DISPLAY=${DISPLAY} xdotool search --sync --onlyvisible --name "OF-Scraper" \
            windowactivate --sync %@ >/dev/null 2>&1 || true
        DISPLAY=${DISPLAY} wmctrl -r "OF-Scraper" -b add,maximized_vert,maximized_horz || true
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