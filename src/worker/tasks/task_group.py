"""Sequential Celery task: run user-configured task group with one pinned progress entry."""

from __future__ import annotations

import contextlib
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import settings
from src.core.i18n import get_text
from src.core.logging import get_logger
from src.services.task_checkpoint import TaskCheckpointService, create_checkpoint_redis
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


def _step_display_label(step: dict, locale: str) -> str:
    kind_label = _kind_short_label(str(step.get("kind") or ""), locale)
    title = str(step.get("display_title") or "").strip()
    return f"{kind_label} — {title}" if title else kind_label


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _build_completion_summary_lines(results: list[dict], locale: str) -> list[str]:
    parsed = sum(_safe_int(r.get("vacancies_count")) for r in results)
    autoparse_found = sum(_safe_int(r.get("new_count")) for r in results)
    responded = sum(_safe_int(r.get("queued")) for r in results)
    failed = sum(_safe_int(r.get("failed")) for r in results)
    employer_tests = sum(_safe_int(r.get("employer_tests")) for r in results)
    synced = sum(_safe_int((r.get("negotiations_sync") or {}).get("inserted")) for r in results)

    lines: list[str] = []
    if parsed > 0:
        lines.append(get_text("progress-summary-parsed", locale, count=parsed))
    if autoparse_found > 0:
        lines.append(get_text("progress-summary-autoparse-found", locale, count=autoparse_found))
    if synced > 0:
        lines.append(get_text("progress-summary-synced", locale, count=synced))
    if responded > 0:
        lines.append(get_text("progress-summary-responded", locale, count=responded))
    if employer_tests > 0:
        lines.append(get_text("progress-summary-tests", locale, count=employer_tests))
    if failed > 0:
        lines.append(get_text("progress-summary-errors", locale, count=failed))
    return lines


async def _run_task_group_sequence_async(
    session_factory: async_sessionmaker[AsyncSession],
    task: HHBotTask,
    user_id: int,
    telegram_id: int,
    steps: list[dict],
    *,
    task_key: str | None = None,
    resume_from_index: int = 0,
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
    redis = create_progress_redis()
    checkpoint_redis = create_checkpoint_redis()
    checkpoint = TaskCheckpointService(checkpoint_redis)
    pk = task_key or f"taskgroup:{uuid.uuid4()}"
    svc = ProgressService(bot, telegram_id, redis, locale)
    n = len(steps)
    try:
        start_index = max(0, min(_safe_int(resume_from_index), n))
        restored_results: list[dict] = []
        restored = await checkpoint.load_task_group_state(telegram_id, pk)
        if restored:
            start_index = max(
                start_index,
                min(_safe_int(restored.get("resume_from_index")), n),
            )
            restored_results = [
                item for item in restored.get("results", []) if isinstance(item, dict)
            ]

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
                    "label": _step_display_label(st, locale),
                    "state": "done" if i < start_index else "pending",
                }
                for i, st in enumerate(steps)
            ],
            active_step_index=min(start_index, max(n - 1, 0)),
        )
        await svc.update_bar(pk, 0, start_index, n)
        if start_index < n:
            await svc.set_group(
                pk,
                current=start_index + 1,
                total=n,
                label=_step_display_label(steps[start_index], locale),
            )
        else:
            await svc.set_group(pk, current=n, total=n, label="")
        await checkpoint.save_task_group_state(
            telegram_id,
            pk,
            user_id=user_id,
            telegram_id=telegram_id,
            steps=steps,
            resume_from_index=start_index,
            results=restored_results,
        )

        results: list[dict] = list(restored_results)
        for i in range(start_index, n):
            st = steps[i]
            kind = st.get("kind")
            cid = st.get("company_id")
            await checkpoint.save_task_group_state(
                telegram_id,
                pk,
                user_id=user_id,
                telegram_id=telegram_id,
                steps=steps,
                resume_from_index=i,
                results=results,
            )
            if kind not in ("autoparse", "autorespond", "parsing") or not cid:
                results.append({"status": "skipped", "reason": "bad_step"})
                await checkpoint.save_task_group_state(
                    telegram_id,
                    pk,
                    user_id=user_id,
                    telegram_id=telegram_id,
                    steps=steps,
                    resume_from_index=i + 1,
                    results=results,
                )
                continue
            company_id = int(cid)
            await svc.set_group(
                pk,
                current=i + 1,
                total=n,
                label=_step_display_label(st, locale),
            )
            await svc.update_bar(pk, 0, i + 1, n)
            await svc.set_step_state(pk, f"tg{i}", "running")
            await svc.set_active_step_index(pk, i)

            if kind == "autoparse":
                await svc.set_bar_label(pk, 1, get_text("progress-step-autoparse-pipeline", locale))
                r = await _run_autoparse_company_async(
                    session_factory,
                    task,
                    company_id,
                    user_id,
                    suppress_progress=True,
                )
            elif kind == "autorespond":
                await svc.set_bar_label(pk, 1, get_text("progress-step-negotiations-sync", locale))
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
                await svc.set_bar_label(pk, 1, get_text("progress-step-parsing-pipeline", locale))
                r = await _run_parsing_company_async(
                    session_factory,
                    task,
                    company_id,
                    user_id,
                    include_blacklisted=False,
                    telegram_chat_id=telegram_id,
                    suppress_progress=True,
                )
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
                await checkpoint.save_task_group_state(
                    telegram_id,
                    pk,
                    user_id=user_id,
                    telegram_id=telegram_id,
                    steps=steps,
                    resume_from_index=i,
                    results=results,
                )
                with contextlib.suppress(Exception):
                    await svc.cancel_task(pk)
                return {"status": "step_failed", "step": i, "result": r, "results": results + [r]}
            results.append(r)
            if kind == "autorespond":
                with contextlib.suppress(Exception):
                    await svc.clear_nested_steps(pk)
            await svc.set_step_state(pk, f"tg{i}", "done")
            await checkpoint.save_task_group_state(
                telegram_id,
                pk,
                user_id=user_id,
                telegram_id=telegram_id,
                steps=steps,
                resume_from_index=i + 1,
                results=results,
            )

        await svc.update_bar(pk, 0, n, n)
        summary_lines = _build_completion_summary_lines(results, locale)
        if summary_lines:
            await svc.update_completion_summary(pk, summary_lines)
        await svc.finish_task(pk)
        await checkpoint.clear_task_group_state(telegram_id, pk)
        return {"status": "completed", "results": results}
    finally:
        with contextlib.suppress(Exception):
            await bot.session.close()
        with contextlib.suppress(Exception):
            await redis.aclose()
        with contextlib.suppress(Exception):
            await checkpoint_redis.aclose()


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
    task_key: str | None = None,
    resume_from_index: int = 0,
) -> dict:
    steps = json.loads(steps_json)
    if not isinstance(steps, list):
        return {"status": "error", "reason": "invalid_steps"}
    return run_async(
        lambda sf: _run_task_group_sequence_async(
            sf,
            self,
            user_id,
            telegram_id,
            steps,
            task_key=task_key,
            resume_from_index=resume_from_index,
        )
    )
