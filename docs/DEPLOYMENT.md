# Deployment Guide

## Low-RAM Servers (2GB or Less)

The default Docker Compose configuration uses `replicas: 2` and `--concurrency=2` for the Celery worker, yielding 4 workers total. This is tuned for servers with ~2GB RAM.

If you have more RAM (4GB+), you can increase capacity:

```yaml
# docker-compose.yml — celery_worker
command: celery -A src.worker.app worker --loglevel=info --concurrency=4
deploy:
  replicas: 5
```

### Monitoring

- **Memory**: `docker stats` — watch bot, celery_worker, postgres, redis
- **Redis**: `docker compose exec redis redis-cli info memory`
- **Disk**: Ensure at least 10% free; Docker logs are capped at 10MB × 3 files per service

### If Parsing Stalls

1. Check Celery worker logs: `docker compose logs -f celery_worker`
2. Temporarily disable autoparse via the admin panel (`task_autoparse_enabled`)
3. Purge stuck tasks: `docker compose exec redis redis-cli FLUSHDB` (clears Redis; use with caution)
4. Restart workers: `docker compose restart celery_worker`
