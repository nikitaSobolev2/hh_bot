FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/app/ms-playwright

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev pandoc && \
    rm -rf /var/lib/apt/lists/*

COPY . .
# Install app + Playwright Chromium + OS deps (required for celery_worker hh_ui.apply_to_vacancy).
RUN pip install --no-cache-dir . \
    && python -m playwright install --with-deps chromium

# Xvfb + VNC + noVNC static files + websockify (Python) for HH login assist on workers.
FROM base AS login_assist
RUN apt-get update && apt-get install -y --no-install-recommends \
    novnc \
    x11vnc \
    xvfb \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir websockify
RUN chmod +x /app/docker/entrypoint-login-assist.sh
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# Default image: bot and Celery workers (``celery`` + optional ``hh_ui`` queues; see docker-compose.yml).
FROM base AS app
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid appuser --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["python", "-m", "src"]
