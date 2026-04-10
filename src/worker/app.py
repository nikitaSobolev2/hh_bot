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
        "src.worker.tasks.recommendation_letter",
        "src.worker.tasks.cover_letter",
        "src.worker.tasks.hh_ui_apply",
        "src.worker.tasks.hh_login_assist",
        "src.worker.tasks.autorespond",
        "src.worker.tasks.negotiations_sync",
        "src.worker.tasks.task_group",
    ],
)

connect_signals(celery_app)


def _register_worker_managed_settings_loader() -> None:
    """Forked Celery workers must load DB app_settings (same as the bot process)."""

    from celery.signals import worker_process_init

    @worker_process_init.connect
    def _load_managed_settings_on_worker_start(**_kwargs: object) -> None:
        # File + structlog (``logs/hh_bot.log``); Celery's ``--loglevel`` only affects its own stdout.
        from src.core.logging import setup_logging

        setup_logging()

        import asyncio

        from src.core.db_managed_settings import load_managed_settings_to_runtime

        asyncio.run(load_managed_settings_to_runtime())


_register_worker_managed_settings_loader()

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Force Playwright applies onto ``hh_ui`` (see docker-compose ``celery_worker_hh_ui``).
    # Relying only on @task(queue=...) is not enough for routing in all Celery versions.
    task_routes={
        "hh_ui.apply_to_vacancy": {"queue": "hh_ui"},
    },
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_acks_on_failure_or_timeout=False,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    # Safety net: kill any task that exceeds 5 min; raise SoftTimeLimitExceeded at 4 min
    # so individual tasks can notify the user before the hard kill.
    task_soft_time_limit=240,
    task_time_limit=300,
    broker_transport_options={
        "visibility_timeout": 7200,
    },
    beat_schedule={
        "autoparse-dispatch-all": {
            "task": "autoparse.dispatch_all",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "hh-ui-resume-checkpoints": {
            "task": "hh_ui.periodic_resume_checkpoints",
            "schedule": crontab(minute="*/5"),
        },
    },
)
