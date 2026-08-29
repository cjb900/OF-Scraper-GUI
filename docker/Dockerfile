FROM ubuntu:24.04

# Build arg: which version of ofscraper + GUI patch to use.
# Must match one of the OF-Scraper-X.X.X/patch_ofscraper_X.X.X_gui.py files.
ARG GUI_PATCH_VERSION=3.14.7

ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:1 \
    SCREEN_WIDTH=2048 \
    SCREEN_HEIGHT=1536 \
    SCREEN_DEPTH=24 \
    VNC_PORT=5900 \
    NOVNC_PORT=6699 \
    GUI_RESTART_DELAY=5
# CLI args appended to "ofscraper --gui" at startup.
# Leave blank to open the GUI without auto-starting a scrape.
# Example: --daemon 120 --username ALL --sub-status active --posts all --discord low
ENV GUI_ARGS=""

# ── System packages ──────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Python
    python3 python3-venv python3-dev \
    # PyQt6 from apt — uses Ubuntu's system Qt, correctly linked to xcb libs
    python3-pyqt6 python3-pyqt6.qtwebengine \
    # Virtual display
    xvfb \
    # Minimal window manager so Qt windows don't get orphaned
    fluxbox \
    # VNC server
    x11vnc \
    # noVNC dependencies
    novnc websockify \
    # Qt xcb platform dependencies
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
    libxcb-render-util0 libxcb-xinerama0 libxcb-xkb1 libxkbcommon-x11-0 \
    libegl1 libgl1 libfontconfig1 libdbus-1-3 \
    # Audio stub (prevents Qt from logging warnings)
    libasound2t64 \
    # ffmpeg — installed natively so all shared libraries (libavdevice etc.) are present.
    # A host bind-mount of /usr/bin/ffmpeg won't work because the host binary links
    # against host libraries that don't exist inside the container, causing DRM
    # decryption to silently fail and leaving every video stuck as a .part file.
    ffmpeg \
    # Utilities
    curl wget ca-certificates git xdotool \
    && rm -rf /var/lib/apt/lists/*

# ── Python virtual environment ────────────────────────────────────────────────
# --system-site-packages lets the venv use the apt-installed python3-pyqt6
RUN python3 -m venv --system-site-packages /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# ── Install ofscraper inside the venv ─────────────────────────────────────────
# PyQt6 is provided by the system package above — skip it here
RUN pip install --no-cache-dir ofscraper==${GUI_PATCH_VERSION}

# ── Copy all available GUI patches and apply the selected one ─────────────────
WORKDIR /opt/ofscraper-gui
COPY OF-Scraper-3.12.9/patch_ofscraper_3.12.9_gui.py ./
COPY OF-Scraper-3.14.3/patch_ofscraper_3.14.3_gui.py ./
COPY OF-Scraper-3.14.5/patch_ofscraper_3.14.5_gui.py ./
COPY OF-Scraper-3.14.7/patch_ofscraper_3.14.7_gui.py ./

RUN python patch_ofscraper_${GUI_PATCH_VERSION}_gui.py -y --skip-pyqt6 \
    && python -c "from ofscraper.gui.patch_version import PATCH_ID; print(f'Applied GUI patch: {PATCH_ID}')"

# ── noVNC setup ───────────────────────────────────────────────────────────────
# Default to resize=remote so the virtual desktop resizes to match the browser
# viewport rather than scaling a fixed resolution down.
RUN printf '<!DOCTYPE html>\n<html><head>\n<meta http-equiv="refresh" content="0;url=vnc.html?autoconnect=true&resize=remote">\n</head></html>\n' \
    > /usr/share/novnc/index.html

# ── Entrypoint script ─────────────────────────────────────────────────────────
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 6699

ENTRYPOINT ["/entrypoint.sh"]