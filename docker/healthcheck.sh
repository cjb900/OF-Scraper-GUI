#!/bin/bash
# Docker HEALTHCHECK for the GUI image.
# MODE=cli has no display or noVNC: report healthy (the container stops when
# the CLI exits). MODE=gui: the X display socket must exist and noVNC must
# accept connections on NOVNC_PORT.
if [ "${MODE:-gui}" = "cli" ]; then
    exit 0
fi
if [ ! -S /tmp/.X11-unix/X1 ]; then
    echo "no X display socket"
    exit 1
fi
if ! (exec 3<>"/dev/tcp/127.0.0.1/${NOVNC_PORT:-6699}") 2>/dev/null; then
    echo "noVNC not answering on ${NOVNC_PORT:-6699}"
    exit 1
fi
exit 0
