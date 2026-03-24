"""Celery task: autorespond to autoparsed vacancies (scheduled after parse or manual)."""

from __future__ import annotations

import contextlib
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.bot.modules.autoparse import autorespond_logic
from src.config import settings
from src.core.logging import get_logger
from src.models.autoparse import AutoparsedVacancy
from src.repositories.app_settings import AppSettingRepository
from src.repositories.autoparse import AutoparsedVacancyRepository
from src.repositories.hh_application_attempt import HhApplicationAttemptRepository
from src.services.hh.client import HhApiClient, HhApiError, apply_to_vacancy_with_resume
from src.services.hh.token_service import ensure_access_token
from src.services.hh_ui.rate_limit import try_acquire_ui_apply_slot_sync
from src.services.hh_ui.runner import normalize_hh_vacancy_url
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)


async def _load_candidates(
    session: AsyncSession,
    company_id: int,
    vacancy_ids: list[int] | None,
    task_started_at: datetime | None,
) -> list[AutoparsedVacancy]:
    repo = AutoparsedVacancyRepository(session)
    if vacancy_ids:
        out: list[AutoparsedVacancy] = []
        for vid in vacancy_ids:
            v = await repo.get_by_id(vid)
            if v and v.autoparse_company_id == company_id:
                out.append(v)
        return out
    stmt = (
        select(AutoparsedVacancy)
        .where(AutoparsedVacancy.autoparse_company_id == company_id)
        .order_by(AutoparsedVacancy.id.desc())
        .limit(500)
    )
    result = await session.execute(stmt)
    rows = list(result.scalars().all())
    if task_started_at is None:
        return rows
    return [v for v in rows if v.created_at and v.created_at >= task_started_at]


async def _run_autorespond_async(
    session_factory: async_sessionmaker[AsyncSession],
    celery_task: object | None,
    company_id: int,
    vacancy_ids: list[int] | None,
    trigger: str,
    task_started_at: datetime | None,
) -> dict:
    from src.core.i18n import get_text
    from src.repositories.autoparse import AutoparseCompanyRepository
    from src.repositories.user import UserRepository
    from src.services.progress_service import ProgressService, create_progress_redis
    from src.worker.tasks.hh_ui_apply import apply_to_vacancy_ui_task

    async with session_factory() as session:
        settings_repo = AppSettingRepository(session)
        global_on = await settings_repo.get_value("task_autorespond_enabled", default=False)
        if not global_on:
            return {"status": "disabled_global"}

        company_repo = AutoparseCompanyRepository(session)
        company = await company_repo.get_by_id(company_id)
        if not company or company.is_deleted:
            return {"status": "company_not_found"}
        if not company.autorespond_enabled:
            return {"status": "disabled_company"}
        if not company.autorespond_resume_id or not company.autorespond_hh_linked_account_id:
            return {"status": "not_configured"}

        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(company.user_id)
        if not user:
            return {"status": "user_not_found"}

        hh_acc_id = company.autorespond_hh_linked_account_id
        resume_id = company.autorespond_resume_id

        raw = await _load_candidates(session, company_id, vacancy_ids, task_started_at)
        filtered = autorespond_logic.filter_vacancies_for_autorespond(
            raw,
            min_compat=company.autorespond_min_compat,
            company_keyword_filter=company.keyword_filter or "",
            keyword_mode=company.autorespond_keyword_mode,
        )
        filtered.sort(key=lambda v: -v.id)
        capped = autorespond_logic.apply_max_cap(filtered, company.autorespond_max_per_run)

        queued = 0
        skipped = 0
        failed = 0
        locale = user.language_code or "ru"

        progress: object | None = None
        task_key: str | None = None
        cid = getattr(celery_task, "request", None)
        celery_id = str(getattr(cid, "id", None) or "local") if celery_task else "local"
        show_progress = bool(
            celery_task
            and user.telegram_id
            and capped
            and user.telegram_id > 0
        )
        if show_progress:
            task_key = f"autorespond:{company_id}:{celery_id}"
            bot = celery_task.create_bot()  # type: ignore[union-attr]
            progress = ProgressService(bot, user.telegram_id, create_progress_redis(), locale)
            await progress.start_task(
                task_key=task_key,
                title=company.vacancy_title,
                bar_labels=[get_text("progress-bar-autorespond", locale)],
                celery_task_id=celery_id,
                initial_totals=[len(capped)],
            )
            await progress.update_footer(
                task_key,
                [get_text("autorespond-progress-failed", locale, count=failed)],
            )

        try:
            for idx, vac in enumerate(capped, start=1):
                async with session_factory() as check_session:
                    ar = HhApplicationAttemptRepository(check_session)
                    if await ar.has_successful_apply(user.id, vac.hh_vacancy_id, resume_id):
                        skipped += 1
                        if progress and task_key:
                            await progress.update_bar(task_key, 0, idx, len(capped))
                            await progress.update_footer(
                                task_key,
                                [get_text("autorespond-progress-failed", locale, count=failed)],
                            )
                        continue

                if settings.hh_ui_apply_enabled:
                    if not try_acquire_ui_apply_slot_sync(user.id):
                        logger.info(
                            "autorespond_rate_limited",
                            company_id=company_id,
                            user_id=user.id,
                            queued=queued,
                        )
                        if progress and task_key:
                            await progress.finish_task(
                                task_key,
                                shortage_note=get_text(
                                    "autorespond-progress-rate-limited",
                                    locale,
                                ),
                                complete_bars=False,
                            )
                            progress = None
                        return {
                            "status": "rate_limited",
                            "queued": queued,
                            "skipped": skipped,
                            "failed": failed,
                            "trigger": trigger,
                        }
                    vacancy_url = normalize_hh_vacancy_url(vac.url, vac.hh_vacancy_id)
                    apply_to_vacancy_ui_task.delay(
                        user.id,
                        user.telegram_id,
                        0,
                        locale,
                        hh_acc_id,
                        vac.id,
                        vac.hh_vacancy_id,
                        resume_id,
                        vacancy_url,
                        0,
                        "",
                        silent_feed=True,
                    )
                    queued += 1
                else:
                    try:
                        async with session_factory() as token_session:
                            _, access = await ensure_access_token(token_session, hh_acc_id)
                            await token_session.commit()
                        client = HhApiClient(access)
                        status = "error"
                        err_code = None
                        neg_id = None
                        excerpt = None
                        try:
                            _st, body = await apply_to_vacancy_with_resume(
                                client,
                                vacancy_id=vac.hh_vacancy_id,
                                resume_id=resume_id,
                            )
                            status = "success"
                            if isinstance(body, dict):
                                neg_id = str(body.get("id", "") or "") or None
                                excerpt = str(body)[:2000]
                        except HhApiError as exc:
                            err_code = str(exc)
                            if isinstance(exc.body, dict):
                                errs = exc.body.get("errors") or []
                                if errs and isinstance(errs[0], dict):
                                    err_code = str(errs[0].get("value", exc))
                            excerpt = str(exc.body)[:2000] if exc.body else str(exc)

                        async with session_factory() as session2:
                            attempt_repo = HhApplicationAttemptRepository(session2)
                            await attempt_repo.create(
                                user_id=user.id,
                                hh_linked_account_id=hh_acc_id,
                                autoparsed_vacancy_id=vac.id,
                                hh_vacancy_id=vac.hh_vacancy_id,
                                resume_id=resume_id,
                                status=status,
                                api_negotiation_id=neg_id,
                                error_code=err_code,
                                response_excerpt=excerpt,
                            )
                            await session2.commit()
                        queued += 1
                        if status != "success":
                            failed += 1
                    except Exception as exc:
                        logger.warning(
                            "autorespond_api_apply_failed",
                            company_id=company_id,
                            vacancy_id=vac.id,
                            error=str(exc)[:200],
                        )
                        failed += 1
                        skipped += 1

                if progress and task_key:
                    await progress.update_bar(task_key, 0, idx, len(capped))
                    await progress.update_footer(
                        task_key,
                        [get_text("autorespond-progress-failed", locale, count=failed)],
                    )

            if progress and task_key:
                await progress.finish_task(task_key)
        except Exception:
            if progress and task_key:
                with contextlib.suppress(Exception):
                    await progress.finish_task(task_key, complete_bars=False)
            raise

        logger.info(
            "autorespond_completed",
            company_id=company_id,
            trigger=trigger,
            queued=queued,
            skipped=skipped,
            failed=failed,
        )
        return {
            "status": "ok",
            "queued": queued,
            "skipped": skipped,
            "failed": failed,
            "trigger": trigger,
        }


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="autoparse.run_autorespond",
    soft_time_limit=600,
    time_limit=660,
)
def run_autorespond_company(
    self,
    company_id: int,
    vacancy_ids: list[int] | None = None,
    trigger: str = "manual",
    task_started_at_iso: str | None = None,
) -> dict:
    ts = None
    if task_started_at_iso:
        try:
            ts = datetime.fromisoformat(task_started_at_iso)
        except ValueError:
            ts = None

    return run_async(
        lambda sf: _run_autorespond_async(sf, self, company_id, vacancy_ids, trigger, ts)
    )
