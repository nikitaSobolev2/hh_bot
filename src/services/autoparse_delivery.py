DELIVER_TASK_PREFIX = "autoparse:deliver_task:"


def deliver_task_key(company_id: int, user_id: int) -> str:
    return f"{DELIVER_TASK_PREFIX}{company_id}:{user_id}"


async def revoke_scheduled_delivery_async(company_id: int, user_id: int) -> None:
    from src.core.celery_async import normalize_celery_task_id, run_sync_in_thread
    from src.core.redis import create_async_redis
    from src.worker.app import celery_app

    task_key = deliver_task_key(company_id, user_id)
    redis = create_async_redis()
    try:
        scheduled_id = await redis.get(task_key)
        if scheduled_id:
            tid = normalize_celery_task_id(scheduled_id)
            if tid:
                await run_sync_in_thread(
                    celery_app.control.revoke,
                    tid,
                    terminate=False,
                )
            await redis.delete(task_key)
    finally:
        await redis.aclose()
