"""Sequential Celery task: run user-configured task group with one pinned progress entry."""

from __future__ import annotations

import contextlib
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import settings
from src.core.i18n import get_text
from src.core.logging import get_logger
from src.services.progress_service import ProgressService, create_progress_redis
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)


def _kind_short_label(kind: str, locale: str) -> str:
    key = {
        "autoparse": "progress-group-kind-autoparse-short",
        "autorespond": "progress-group-kind-autorespond-short",
        "parsing": "progress-group-kind-parsing-short",
    }.get(kind, "progress-btn-task-title-fallback")
    return get_text(key, locale)


async def _run_task_group_sequence_async(
    session_factory: async_sessionmaker[AsyncSession],
    task: HHBotTask,
    user_id: int,
    telegram_id: int,
    steps: list[dict],
) -> dict:
    if not steps:
        return {"status": "empty"}

    from src.repositories.user import UserRepository
    from src.worker.tasks.autoparse import _run_autoparse_company_async
    from src.worker.tasks.autorespond import _run_autorespond_async
    from src.worker.tasks.parsing import _run_parsing_company_async

    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if not user or user.telegram_id != telegram_id:
            return {"status": "error", "reason": "user_mismatch"}
        locale = user.language_code or "ru"

    bot = task.create_bot()
    celery_id = str(task.request.id or "")
    run_id = str(uuid.uuid4())
    pk = f"taskgroup:{run_id}"
    redis = create_progress_redis()
    svc = ProgressService(bot, telegram_id, redis, locale)
    n = len(steps)
    try:
        await svc.start_task(
            pk,
            get_text("progress-taskgroup-title", locale),
            [
                get_text("progress-taskgroup-macro-bar", locale),
                get_text("progress-taskgroup-detail-bar", locale),
            ],
            celery_task_id=celery_id,
            initial_totals=[n, 0],
            steps=[
                {
                    "id": f"tg{i}",
                    "label": _kind_short_label(str(st.get("kind") or ""), locale),
                    "state": "pending",
                }
                for i, st in enumerate(steps)
            ],
            active_step_index=0,
        )
        await svc.set_group(pk, current=1, total=n, label="")

        results: list[dict] = []
        for i, st in enumerate(steps):
            kind = st.get("kind")
            cid = st.get("company_id")
            if kind not in ("autoparse", "autorespond", "parsing") or not cid:
                results.append({"status": "skipped", "reason": "bad_step"})
                continue
            company_id = int(cid)
            await svc.set_group(
                pk,
                current=i + 1,
                total=n,
                label=_kind_short_label(str(kind), locale),
            )
            await svc.update_bar(pk, 0, i + 1, n)
            await svc.set_step_state(pk, f"tg{i}", "running")
            await svc.set_active_step_index(pk, i)

            if kind == "autoparse":
                r = await _run_autoparse_company_async(
                    session_factory,
                    task,
                    company_id,
                    user_id,
                    suppress_progress=True,
                )
            elif kind == "autorespond":
                r = await _run_autorespond_async(
                    session_factory,
                    task,
                    company_id,
                    None,
                    "task_group",
                    None,
                    pipeline_context={
                        "svc": svc,
                        "bot": bot,
                        "task_key": pk,
                        "bar_index": 1,
                        "task_group": True,
                    },
                )
            else:
                r = await _run_parsing_company_async(
                    session_factory,
                    task,
                    company_id,
                    user_id,
                    include_blacklisted=False,
                    telegram_chat_id=telegram_id,
                    suppress_progress=True,
                )
            results.append(r)
            step_status = r.get("status")
            if step_status in (
                "error",
                "negotiations_sync_failed",
                "locked",
                "deleted",
                "disabled",
                "circuit_open",
                "disabled_global",
                "company_not_found",
                "not_configured",
            ) or (isinstance(step_status, str) and step_status.startswith("circuit")):
                with contextlib.suppress(Exception):
                    await svc.cancel_task(pk)
                return {"status": "step_failed", "step": i, "result": r, "results": results}
            if kind == "autorespond":
                with contextlib.suppress(Exception):
                    await svc.clear_nested_steps(pk)
            await svc.set_step_state(pk, f"tg{i}", "done")

        await svc.update_bar(pk, 0, n, n)
        await svc.finish_task(pk)
        return {"status": "completed", "results": results}
    finally:
        with contextlib.suppress(Exception):
            await bot.session.close()


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="task_group.run_sequence",
    soft_time_limit=settings.autoparse_run_company_soft_time_limit_seconds * 10,
    time_limit=settings.autoparse_run_company_time_limit_seconds * 10,
)
def run_task_group_sequence(
    self: HHBotTask,
    user_id: int,
    telegram_id: int,
    steps_json: str,
) -> dict:
    steps = json.loads(steps_json)
    if not isinstance(steps, list):
        return {"status": "error", "reason": "invalid_steps"}
    return run_async(
        lambda sf: _run_task_group_sequence_async(
            sf, self, user_id, telegram_id, steps
        )
    )
