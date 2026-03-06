from celery import Celery

from src.config import settings

celery_app = Celery(
    "hh_bot",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "src.worker.tasks.parsing",
        "src.worker.tasks.ai",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
)
