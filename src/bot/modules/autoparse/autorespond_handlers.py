"""Autorespond settings and manual run (company detail)."""

from __future__ import annotations

import asyncio
import contextlib

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.autoparse import services as ap_service
from src.bot.modules.autoparse.callbacks import AutoparseCallback
from src.bot.modules.autoparse.keyboards import autorespond_settings_keyboard, autoparse_detail_keyboard
from src.core.celery_async import run_celery_task
from src.core.i18n import I18nContext
from src.core.logging import get_logger
from src.models.user import User
from src.repositories.app_settings import AppSettingRepository
from src.repositories.autoparse import AutoparseCompanyRepository
from src.repositories.hh_linked_account import HhLinkedAccountRepository

router = Router(name="autoparse_autorespond")
logger = get_logger(__name__)


async def autorespond_globally_enabled(session: AsyncSession) -> bool:
    repo = AppSettingRepository(session)
    return await repo.get_value("task_autorespond_enabled", default=False)


@router.callback_query(AutoparseCallback.filter(F.action == "ar_menu"))
async def ar_menu(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id)
    if not company or company.user_id != user.id:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    count = await ap_service.get_vacancy_count(session, company.id)
    ar_task_on = await autorespond_globally_enabled(session)
    text = ap_service.format_company_detail(
        company,
        count,
        i18n,
        autorespond_global=True,
        autorespond_task_enabled=ar_task_on,
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=autorespond_settings_keyboard(company, i18n),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "ar_toggle"))
async def ar_toggle(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    repo = AutoparseCompanyRepository(session)
    company = await repo.get_by_id(callback_data.company_id)
    if not company or company.user_id != user.id:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    await repo.update(company, autorespond_enabled=not company.autorespond_enabled)
    await session.commit()
    company = await ap_service.get_autoparse_detail(session, company.id)
    assert company is not None
    count = await ap_service.get_vacancy_count(session, company.id)
    ar_task_on = await autorespond_globally_enabled(session)
    text = ap_service.format_company_detail(
        company,
        count,
        i18n,
        autorespond_global=True,
        autorespond_task_enabled=ar_task_on,
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=autorespond_settings_keyboard(company, i18n),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "ar_mode"))
async def ar_mode(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    repo = AutoparseCompanyRepository(session)
    company = await repo.get_by_id(callback_data.company_id)
    if not company or company.user_id != user.id:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    new_mode = (
        "title_and_keywords"
        if company.autorespond_keyword_mode == "title_only"
        else "title_only"
    )
    await repo.update(company, autorespond_keyword_mode=new_mode)
    await session.commit()
    company = await ap_service.get_autoparse_detail(session, company.id)
    assert company is not None
    count = await ap_service.get_vacancy_count(session, company.id)
    ar_task_on = await autorespond_globally_enabled(session)
    text = ap_service.format_company_detail(
        company,
        count,
        i18n,
        autorespond_global=True,
        autorespond_task_enabled=ar_task_on,
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=autorespond_settings_keyboard(company, i18n),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "ar_limit"))
async def ar_limit(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    repo = AutoparseCompanyRepository(session)
    company = await repo.get_by_id(callback_data.company_id)
    if not company or company.user_id != user.id:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    raw = callback_data.page
    lim = -1 if raw == 9999 else raw
    if lim not in {10, 20, 30, 50, -1}:
        await callback.answer()
        return
    await repo.update(company, autorespond_max_per_run=lim)
    await session.commit()
    company = await ap_service.get_autoparse_detail(session, company.id)
    assert company is not None
    count = await ap_service.get_vacancy_count(session, company.id)
    ar_task_on = await autorespond_globally_enabled(session)
    text = ap_service.format_company_detail(
        company,
        count,
        i18n,
        autorespond_global=True,
        autorespond_task_enabled=ar_task_on,
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=autorespond_settings_keyboard(company, i18n),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "ar_thr"))
async def ar_thr(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    thr = callback_data.page
    if thr not in {40, 50, 60, 70, 80}:
        await callback.answer()
        return
    repo = AutoparseCompanyRepository(session)
    company = await repo.get_by_id(callback_data.company_id)
    if not company or company.user_id != user.id:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    await repo.update(company, autorespond_min_compat=thr)
    await session.commit()
    company = await ap_service.get_autoparse_detail(session, company.id)
    assert company is not None
    count = await ap_service.get_vacancy_count(session, company.id)
    ar_task_on = await autorespond_globally_enabled(session)
    text = ap_service.format_company_detail(
        company,
        count,
        i18n,
        autorespond_global=True,
        autorespond_task_enabled=ar_task_on,
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=autorespond_settings_keyboard(company, i18n),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "ar_resume"))
async def ar_resume(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id)
    if not company or company.user_id != user.id:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    acc_repo = HhLinkedAccountRepository(session)
    accounts = await acc_repo.list_active_for_user(user.id)
    if not accounts:
        await callback.answer(i18n.get("autorespond-no-hh-account"), show_alert=True)
        return
    rows = []
    for acc in accounts[:6]:
        label = acc.label or acc.hh_user_id[:12]
        rows.append(
            [
                InlineKeyboardButton(
                    text=label[:40],
                    callback_data=AutoparseCallback(
                        action="ar_resume_acc",
                        company_id=company.id,
                        aux_id=acc.id,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=AutoparseCallback(action="ar_menu", company_id=company.id).pack(),
            )
        ]
    )
    await callback.message.edit_text(
        i18n.get("autorespond-pick-account"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "ar_resume_acc"))
async def ar_resume_acc(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id)
    if not company or company.user_id != user.id:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    acc_repo = HhLinkedAccountRepository(session)
    acc = await acc_repo.get_by_id(callback_data.aux_id)
    if not acc or acc.user_id != user.id:
        await callback.answer(i18n.get("autorespond-no-hh-account"), show_alert=True)
        return
    callback_answered = False
    cache = acc.resume_list_cache or []
    if not cache:
        from src.config import settings
        from src.bot.modules.autoparse.hh_resume_list_ui_async import (
            LIST_RESUMES_TIMEOUT_S,
            run_list_resumes_ui_async,
        )
        from src.services.hh.client import HhApiClient
        from src.services.hh.crypto import HhTokenCipher
        from src.services.hh.token_service import ensure_access_token
        from src.services.hh_ui.outcomes import ApplyOutcome
        from src.services.hh_ui.storage import decrypt_browser_storage

        if settings.hh_ui_apply_enabled:
            if not acc.browser_storage_enc:
                await callback.answer(
                    i18n.get("feed-respond-no-browser-session"), show_alert=True
                )
                return
            try:
                cipher = HhTokenCipher(settings.hh_token_encryption_key)
                storage = decrypt_browser_storage(acc.browser_storage_enc, cipher)
            except Exception:
                await callback.answer(i18n.get("hh-token-error"), show_alert=True)
                return
            if not storage:
                await callback.answer(
                    i18n.get("feed-respond-no-browser-session"), show_alert=True
                )
                return

            await callback.answer()
            callback_answered = True
            with contextlib.suppress(TelegramBadRequest):
                await callback.message.edit_text(
                    i18n.get("feed-respond-loading-resumes"),
                    parse_mode="HTML",
                )
            try:
                lr = await run_list_resumes_ui_async(storage, user.id)
            except asyncio.TimeoutError:
                logger.warning(
                    "autorespond_list_resumes_timeout",
                    user_id=user.id,
                    hh_linked_account_id=acc.id,
                    timeout_s=LIST_RESUMES_TIMEOUT_S,
                )
                with contextlib.suppress(TelegramBadRequest):
                    await callback.message.edit_text(
                        i18n.get("feed-respond-load-timeout"),
                        parse_mode="HTML",
                    )
                return
            except Exception as exc:
                logger.exception(
                    "autorespond_list_resumes_failed",
                    user_id=user.id,
                    hh_linked_account_id=acc.id,
                    error=str(exc),
                )
                with contextlib.suppress(TelegramBadRequest):
                    await callback.message.edit_text(
                        i18n.get("feed-respond-fetch-error"), parse_mode="HTML"
                    )
                return
            if lr.outcome == ApplyOutcome.CAPTCHA:
                with contextlib.suppress(TelegramBadRequest):
                    await callback.message.edit_text(
                        i18n.get("feed-respond-ui-captcha"), parse_mode="HTML"
                    )
                if lr.screenshot_bytes:
                    await callback.message.answer_photo(
                        BufferedInputFile(lr.screenshot_bytes, "hh_captcha.png"),
                    )
                return
            if lr.outcome == ApplyOutcome.SESSION_EXPIRED:
                with contextlib.suppress(TelegramBadRequest):
                    await callback.message.edit_text(
                        i18n.get("feed-respond-ui-session-expired"), parse_mode="HTML"
                    )
                return
            if lr.outcome != ApplyOutcome.SUCCESS or not lr.resumes:
                with contextlib.suppress(TelegramBadRequest):
                    await callback.message.edit_text(
                        i18n.get("feed-respond-fetch-error"), parse_mode="HTML"
                    )
                return
            logger.info(
                "autorespond_resume_cache_miss",
                user_id=user.id,
                hh_linked_account_id=acc.id,
                resume_count=len(lr.resumes),
            )
            await acc_repo.update_resume_list_cache(
                acc,
                [{"id": r.id, "title": r.title} for r in lr.resumes[:12]],
            )
            await session.commit()
            await session.refresh(acc)
        else:
            try:
                _, access = await ensure_access_token(session, acc.id)
            except Exception:
                await callback.answer(i18n.get("hh-token-error"), show_alert=True)
                return

            await callback.answer()
            callback_answered = True
            with contextlib.suppress(TelegramBadRequest):
                await callback.message.edit_text(
                    i18n.get("feed-respond-loading-resumes"),
                    parse_mode="HTML",
                )
            client = HhApiClient(access)
            try:
                data = await client.get_resumes_mine(per_page=20)
            except Exception:
                with contextlib.suppress(TelegramBadRequest):
                    await callback.message.edit_text(
                        i18n.get("feed-respond-fetch-error"), parse_mode="HTML"
                    )
                return

            items = data.get("items") or []
            cache_items: list[dict[str, str]] = []
            for it in items:
                rid = it.get("id")
                if not rid:
                    continue
                title = it.get("title") or rid
                cache_items.append(
                    {"id": str(rid).strip(), "title": str(title)[:60]}
                )
            if not cache_items:
                with contextlib.suppress(TelegramBadRequest):
                    await callback.message.edit_text(
                        i18n.get("feed-respond-no-resumes"), parse_mode="HTML"
                    )
                return
            await acc_repo.update_resume_list_cache(acc, cache_items[:12])
            await session.commit()
            await session.refresh(acc)

        cache = acc.resume_list_cache or []

    if not cache:
        with contextlib.suppress(TelegramBadRequest):
            await callback.message.edit_text(
                i18n.get("feed-respond-no-resumes"), parse_mode="HTML"
            )
        if not callback_answered:
            await callback.answer()
        return

    rows = []
    for idx, item in enumerate(cache[:12]):
        rid = str(item.get("id", ""))
        title = str(item.get("title", rid))[:40]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{idx + 1}. {title}",
                    callback_data=AutoparseCallback(
                        action="ar_resume_pick",
                        company_id=company.id,
                        aux_id=acc.id,
                        page=idx,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=AutoparseCallback(action="ar_resume", company_id=company.id).pack(),
            )
        ]
    )
    await callback.message.edit_text(
        i18n.get("autorespond-pick-default-resume"),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )
    if not callback_answered:
        await callback.answer()


@router.callback_query(AutoparseCallback.filter(F.action == "ar_resume_pick"))
async def ar_resume_pick(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    repo = AutoparseCompanyRepository(session)
    company = await repo.get_by_id(callback_data.company_id)
    if not company or company.user_id != user.id:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    acc_repo = HhLinkedAccountRepository(session)
    acc = await acc_repo.get_by_id(callback_data.aux_id)
    if not acc or acc.user_id != user.id:
        await callback.answer(i18n.get("autorespond-no-hh-account"), show_alert=True)
        return
    cache = acc.resume_list_cache or []
    idx = callback_data.page
    if idx < 0 or idx >= len(cache):
        await callback.answer()
        return
    rid = str(cache[idx].get("id", ""))
    if not rid:
        await callback.answer()
        return
    await repo.update(
        company,
        autorespond_hh_linked_account_id=acc.id,
        autorespond_resume_id=rid,
    )
    await session.commit()
    company = await ap_service.get_autoparse_detail(session, company.id)
    assert company is not None
    count = await ap_service.get_vacancy_count(session, company.id)
    ar_task_on = await autorespond_globally_enabled(session)
    text = ap_service.format_company_detail(
        company,
        count,
        i18n,
        autorespond_global=True,
        autorespond_task_enabled=ar_task_on,
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=autorespond_settings_keyboard(company, i18n),
            parse_mode="HTML",
        )
    await callback.answer(i18n.get("autorespond-saved"))


@router.callback_query(AutoparseCallback.filter(F.action == "ar_run"))
async def ar_run(
    callback: CallbackQuery,
    callback_data: AutoparseCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    if not await autorespond_globally_enabled(session):
        await callback.answer(i18n.get("autorespond-disabled-global"), show_alert=True)
        return
    company = await ap_service.get_autoparse_detail(session, callback_data.company_id)
    if not company or company.user_id != user.id:
        await callback.answer(i18n.get("autoparse-not-found"), show_alert=True)
        return
    if not company.autorespond_enabled:
        await callback.answer(i18n.get("autorespond-enable-first"), show_alert=True)
        return
    if not company.autorespond_hh_linked_account_id:
        await callback.answer(i18n.get("autorespond-configure-first"), show_alert=True)
        return
    from src.repositories.hh_linked_account import HhLinkedAccountRepository
    from src.services.ai.resume_selection import normalize_hh_resume_cache_items

    acc_repo = HhLinkedAccountRepository(session)
    acc = await acc_repo.get_by_id(company.autorespond_hh_linked_account_id)
    if not acc or not normalize_hh_resume_cache_items(acc.resume_list_cache):
        await callback.answer(i18n.get("autorespond-configure-first"), show_alert=True)
        return
    from src.core.celery_async import run_sync_in_thread
    from src.worker.tasks.autorespond import run_manual_autoparse_autorespond_pipeline

    await run_sync_in_thread(
        lambda: run_manual_autoparse_autorespond_pipeline.delay(company.id, user.id)
    )
    await callback.answer(i18n.get("autorespond-manual-pipeline-queued"), show_alert=True)
