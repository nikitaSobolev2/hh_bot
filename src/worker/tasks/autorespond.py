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
from src.repositories.autoparse import AutoparseCompanyRepository, AutoparsedVacancyRepository
from src.repositories.vacancy_feed import VacancyFeedSessionRepository
from src.repositories.hh_application_attempt import HhApplicationAttemptRepository
from src.services.hh.client import HhApiClient, HhApiError, apply_to_vacancy_with_resume
from src.services.hh.token_service import ensure_access_token
from src.services.hh_ui.rate_limit import (
    current_ui_apply_count_sync,
    get_hh_ui_apply_max_per_day_effective,
    try_acquire_ui_apply_slot_sync,
)
from src.services.hh_ui.runner import normalize_hh_vacancy_url
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)


def _autorespond_filter_rejection_counts(
    raw: list[AutoparsedVacancy],
    *,
    min_compat: int,
    company_keyword_filter: str,
    keyword_mode: str,
    allow_missing_compatibility_score: bool,
) -> tuple[int, int]:
    """How many rows fail compatibility vs keyword (among those that passed compat)."""
    compat_rejected = 0
    keyword_rejected = 0
    for v in raw:
        if not autorespond_logic.vacancy_passes_compatibility(
            v,
            min_compat,
            allow_missing_score=allow_missing_compatibility_score,
        ):
            compat_rejected += 1
            continue
        if not autorespond_logic.vacancy_passes_keyword_mode(
            v, company_keyword_filter, keyword_mode
        ):
            keyword_rejected += 1
    return compat_rejected, keyword_rejected


async def _load_candidates(
    session: AsyncSession,
    company_id: int,
    vacancy_ids: list[int] | None,
    task_started_at: datetime | None,
) -> list[AutoparsedVacancy]:
    repo = AutoparsedVacancyRepository(session)
    if vacancy_ids:
        return await repo.get_by_ids_for_company(company_id, vacancy_ids)
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


async def _unreacted_autoparsed_vacancy_ids(
    session_factory: async_sessionmaker[AsyncSession],
    company_id: int,
    user_id: int,
) -> list[int]:
    """Autoparsed vacancy PKs for this company that the user has not liked/disliked in any feed."""
    async with session_factory() as session:
        feed_repo = VacancyFeedSessionRepository(session)
        reacted = await feed_repo.get_all_reacted_vacancy_ids(user_id, company_id)
        stmt = select(AutoparsedVacancy.id).where(
            AutoparsedVacancy.autoparse_company_id == company_id,
        )
        if reacted:
            stmt = stmt.where(AutoparsedVacancy.id.notin_(list(reacted)))
        stmt = stmt.order_by(AutoparsedVacancy.id.desc())
        result = await session.execute(stmt)
        return [int(row[0]) for row in result.all()]


async def _run_autorespond_after_manual_parse_async(
    session_factory: async_sessionmaker[AsyncSession],
    company_id: int,
    user_id: int,
) -> dict:
    """After manual autoparse completes: enqueue autorespond for all unreacted vacancies."""
    async with session_factory() as session:
        settings_repo = AppSettingRepository(session)
        if not await settings_repo.get_value("task_autorespond_enabled", default=False):
            return {"status": "skipped", "reason": "autorespond_disabled_global"}
        company_repo = AutoparseCompanyRepository(session)
        company = await company_repo.get_by_id(company_id)
        if not company or company.is_deleted or company.user_id != user_id:
            return {"status": "skipped", "reason": "company_invalid"}
        if not company.autorespond_enabled:
            return {"status": "skipped", "reason": "autorespond_disabled_company"}
        if not company.autorespond_hh_linked_account_id:
            return {"status": "skipped", "reason": "autorespond_not_configured"}
        from src.repositories.hh_linked_account import HhLinkedAccountRepository
        from src.services.ai.resume_selection import normalize_hh_resume_cache_items

        hh_acc_repo = HhLinkedAccountRepository(session)
        hh_acc = await hh_acc_repo.get_by_id(company.autorespond_hh_linked_account_id)
        if not hh_acc or not normalize_hh_resume_cache_items(hh_acc.resume_list_cache):
            return {"status": "skipped", "reason": "autorespond_not_configured"}

    ids = await _unreacted_autoparsed_vacancy_ids(session_factory, company_id, user_id)
    if not ids:
        logger.info(
            "manual_chain_no_unreacted",
            company_id=company_id,
            user_id=user_id,
        )
        return {"status": "no_unreacted", "vacancy_ids": []}

    run_autorespond_company.delay(
        company_id,
        vacancy_ids=ids,
        trigger="manual_unreacted",
    )
    logger.info(
        "manual_chain_autorespond_enqueued",
        company_id=company_id,
        user_id=user_id,
        count=len(ids),
    )
    return {"status": "enqueued", "vacancy_count": len(ids), "vacancy_ids": ids}


async def _run_autorespond_async(
    session_factory: async_sessionmaker[AsyncSession],
    celery_task: object | None,
    company_id: int,
    vacancy_ids: list[int] | None,
    trigger: str,
    task_started_at: datetime | None,
) -> dict:
    from src.bot.modules.autoparse import services as ap_service
    from src.core.constants import AppSettingKey
    from src.core.i18n import get_text
    from src.repositories.autoparse import AutoparseCompanyRepository
    from src.repositories.user import UserRepository
    from src.services.autorespond_progress import (
        clear_autorespond_done_counter,
        clear_autorespond_failed_counter,
        clear_autorespond_parent_loop_active_sync,
        clear_autorespond_ui_tail_sync,
        clear_hh_ui_batch_checkpoint_sync,
        is_autorespond_cancelled_sync,
        save_autorespond_ui_tail_sync,
        set_autorespond_parent_loop_active_sync,
        tick_autorespond_bar,
    )
    from src.services.progress_service import ProgressService, create_progress_redis
    from src.worker.tasks.cover_letter import generate_cover_letter_plaintext_for_autoparsed_vacancy
    from src.worker.tasks.hh_ui_apply import apply_to_vacancies_batch_ui_task
    from src.repositories.hh_linked_account import HhLinkedAccountRepository
    from src.services.ai.client import AIClient
    from src.services.ai.resume_selection import (
        normalize_hh_resume_cache_items,
        resolve_resume_id_for_autorespond_vacancy,
    )
    from src.bot.modules.autoparse import feed_services as feed_services_autorespond
    from src.services.hh.vacancy_public import hh_vacancy_public_is_unavailable

    async with session_factory() as session:
        settings_repo = AppSettingRepository(session)
        global_on = await settings_repo.get_value("task_autorespond_enabled", default=False)
        if not global_on:
            logger.info(
                "autorespond_exit",
                company_id=company_id,
                trigger=trigger,
                reason="disabled_global",
            )
            return {"status": "disabled_global"}

        company_repo = AutoparseCompanyRepository(session)
        company = await company_repo.get_by_id(company_id)
        if not company or company.is_deleted:
            logger.info(
                "autorespond_exit",
                company_id=company_id,
                trigger=trigger,
                reason="company_not_found",
            )
            return {"status": "company_not_found"}
        if not company.autorespond_enabled:
            logger.info(
                "autorespond_exit",
                company_id=company_id,
                trigger=trigger,
                reason="disabled_company",
            )
            return {"status": "disabled_company"}
        if not company.autorespond_hh_linked_account_id:
            logger.info(
                "autorespond_exit",
                company_id=company_id,
                trigger=trigger,
                reason="not_configured",
            )
            return {"status": "not_configured"}

        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(company.user_id)
        if not user:
            logger.info(
                "autorespond_exit",
                company_id=company_id,
                trigger=trigger,
                reason="user_not_found",
            )
            return {"status": "user_not_found"}

        hh_acc_id = company.autorespond_hh_linked_account_id
        hh_acc_repo = HhLinkedAccountRepository(session)
        hh_linked = await hh_acc_repo.get_by_id(hh_acc_id)
        if not hh_linked:
            logger.info(
                "autorespond_exit",
                company_id=company_id,
                trigger=trigger,
                reason="hh_account_not_found",
            )
            return {"status": "not_configured"}
        resume_items = normalize_hh_resume_cache_items(hh_linked.resume_list_cache)
        if not resume_items:
            logger.info(
                "autorespond_exit",
                company_id=company_id,
                trigger=trigger,
                reason="resume_cache_empty",
            )
            return {"status": "not_configured"}

        ap_settings = await ap_service.get_user_autoparse_settings(session, user.id)
        cover_letter_style = ap_settings.get("cover_letter_style", "professional")
        cover_task_enabled = bool(
            await settings_repo.get_value(AppSettingKey.TASK_COVER_LETTER_ENABLED, default=True)
        )

        raw = await _load_candidates(session, company_id, vacancy_ids, task_started_at)
        # Manual chain passes concrete unreacted feed IDs; do not re-apply company
        # keyword_filter here (it targets search/query matching and can drop every row).
        kw_filter = (company.keyword_filter or "") if trigger != "manual_unreacted" else ""
        allow_missing_compat = vacancy_ids is not None
        compat_rejected, keyword_rejected = _autorespond_filter_rejection_counts(
            raw,
            min_compat=company.autorespond_min_compat,
            company_keyword_filter=kw_filter,
            keyword_mode=company.autorespond_keyword_mode,
            allow_missing_compatibility_score=allow_missing_compat,
        )
        filtered = autorespond_logic.filter_vacancies_for_autorespond(
            raw,
            min_compat=company.autorespond_min_compat,
            company_keyword_filter=kw_filter,
            keyword_mode=company.autorespond_keyword_mode,
            allow_missing_compatibility_score=allow_missing_compat,
        )
        filtered.sort(key=lambda v: -v.id)
        capped = autorespond_logic.apply_max_cap(filtered, company.autorespond_max_per_run)

        logger.info(
            "autorespond_selection_breakdown",
            company_id=company_id,
            trigger=trigger,
            user_id=user.id,
            vacancy_ids_requested=len(vacancy_ids) if vacancy_ids else None,
            raw_loaded=len(raw),
            min_compat=company.autorespond_min_compat,
            keyword_mode=company.autorespond_keyword_mode,
            keyword_filter_chars=len(kw_filter.strip()),
            keyword_filter_skipped_for_trigger=trigger == "manual_unreacted",
            allow_missing_compatibility_score=allow_missing_compat,
            compat_rejected=compat_rejected,
            keyword_rejected=keyword_rejected,
            after_filter=len(filtered),
            max_per_run=company.autorespond_max_per_run,
            after_cap=len(capped),
            hh_ui_apply_enabled=settings.hh_ui_apply_enabled,
            cover_task_enabled=cover_task_enabled,
        )

        attempt_repo = HhApplicationAttemptRepository(session)
        already_handled: set[str] = set()
        if capped:
            already_handled = await attempt_repo.hh_vacancy_ids_with_success_or_employer_questions(
                user.id,
                [v.hh_vacancy_id for v in capped],
            )

        work_units, pre_skipped_autorespond = autorespond_logic.work_units_for_autorespond_progress(
            capped, already_handled
        )
        logger.info(
            "autorespond_progress_totals",
            company_id=company_id,
            trigger=trigger,
            user_id=user.id,
            after_cap=len(capped),
            work_units=work_units,
            pre_skipped_autorespond=pre_skipped_autorespond,
        )

        cover_ai_client: AIClient | None = None

        queued = 0
        skipped = 0
        failed = 0
        locale = user.language_code or "ru"
        ui_batch_buffer: list[tuple[AutoparsedVacancy, str]] = []
        queue_ui_items: list[dict] = []

        progress: object | None = None
        task_key: str | None = None
        progress_bot = None
        cid = getattr(celery_task, "request", None)
        celery_id = str(getattr(cid, "id", None) or "local") if celery_task else "local"
        show_progress = bool(
            celery_task
            and user.telegram_id
            and capped
            and work_units > 0
            and user.telegram_id > 0
        )
        if show_progress:
            task_key = f"autorespond:{company_id}:{celery_id}"
            progress_bot = celery_task.create_bot()  # type: ignore[union-attr]
            progress = ProgressService(progress_bot, user.telegram_id, create_progress_redis(), locale)
            await progress.start_task(
                task_key=task_key,
                title=company.vacancy_title,
                bar_labels=[get_text("progress-bar-autorespond", locale)],
                celery_task_id=celery_id,
                initial_totals=[work_units],
            )
            await progress.update_footer(
                task_key,
                [get_text("autorespond-progress-failed", locale, count=failed)],
            )
            await clear_autorespond_failed_counter(user.telegram_id, task_key)

        ar_prog = (
            {
                "task_key": task_key,
                "total": work_units,
                "locale": locale,
                "title": company.vacancy_title,
                "celery_task_id": celery_id,
            }
            if (task_key and progress and progress_bot)
            else None
        )

        # cancelled / rate_limited returns skip the safety flush below
        _autorespond_exit = "ok"

        try:
            async def flush_ui_batch() -> None:
                nonlocal queued
                if not ui_batch_buffer:
                    return
                n = len(ui_batch_buffer)
                batch_payload = [
                    {
                        "autoparsed_vacancy_id": vac.id,
                        "hh_vacancy_id": vac.hh_vacancy_id,
                        "resume_id": rid,
                        "vacancy_url": normalize_hh_vacancy_url(vac.url, vac.hh_vacancy_id),
                    }
                    for vac, rid in ui_batch_buffer
                ]
                apply_to_vacancies_batch_ui_task.delay(
                    user.id,
                    user.telegram_id,
                    0,
                    locale,
                    hh_acc_id,
                    0,
                    batch_payload,
                    cover_letter_style,
                    cover_task_enabled,
                    silent_feed=True,
                    autorespond_progress=ar_prog,
                )
                queued += n
                ui_batch_buffer.clear()
                for _ in range(n):
                    if queue_ui_items:
                        queue_ui_items.pop(0)
                if task_key and user.telegram_id:
                    save_autorespond_ui_tail_sync(user.telegram_id, task_key, list(queue_ui_items))

            if settings.hh_ui_apply_enabled and task_key and user.telegram_id:
                set_autorespond_parent_loop_active_sync(user.telegram_id, task_key)

            for idx, vac in enumerate(capped, start=1):
                if task_key and user.telegram_id and is_autorespond_cancelled_sync(
                    user.telegram_id, task_key
                ):
                    logger.info(
                        "autorespond_loop_cancelled",
                        company_id=company_id,
                        user_id=user.id,
                        task_key=task_key,
                        trigger=trigger,
                        queued=queued,
                    )
                    if task_key and user.telegram_id:
                        clear_autorespond_ui_tail_sync(user.telegram_id, task_key)
                        clear_hh_ui_batch_checkpoint_sync(user.telegram_id, task_key)
                    _autorespond_exit = "cancelled"
                    return {
                        "status": "cancelled",
                        "queued": queued,
                        "skipped": skipped,
                        "failed": failed,
                        "trigger": trigger,
                    }

                if vac.hh_vacancy_id in already_handled or vac.needs_employer_questions:
                    skipped += 1
                    continue

                if await hh_vacancy_public_is_unavailable(vac.hh_vacancy_id):
                    skipped += 1
                    async with session_factory() as s_merge:
                        await feed_services_autorespond.merge_dislike_vacancy_into_feed_sessions(
                            s_merge,
                            user.id,
                            company_id,
                            vac.id,
                        )
                    if ar_prog and progress_bot:
                        await tick_autorespond_bar(
                            bot=progress_bot,
                            chat_id=user.telegram_id,
                            task_key=ar_prog["task_key"],
                            total=ar_prog["total"],
                            locale=ar_prog["locale"],
                            footer_failed_line=get_text(
                                "autorespond-progress-failed", locale, count=failed
                            ),
                            title=ar_prog.get("title"),
                            celery_task_id=ar_prog.get("celery_task_id"),
                        )
                    continue

                if settings.hh_ui_apply_enabled:
                    if not try_acquire_ui_apply_slot_sync(user.id):
                        await flush_ui_batch()
                        logger.info(
                            "autorespond_rate_limited",
                            company_id=company_id,
                            user_id=user.id,
                            queued=queued,
                            partial_batch=queued > 0,
                            hh_ui_apply_count_today=current_ui_apply_count_sync(user.id),
                            hh_ui_apply_max_per_day=get_hh_ui_apply_max_per_day_effective(),
                        )
                        if task_key and user.telegram_id:
                            await clear_autorespond_done_counter(user.telegram_id, task_key)
                            await clear_autorespond_failed_counter(user.telegram_id, task_key)
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
                        if task_key and user.telegram_id:
                            clear_autorespond_ui_tail_sync(user.telegram_id, task_key)
                            clear_hh_ui_batch_checkpoint_sync(user.telegram_id, task_key)
                        _autorespond_exit = "rate_limited"
                        return {
                            "status": "rate_limited",
                            "queued": queued,
                            "skipped": skipped,
                            "failed": failed,
                            "trigger": trigger,
                        }
                    if len(resume_items) > 1 and cover_ai_client is None:
                        cover_ai_client = AIClient()
                    resume_id = await resolve_resume_id_for_autorespond_vacancy(
                        cover_ai_client,
                        vac,
                        resume_items,
                        stored_autorespond_resume_id=company.autorespond_resume_id,
                    )
                    if not resume_id:
                        skipped += 1
                        if ar_prog and progress_bot:
                            await tick_autorespond_bar(
                                bot=progress_bot,
                                chat_id=user.telegram_id,
                                task_key=ar_prog["task_key"],
                                total=ar_prog["total"],
                                locale=ar_prog["locale"],
                                footer_failed_line=get_text(
                                    "autorespond-progress-failed", locale, count=failed
                                ),
                                title=ar_prog.get("title"),
                                celery_task_id=ar_prog.get("celery_task_id"),
                            )
                        continue
                    item_d = {
                        "autoparsed_vacancy_id": vac.id,
                        "hh_vacancy_id": vac.hh_vacancy_id,
                        "resume_id": str(resume_id),
                        "vacancy_url": normalize_hh_vacancy_url(vac.url, vac.hh_vacancy_id),
                    }
                    queue_ui_items.append(item_d)
                    ui_batch_buffer.append((vac, resume_id))
                    if task_key and user.telegram_id:
                        save_autorespond_ui_tail_sync(user.telegram_id, task_key, list(queue_ui_items))
                    if len(ui_batch_buffer) >= settings.hh_ui_apply_batch_size:
                        await flush_ui_batch()
                else:
                    if len(resume_items) > 1 and cover_ai_client is None:
                        cover_ai_client = AIClient()
                    resume_id = await resolve_resume_id_for_autorespond_vacancy(
                        cover_ai_client,
                        vac,
                        resume_items,
                        stored_autorespond_resume_id=company.autorespond_resume_id,
                    )
                    if not resume_id:
                        skipped += 1
                        if ar_prog and progress_bot:
                            await tick_autorespond_bar(
                                bot=progress_bot,
                                chat_id=user.telegram_id,
                                task_key=ar_prog["task_key"],
                                total=ar_prog["total"],
                                locale=ar_prog["locale"],
                                footer_failed_line=get_text(
                                    "autorespond-progress-failed", locale, count=failed
                                ),
                                title=ar_prog.get("title"),
                                celery_task_id=ar_prog.get("celery_task_id"),
                            )
                        continue
                    letter_for_api: str | None = None
                    if cover_task_enabled:
                        try:
                            if cover_ai_client is None:
                                cover_ai_client = AIClient()
                            letter_for_api = await generate_cover_letter_plaintext_for_autoparsed_vacancy(
                                session_factory,
                                user.id,
                                vac.id,
                                cover_letter_style,
                                ai_client=cover_ai_client,
                            )
                        except Exception as gen_exc:
                            logger.warning(
                                "autorespond_cover_letter_failed",
                                company_id=company_id,
                                vacancy_id=vac.id,
                                error=str(gen_exc)[:300],
                            )
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
                                letter=letter_for_api,
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

                    if ar_prog and progress_bot:
                        await tick_autorespond_bar(
                            bot=progress_bot,
                            chat_id=user.telegram_id,
                            task_key=ar_prog["task_key"],
                            total=ar_prog["total"],
                            locale=ar_prog["locale"],
                            footer_failed_line=get_text(
                                "autorespond-progress-failed", locale, count=failed
                            ),
                            title=ar_prog.get("title"),
                            celery_task_id=ar_prog.get("celery_task_id"),
                        )

            await flush_ui_batch()

            # Do not clear hh_ui checkpoint / parent UI tail here: children may still be
            # applying in Playwright. Cleanup runs when ``tick_autorespond_bar`` reaches
            # done >= total (all units accounted for).

        except Exception:
            if progress and task_key and user.telegram_id:
                with contextlib.suppress(Exception):
                    await clear_autorespond_done_counter(user.telegram_id, task_key)
                with contextlib.suppress(Exception):
                    await clear_autorespond_failed_counter(user.telegram_id, task_key)
                with contextlib.suppress(Exception):
                    await progress.finish_task(task_key, complete_bars=False)
            raise
        finally:
            # If Celery soft-timeout or another error stops the loop mid-way, the last
            # partial UI batch may never reach the normal ``await flush_ui_batch()`` — then
            # no hh_ui tasks run for those rows and the progress bar never reaches ``total``.
            if _autorespond_exit not in ("cancelled", "rate_limited"):
                try:
                    if ui_batch_buffer:
                        logger.warning(
                            "autorespond_flush_ui_batch_finally",
                            company_id=company_id,
                            user_id=user.id,
                            trigger=trigger,
                            pending=len(ui_batch_buffer),
                        )
                    await flush_ui_batch()
                except Exception as exc:
                    logger.warning(
                        "autorespond_flush_ui_batch_finally_failed",
                        company_id=company_id,
                        error=str(exc)[:400],
                    )
            if task_key and user.telegram_id:
                clear_autorespond_parent_loop_active_sync(user.telegram_id, task_key)
            if cover_ai_client is not None:
                with contextlib.suppress(Exception):
                    await cover_ai_client.aclose()
            if progress_bot:
                with contextlib.suppress(Exception):
                    await progress_bot.session.close()

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
    # Parent task only enqueues hh_ui batches (Playwright runs elsewhere). The loop still
    # does DB + HH API + optional cover/AI per vacancy — 10m was too short and left a
    # partial ``ui_batch_buffer`` unflushed, stalling the progress bar short of ``total``.
    soft_time_limit=settings.autoparse_run_company_soft_time_limit_seconds,
    time_limit=settings.autoparse_run_company_time_limit_seconds,
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


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="autoparse.chain_autorespond_after_manual_parse",
    soft_time_limit=120,
    time_limit=150,
)
def run_autorespond_after_manual_parse(
    self,
    prev_result: dict | None,
    company_id: int,
    user_id: int,
) -> dict:
    """Chain step after `run_autoparse_company`: autorespond for all unreacted vacancies."""
    if not isinstance(prev_result, dict):
        logger.info(
            "chain_autorespond_skipped",
            company_id=company_id,
            user_id=user_id,
            reason="bad_prev",
        )
        return {"status": "skipped", "reason": "bad_prev"}
    if prev_result.get("status") != "completed":
        logger.info(
            "chain_autorespond_skipped",
            company_id=company_id,
            user_id=user_id,
            autoparse_status=prev_result.get("status"),
        )
        return {
            "status": "skipped",
            "reason": "autoparse_not_completed",
            "autoparse": prev_result,
        }

    return run_async(
        lambda sf: _run_autorespond_after_manual_parse_async(sf, company_id, user_id)
    )
