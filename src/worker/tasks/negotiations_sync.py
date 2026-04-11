"""Celery task: sync HH applicant negotiations (responded vacancies) into hh_application_attempts."""

from __future__ import annotations

import asyncio
import contextlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import settings
from src.core.i18n import get_text
from src.core.logging import get_logger
from src.models.autoparse import NEGOTIATIONS_SYNC_PLACEHOLDER_COMPAT, AutoparsedVacancy
from src.repositories.autoparse import AutoparseCompanyRepository, AutoparsedVacancyRepository
from src.repositories.hh import HHAreaRepository, HHEmployerRepository
from src.repositories.hh_application_attempt import HhApplicationAttemptRepository
from src.repositories.hh_linked_account import HhLinkedAccountRepository
from src.repositories.vacancy_feed import VacancyFeedSessionRepository
from src.services.autoparse.negotiations_liked_merge import merge_liked_from_negotiations_sync
from src.services.hh.crypto import HhTokenCipher
from src.services.hh_ui.applicant_negotiations_http import fetch_all_negotiation_vacancy_ids
from src.services.hh_ui.config import HhUiApplyConfig
from src.services.hh_ui.storage import decrypt_browser_storage
from src.services.parser.scraper import HHCaptchaRequiredError
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)

_SYNC_RESUME_PLACEHOLDER = "sync"


async def _sync_negotiations_async(
    session_factory: async_sessionmaker[AsyncSession],
    task: HHBotTask | None,
    user_id: int,
    hh_linked_account_id: int,
    autoparse_company_id: int,
    chat_id: int,
    locale: str,
    *,
    notify_user: bool = True,
    prefetched_vacancy_ids: set[str] | None = None,
) -> dict:
    vacancy_ids = prefetched_vacancy_ids
    if vacancy_ids is None:
        async with session_factory() as session:
            acc_repo = HhLinkedAccountRepository(session)
            acc = await acc_repo.get_by_id(hh_linked_account_id)
            if not acc or acc.user_id != user_id:
                return {"status": "error", "reason": "account_not_found"}
            if not acc.browser_storage_enc:
                return {"status": "error", "reason": "no_browser_session"}
            try:
                cipher = HhTokenCipher(settings.hh_token_encryption_key)
                storage = decrypt_browser_storage(acc.browser_storage_enc, cipher)
            except Exception as exc:
                logger.warning("negotiations_sync_decrypt_failed", error=str(exc)[:200])
                return {"status": "error", "reason": "decrypt_failed"}
        if not storage:
            return {"status": "error", "reason": "no_browser_session"}

        config = HhUiApplyConfig.from_settings()
        vacancy_ids, fetch_err = await asyncio.to_thread(
            fetch_all_negotiation_vacancy_ids,
            storage,
            config,
        )
        if fetch_err:
            logger.info(
                "negotiations_sync_fetch_issue",
                user_id=user_id,
                hh_linked_account_id=hh_linked_account_id,
                reason=fetch_err,
                parsed_count=len(vacancy_ids),
            )
            if fetch_err == "login_redirect" and not vacancy_ids:
                return {"status": "error", "reason": "login_redirect"}
            if not vacancy_ids:
                return {"status": "error", "reason": fetch_err}

    vacancy_ids = set(vacancy_ids)

    if not vacancy_ids:
        if notify_user and task is not None:
            bot = task.create_bot()
            try:
                body = get_text("autoparse-sync-empty", locale)
                await bot.send_message(chat_id, body, parse_mode="HTML")
            finally:
                await bot.session.close()
        return {
            "status": "ok",
            "inserted": 0,
            "skipped_existing": 0,
            "total_parsed": 0,
            "liked_in_feed": 0,
            "vacancies_imported": 0,
        }

    inserted = 0
    skipped_existing = 0
    liked_in_feed = 0
    vacancies_imported = 0

    async with session_factory() as session:
        company_repo = AutoparseCompanyRepository(session)
        company = await company_repo.get_by_id(autoparse_company_id)
        if not company or company.user_id != user_id:
            return {"status": "error", "reason": "company_not_found"}
        vac_repo = AutoparsedVacancyRepository(session)
        already = await vac_repo.hh_vacancy_ids_already_in_company(autoparse_company_id, vacancy_ids)

    missing = sorted(vacancy_ids - already)
    fetched: dict[str, dict] = {}
    if missing:
        from src.services.autoparse.negotiations_vacancy_import import fetch_merged_vac_dicts_for_hh_ids

        try:
            fetched = await fetch_merged_vac_dicts_for_hh_ids(missing)
        except HHCaptchaRequiredError as exc:
            logger.warning(
                "negotiations_sync_fetch_aborted_captcha",
                user_id=user_id,
                hh_linked_account_id=hh_linked_account_id,
                autoparse_company_id=autoparse_company_id,
                missing=len(missing),
                total_parsed=len(vacancy_ids),
                error=str(exc)[:200],
            )
            return {
                "status": "error",
                "reason": "captcha_required",
                "vacancy_ids": sorted(vacancy_ids),
            }

    async with session_factory() as session:
        company_repo = AutoparseCompanyRepository(session)
        company = await company_repo.get_by_id(autoparse_company_id)
        if not company or company.user_id != user_id:
            return {"status": "error", "reason": "company_not_found"}

        vac_repo = AutoparsedVacancyRepository(session)
        employer_repo = HHEmployerRepository(session)
        area_repo = HHAreaRepository(session)
        from src.worker.tasks.autoparse import _build_autoparsed_vacancy

        for hid, vac_dict in fetched.items():
            dup = await session.execute(
                select(AutoparsedVacancy.id).where(
                    AutoparsedVacancy.autoparse_company_id == autoparse_company_id,
                    AutoparsedVacancy.hh_vacancy_id == hid,
                )
            )
            if dup.scalar_one_or_none() is not None:
                continue
            is_placeholder = bool(vac_dict.pop("_negotiations_placeholder", False))
            employer_id = vac_dict.get("_employer_id")
            area_id = vac_dict.get("_area_id")
            if employer_id is None or area_id is None:
                employer_data = vac_dict.get("employer_data") or {}
                area_data = vac_dict.get("area_data") or {}
                if employer_id is None and employer_data.get("id"):
                    employer = await employer_repo.get_or_create_by_hh_id(employer_data)
                    employer_id = employer.id
                if area_id is None and area_data.get("id"):
                    area = await area_repo.get_or_create_by_hh_id(area_data)
                    area_id = area.id
            compat_score = (
                NEGOTIATIONS_SYNC_PLACEHOLDER_COMPAT if is_placeholder else None
            )
            row = _build_autoparsed_vacancy(
                vac_dict,
                autoparse_company_id,
                compat_score=compat_score,
                ai_summary=None,
                ai_stack=None,
                employer_id=employer_id,
                area_id=area_id,
            )
            session.add(row)
            vacancies_imported += 1

        await session.flush()

        stmt_hh_ap = select(AutoparsedVacancy.hh_vacancy_id, AutoparsedVacancy.id).where(
            AutoparsedVacancy.autoparse_company_id == autoparse_company_id,
            AutoparsedVacancy.hh_vacancy_id.in_(list(vacancy_ids)),
        )
        hh_to_ap = {
            str(h): int(ap_id) for h, ap_id in (await session.execute(stmt_hh_ap)).all()
        }

        attempt_repo = HhApplicationAttemptRepository(session)
        for vid in sorted(vacancy_ids):
            if await attempt_repo.user_has_any_attempt_for_hh_vacancy(user_id, vid):
                skipped_existing += 1
                continue
            await attempt_repo.create(
                user_id=user_id,
                hh_linked_account_id=hh_linked_account_id,
                autoparsed_vacancy_id=hh_to_ap.get(vid),
                hh_vacancy_id=vid,
                resume_id=_SYNC_RESUME_PLACEHOLDER,
                status="success",
                api_negotiation_id=None,
                error_code="sync:negotiations",
                response_excerpt=None,
            )
            inserted += 1

        feed_repo = VacancyFeedSessionRepository(session)
        to_like = set(
            await vac_repo.list_ids_by_company_and_hh_vacancy_ids(autoparse_company_id, vacancy_ids)
        )
        if to_like:
            sessions = await feed_repo.list_sessions_for_user_company(user_id, autoparse_company_id)
            if sessions:
                for fs in sessions:
                    new_liked, new_disliked = merge_liked_from_negotiations_sync(
                        list(fs.liked_ids or []),
                        list(fs.disliked_ids or []),
                        to_like,
                    )
                    if new_liked != list(fs.liked_ids or []) or new_disliked != list(
                        fs.disliked_ids or []
                    ):
                        await feed_repo.update(fs, liked_ids=new_liked, disliked_ids=new_disliked)
                liked_in_feed = len(to_like)
            else:
                logger.info(
                    "negotiations_sync_no_feed_sessions_for_liked_merge",
                    user_id=user_id,
                    autoparse_company_id=autoparse_company_id,
                    matching_autoparsed=len(to_like),
                )

        await session.commit()

    if notify_user and task is not None:
        bot = task.create_bot()
        try:
            body = get_text(
                "autoparse-sync-done",
                locale,
                inserted=inserted,
                skipped=skipped_existing,
                total=len(vacancy_ids),
                liked_in_feed=liked_in_feed,
                vacancies_imported=vacancies_imported,
            )
            await bot.send_message(chat_id, body, parse_mode="HTML")
        finally:
            await bot.session.close()

    logger.info(
        "negotiations_sync_completed",
        user_id=user_id,
        hh_linked_account_id=hh_linked_account_id,
        autoparse_company_id=autoparse_company_id,
        inserted=inserted,
        skipped_existing=skipped_existing,
        total_parsed=len(vacancy_ids),
        liked_in_feed=liked_in_feed,
        vacancies_imported=vacancies_imported,
    )
    return {
        "status": "ok",
        "inserted": inserted,
        "skipped_existing": skipped_existing,
        "total_parsed": len(vacancy_ids),
        "liked_in_feed": liked_in_feed,
        "vacancies_imported": vacancies_imported,
    }


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="negotiations.sync_from_hh",
    soft_time_limit=300,
    time_limit=360,
)
def sync_negotiations_from_hh_task(
    self,
    user_id: int,
    hh_linked_account_id: int,
    autoparse_company_id: int,
    chat_id: int,
    locale: str,
) -> dict:
    async def _with_progress(session_factory):
        from src.core.i18n import get_text
        from src.services.progress_service import ProgressService, create_progress_redis

        if chat_id and chat_id > 0:
            bot = self.create_bot()
            redis = create_progress_redis()
            tid = str(self.request.id or "local")
            tk = f"sync_negotiations:{autoparse_company_id}:{tid}"
            svc = ProgressService(bot, chat_id, redis, locale)
            title = get_text("negotiations-progress-title", locale)
            used_progress = False
            try:
                await svc.start_task(
                    tk,
                    title,
                    [get_text("progress-generic-working", locale)],
                    celery_task_id=tid,
                    initial_totals=[1],
                )
                used_progress = True
            except Exception as exc:
                # Telegram may reject send_message (blocked bot, invalid chat, etc.)
                logger.warning(
                    "negotiations_progress_unavailable",
                    chat_id=chat_id,
                    error=str(exc)[:400],
                )
            try:
                try:
                    res = await _sync_negotiations_async(
                        session_factory,
                        self,
                        user_id,
                        hh_linked_account_id,
                        autoparse_company_id,
                        chat_id,
                        locale,
                    )
                except Exception:
                    if used_progress:
                        with contextlib.suppress(Exception):
                            await svc.cancel_task(tk)
                    raise
                if used_progress:
                    if res.get("status") == "ok":
                        await svc.update_bar(tk, 0, 1, 1)
                        await svc.finish_task(tk)
                    else:
                        with contextlib.suppress(Exception):
                            await svc.cancel_task(tk)
                return res
            finally:
                with contextlib.suppress(Exception):
                    await bot.session.close()
        return await _sync_negotiations_async(
            session_factory,
            self,
            user_id,
            hh_linked_account_id,
            autoparse_company_id,
            chat_id,
            locale,
        )

    return run_async(_with_progress)
