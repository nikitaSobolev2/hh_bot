# HeadHunter server-side login assist (Option B)

Interactive login runs inside Playwright on a Celery worker. Users complete email/password and 2FA in **the same browser context** the bot will later use for UI apply. A plain headless container **cannot** receive keyboard input from the user, so you must provide a **graphical path** to that browser.

## Why Xvfb + noVNC (or similar)

- **Headless Chromium alone**: no way for a human to type credentials into hh.ru.
- **Recommended**: Run Chromium on a virtual framebuffer (`Xvfb`), attach **x11vnc** + **websockify** (noVNC), put the viewer behind HTTPS with a password or one-time token, and send the user that URL via Telegram.
- **Single-tenant / dev**: one static `HH_LOGIN_ASSIST_VIEWER_URL` pointing at your noVNC endpoint; all login-assist jobs share one worker display (serialize with Celery concurrency=1 for that queue).
- **Multi-tenant**: you need a reverse proxy that maps one-time tokens to the correct VNC port per job (out of scope for this repo; use a dedicated sidecar or external product).

## Example layout

1. **Worker image** (extend app image or separate Dockerfile):
   - `xvfb`, `x11vnc`, `websockify` (or `novnc` package), `chromium` (Playwright already installs Chromium).
2. **Entrypoint** (conceptual):
   - Start `Xvfb :99 -screen 0 1280x1024x24`.
   - `export DISPLAY=:99`.
   - Start `x11vnc` on a port, front it with websockify/noVNC on HTTPS (often behind nginx with TLS).
3. **Celery**:
   - Run a **dedicated** worker for queue `login_assist` with `--concurrency=1` so only one browser uses the display at a time.
   - Set `HH_LOGIN_ASSIST_HEADLESS=false` and ensure `DISPLAY=:99` in that service’s environment.

## Docker Compose

See `docker-compose.login-assist.example.yml` in the repo root for a **reference** service override. Adjust hostnames, TLS certificates, and firewall rules for your environment.

## Security

- Do not log `storage_state`, cookies, or screenshots containing credentials.
- Use short-lived viewer URLs and passwords; restrict noVNC by IP/VPN if possible.
- Review hh.ru terms of use for automated access; datacenter IPs may be challenged ([uncertain] anti-bot).

## Fallback

Users can still link via **Playwright `storage_state` JSON file upload** in Telegram if server-side login is unavailable.
