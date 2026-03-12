from celery import Celery
from celery.schedules import crontab

from src.config import settings
from src.worker.signals import connect_signals

celery_app = Celery(
    "hh_bot",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "src.worker.tasks.parsing",
        "src.worker.tasks.ai",
        "src.worker.tasks.autoparse",
        "src.worker.tasks.interviews",
        "src.worker.tasks.interview_prep",
        "src.worker.tasks.achievements",
        "src.worker.tasks.interview_qa",
        "src.worker.tasks.vacancy_summary",
        "src.worker.tasks.work_experience",
    ],
)

connect_signals(celery_app)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_acks_on_failure_or_timeout=False,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    broker_transport_options={
        "visibility_timeout": 7200,
    },
    beat_schedule={
        "autoparse-dispatch-all": {
            "task": "autoparse.dispatch_all",
            "schedule": crontab(minute=0, hour="*/6"),
        },
    },
)
