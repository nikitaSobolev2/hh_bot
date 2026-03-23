FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev pandoc && \
    rm -rf /var/lib/apt/lists/*

COPY . .
# Install app + Playwright Chromium + OS deps (required for celery_worker hh_ui.apply_to_vacancy).
RUN pip install --no-cache-dir . \
    && python -m playwright install --with-deps chromium

CMD ["python", "-m", "src"]
