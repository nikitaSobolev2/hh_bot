def test_celery_worker_keeps_root_logger_handlers() -> None:
    from src.worker.app import celery_app

    assert celery_app.conf.worker_hijack_root_logger is False
