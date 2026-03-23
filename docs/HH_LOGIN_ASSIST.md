# HeadHunter server-side login assist (Option B)

Interactive login runs inside Playwright on a Celery worker. Users complete email/password and 2FA in **the same browser context** the bot will later use for UI apply. A plain headless container **cannot** receive keyboard input from the user, so you must provide a **graphical path** to that browser.

## Why Xvfb + noVNC (or similar)

- **Headless Chromium alone**: no way for a human to type credentials into hh.ru.
- **Recommended**: Run Chromium on a virtual framebuffer (`Xvfb`), attach **x11vnc** + **websockify** (noVNC), put the viewer behind HTTPS with a password or reverse proxy, and set **`HH_LOGIN_ASSIST_VIEWER_URL`** to that HTTPS URL (shown in Telegram while the job runs).
- **Single-tenant / dev**: one static `HH_LOGIN_ASSIST_VIEWER_URL` pointing at your noVNC endpoint; all login-assist jobs share one worker display (Celery `--concurrency=1` on queue `login_assist`).
- **Multi-tenant**: one-time tokens per job need a reverse proxy or external product (out of scope for this repo).

## Docker Compose (built-in)

The repo defines **`celery_worker_login_assist`** in [`docker-compose.yml`](../docker-compose.yml):

- **Image**: Dockerfile target `login_assist` (Xvfb, x11vnc, `novnc` static UI, `websockify`).
- **Entrypoint**: [`docker/entrypoint-login-assist.sh`](../docker/entrypoint-login-assist.sh) starts `DISPLAY :99`, VNC on `localhost:5900`, websockify on port **6080** (configurable via `WEBSOCKIFY_PORT`).
- **Celery**: `worker -Q login_assist --concurrency=1` — tasks `hh.login_assist` are **not** consumed by the default `celery_worker` (`-Q celery` only).
- **Port**: host `${LOGIN_ASSIST_NOVNC_PORT:-6080}` maps to container 6080.

### Operator checklist

1. Set in `.env` (same as bot / other workers):
   - `HH_LOGIN_ASSIST_ENABLED=true`
   - `HH_UI_APPLY_ENABLED=true`
   - `HH_TOKEN_ENCRYPTION_KEY=...`
   - `HH_LOGIN_ASSIST_HEADLESS=false` (the login-assist service also sets this in Compose; keep consistent).
2. Set **`HH_LOGIN_ASSIST_VIEWER_URL`** to a URL users can open:
   - **LAN / test**: `http://YOUR_SERVER_IP:6080/vnc.html` (match `LOGIN_ASSIST_NOVNC_PORT` if you change the mapping).
   - **Production**: HTTPS URL via reverse proxy (TLS), do not expose unauthenticated VNC to the internet.
3. Optional: **`LOGIN_ASSIST_VNC_PASSWORD`** — passed to `x11vnc -passwd` (password may appear in process list; prefer proxy auth + TLS for production).
4. Run: `docker compose up -d` (includes `celery_worker_login_assist`).
5. In Telegram: **Settings → HeadHunter accounts → Вход на сервере** (or “Server login”), open the viewer URL in a normal browser, complete hh.ru login and 2FA within the configured wait time.

## Celery routing

Task `hh.login_assist` uses queue **`login_assist`**. If no `celery_worker_login_assist` container is running, login assist jobs stay queued.

## Security

- Do not log `storage_state`, cookies, or screenshots containing credentials.
- Use TLS and access control in front of websockify; restrict by IP/VPN if possible.
- `-nopw` is used when `LOGIN_ASSIST_VNC_PASSWORD` is unset (convenient for dev only).
- Review hh.ru terms of use for automated access; datacenter IPs may be challenged ([uncertain] anti-bot).

## Fallback

Users can still link via **Playwright `storage_state` JSON file upload** in Telegram if server-side login is unavailable.
