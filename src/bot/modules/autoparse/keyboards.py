from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.autoparse.callbacks import (
    AutoparseCallback,
    AutoparseDownloadCallback,
    AutoparseSettingsCallback,
)
from src.models.autoparse import AutoparseCompany
from src.models.parsing import ParsingCompany

if TYPE_CHECKING:
    from src.core.i18n import I18nContext

_PER_PAGE = 5


def autoparse_hub_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-create-new"),
                    callback_data=AutoparseCallback(action="create").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-list-title"),
                    callback_data=AutoparseCallback(action="list").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-settings-title"),
                    callback_data=AutoparseCallback(action="settings").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )


def template_list_keyboard(
    companies: list[ParsingCompany],
    page: int,
    has_more: bool,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for c in companies:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{c.vacancy_title} ({c.created_at.strftime('%m/%d')})",
                    callback_data=AutoparseCallback(
                        action="template_select", company_id=c.id
                    ).pack(),
                )
            ]
        )
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="<",
                callback_data=AutoparseCallback(action="create", page=page - 1).pack(),
            )
        )
    if has_more:
        nav_row.append(
            InlineKeyboardButton(
                text=">",
                callback_data=AutoparseCallback(action="create", page=page + 1).pack(),
            )
        )
    if nav_row:
        rows.append(nav_row)
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("autoparse-skip-template"),
                callback_data=AutoparseCallback(action="skip_template").pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=AutoparseCallback(action="hub").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def autoparse_list_keyboard(
    companies: list[AutoparseCompany],
    page: int,
    has_more: bool,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for c in companies:
        icon = "\u2705" if c.is_enabled else "\u23f8\ufe0f"
        status = (
            i18n.get("autoparse-status-enabled")
            if c.is_enabled
            else i18n.get("autoparse-status-disabled")
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{icon} {c.vacancy_title} [{status}]",
                    callback_data=AutoparseCallback(action="detail", company_id=c.id).pack(),
                )
            ]
        )
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="<",
                callback_data=AutoparseCallback(action="list", page=page - 1).pack(),
            )
        )
    if has_more:
        nav_row.append(
            InlineKeyboardButton(
                text=">",
                callback_data=AutoparseCallback(action="list", page=page + 1).pack(),
            )
        )
    if nav_row:
        rows.append(nav_row)
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=AutoparseCallback(action="hub").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def autoparse_detail_keyboard(company: AutoparseCompany, i18n: I18nContext) -> InlineKeyboardMarkup:
    toggle_text = (
        i18n.get("autoparse-toggle-disabled")
        if company.is_enabled
        else i18n.get("autoparse-toggle-enabled")
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=toggle_text,
                    callback_data=AutoparseCallback(action="toggle", company_id=company.id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-download-title"),
                    callback_data=AutoparseCallback(
                        action="download", company_id=company.id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-confirm-delete"),
                    callback_data=AutoparseCallback(action="delete", company_id=company.id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=AutoparseCallback(action="list").pack(),
                )
            ],
        ]
    )


def download_format_keyboard(company_id: int, i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-download-links"),
                    callback_data=AutoparseDownloadCallback(
                        company_id=company_id, format="links_txt"
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-download-summary"),
                    callback_data=AutoparseDownloadCallback(
                        company_id=company_id, format="summary_txt"
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-download-full"),
                    callback_data=AutoparseDownloadCallback(
                        company_id=company_id, format="full_md"
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=AutoparseCallback(action="detail", company_id=company_id).pack(),
                )
            ],
        ]
    )


def confirm_delete_keyboard(company_id: int, i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-confirm"),
                    callback_data=AutoparseCallback(
                        action="confirm_delete", company_id=company_id
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=AutoparseCallback(action="detail", company_id=company_id).pack(),
                ),
            ]
        ]
    )


def autoparse_settings_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-settings-work-exp"),
                    callback_data=AutoparseSettingsCallback(action="work_exp").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-settings-send-time"),
                    callback_data=AutoparseSettingsCallback(action="send_time").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-settings-tech-stack"),
                    callback_data=AutoparseSettingsCallback(action="tech_stack").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=AutoparseCallback(action="hub").pack(),
                )
            ],
        ]
    )


def cancel_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=AutoparseCallback(action="hub").pack(),
                )
            ]
        ]
    )
