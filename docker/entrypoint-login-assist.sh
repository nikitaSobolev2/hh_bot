#!/bin/sh
# Start Xvfb + x11vnc + websockify (noVNC), then exec Celery for queue login_assist.
# Requires target login_assist image (see Dockerfile). Do not expose VNC without TLS/password in production.

set -e

export DISPLAY="${DISPLAY:-:99}"

Xvfb "${DISPLAY}" -screen 0 1280x1024x24 &
sleep 2

WEBSOCKIFY_PORT="${WEBSOCKIFY_PORT:-6080}"
NOVNC_WEB="${NOVNC_WEB:-/usr/share/novnc}"

if [ -n "$LOGIN_ASSIST_VNC_PASSWORD" ]; then
  # Password may appear in process list; prefer reverse-proxy auth for production.
  x11vnc -display "${DISPLAY}" -forever -shared -listen localhost -rfbport 5900 \
    -passwd "$LOGIN_ASSIST_VNC_PASSWORD" &
else
  x11vnc -display "${DISPLAY}" -forever -shared -listen localhost -rfbport 5900 -nopw &
fi

# noVNC static UI + WebSocket bridge to localhost VNC
websockify --web="${NOVNC_WEB}" "${WEBSOCKIFY_PORT}" localhost:5900 &
sleep 1

exec "$@"
