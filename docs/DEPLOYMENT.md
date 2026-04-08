# Deployment Guide

## Low-RAM Servers (2GB or Less)

With the default [`docker-compose.yml`](../docker-compose.yml), **`docker compose up` runs one `celery_worker` container** with `--concurrency=2` on queue `celery`, so you get **two Celery worker processes** for that queue (not four). The `hh_ui` queue is handled separately by `celery_worker_hh_ui`; login assist uses `celery_worker_login_assist`.

`deploy.replicas` in Compose is **not** applied by `docker compose up` (only by Swarm / `docker stack deploy`). Ignore any stale `replicas` comments in older notes.

This layout is tuned for servers with ~2GB RAM.

If you have more RAM (4GB+), you can increase capacity:

- Raise concurrency in the service command, **or**
- Run multiple `celery_worker` containers:  
  `docker compose up -d --scale celery_worker=2`  
  (total general-queue processes ≈ replicas × `--concurrency`).

Example: edit the `celery_worker` command to use `--concurrency=4` instead of `2`.

### Production / shared hosts

- Set strong `POSTGRES_USER` and `POSTGRES_PASSWORD` in `.env`. The compose defaults exist for local development.
- Login assist exposes noVNC on the host port — see [HH_LOGIN_ASSIST.md](HH_LOGIN_ASSIST.md) (TLS, proxy auth, optional `LOGIN_ASSIST_REQUIRE_VNC_PASSWORD`).

### Monitoring

- **Memory**: `docker stats` — watch bot, celery_worker, postgres, redis
- **Redis**: `docker compose exec redis redis-cli info memory`
- **Disk**: Ensure at least 10% free; Docker logs are capped at 10MB × 3 files per service

### If Parsing Stalls

1. Check Celery worker logs: `docker compose logs -f celery_worker`
2. Temporarily disable autoparse via the admin panel (`task_autoparse_enabled`)
3. **Last resort — full Redis reset**: `docker compose exec redis redis-cli FLUSHDB` wipes the **entire** selected Redis logical database (Celery broker and result backend, OAuth state keys, FSM keys, circuit-breaker keys, etc.), not just one queue. Prefer restarting workers or fixing the underlying issue first.
4. Restart workers: `docker compose restart celery_worker`

### Testing in Docker

The default [`.dockerignore`](../.dockerignore) excludes `tests/`, so the runtime image does not contain the test suite. To run `pytest` inside a container, use a dedicated image build (e.g. multi-stage target or a compose override) that includes tests, or adjust `.dockerignore` for that build only.
