"""Autorespond settings and manual run (company detail)."""

from __future__ import annotations

import contextlib

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.modules.autoparse import services as ap_service
from src.bot.modules.autoparse.callbacks import AutoparseCallback
from src.bot.modules.autoparse.keyboards import autorespond_settings_keyboard, autoparse_detail_keyboard
from src.core.celery_async import run_celery_task
from src.core.i18n import I18nContext
from src.models.user import User
from src.repositories.app_settings import AppSettingRepository
from src.repositories.autoparse import AutoparseCompanyRepository
from src.repositories.hh_linked_account import HhLinkedAccountRepository

router = Router(name="autoparse_autorespond")


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
    cache = acc.resume_list_cache or []
    if not cache:
        await callback.answer(i18n.get("autorespond-resume-cache-empty"), show_alert=True)
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
    from celery import chain

    from src.core.celery_async import run_sync_in_thread
    from src.worker.tasks.autoparse import run_autoparse_company
    from src.worker.tasks.autorespond import run_autorespond_after_manual_parse

    await run_sync_in_thread(
        lambda: chain(
            run_autoparse_company.s(company.id, user.id),
            run_autorespond_after_manual_parse.s(company.id, user.id),
        ).delay()
    )
    await callback.answer(i18n.get("autorespond-manual-pipeline-queued"), show_alert=True)
