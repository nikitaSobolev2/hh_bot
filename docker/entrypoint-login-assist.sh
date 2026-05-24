#!/bin/sh
# Start Xvfb + x11vnc + websockify (noVNC), then exec Celery for queue login_assist.
# Requires target login_assist image (see Dockerfile). Do not expose VNC without TLS/password in production.
# Runs as root so bind-mounted ./logs can be chowned for appuser (uid 1000).

set -e

if [ "$(id -u)" -eq 0 ]; then
  mkdir -p /app/logs
  chown -R appuser:appuser /app/logs 2>/dev/null || chmod -R a+rwX /app/logs 2>/dev/null || true
fi

case "${LOGIN_ASSIST_REQUIRE_VNC_PASSWORD:-}" in
  true|1)
    if [ -z "${LOGIN_ASSIST_VNC_PASSWORD:-}" ]; then
      echo "LOGIN_ASSIST_REQUIRE_VNC_PASSWORD is enabled but LOGIN_ASSIST_VNC_PASSWORD is empty — refusing to start without VNC password." >&2
      exit 1
    fi
    ;;
esac

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

if [ "$(id -u)" -eq 0 ]; then
  if command -v runuser >/dev/null 2>&1; then
    exec runuser -u appuser -- "$@"
  fi
  exec su appuser -s /bin/sh -c 'exec "$@"' sh "$@"
fi
exec "$@"
