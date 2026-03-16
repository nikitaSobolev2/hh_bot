from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.autoparse.callbacks import (
    AutoparseCallback,
    AutoparseDownloadCallback,
    AutoparseSettingsCallback,
    AutoparseWorkExpCallback,
)
from src.models.autoparse import AutoparseCompany
from src.models.parsing import ParsingCompany
from src.models.work_experience import UserWorkExperience

if TYPE_CHECKING:
    from src.core.i18n import I18nContext

_PER_PAGE = 5
MAX_WORK_EXPERIENCES = 6


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
                text=i18n.get("autoparse-btn-show-liked"),
                callback_data=AutoparseCallback(action="show_liked").pack(),
            ),
            InlineKeyboardButton(
                text=i18n.get("autoparse-btn-show-disliked"),
                callback_data=AutoparseCallback(action="show_disliked").pack(),
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


def liked_disliked_list_keyboard(
    action: str,
    page: int,
    has_more: bool,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """Keyboard for paginated liked or disliked vacancies list."""
    rows: list[list[InlineKeyboardButton]] = []
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(
                text="<",
                callback_data=AutoparseCallback(action=action, page=page - 1).pack(),
            )
        )
    if has_more:
        nav_row.append(
            InlineKeyboardButton(
                text=">",
                callback_data=AutoparseCallback(action=action, page=page + 1).pack(),
            )
        )
    if nav_row:
        rows.append(nav_row)
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=AutoparseCallback(action="list").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def include_reacted_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    """Keyboard for include reacted vacancies step in create flow."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-include-reacted-yes"),
                    callback_data=AutoparseCallback(action="include_reacted_yes").pack(),
                ),
                InlineKeyboardButton(
                    text=i18n.get("autoparse-include-reacted-no"),
                    callback_data=AutoparseCallback(action="include_reacted_no").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=AutoparseCallback(action="hub").pack(),
                )
            ],
        ]
    )


def autoparse_detail_keyboard(
    company: AutoparseCompany,
    i18n: I18nContext,
    show_run_now: bool = False,
    show_show_now: bool = False,
) -> InlineKeyboardMarkup:
    toggle_text = (
        i18n.get("autoparse-toggle-disabled")
        if company.is_enabled
        else i18n.get("autoparse-toggle-enabled")
    )
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=toggle_text,
                callback_data=AutoparseCallback(action="toggle", company_id=company.id).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.get("autoparse-download-title"),
                callback_data=AutoparseCallback(action="download", company_id=company.id).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.get("autoparse-confirm-delete"),
                callback_data=AutoparseCallback(action="delete", company_id=company.id).pack(),
            )
        ],
    ]
    if show_run_now:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-run-now"),
                    callback_data=AutoparseCallback(action="run_now", company_id=company.id).pack(),
                )
            ]
        )
    if show_show_now:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-show-now"),
                    callback_data=AutoparseCallback(
                        action="show_now", company_id=company.id
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=AutoparseCallback(action="list").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
                    text=i18n.get("autoparse-settings-min-compat"),
                    callback_data=AutoparseSettingsCallback(action="min_compat").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-settings-user-name"),
                    callback_data=AutoparseSettingsCallback(action="user_name").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-settings-about-me"),
                    callback_data=AutoparseSettingsCallback(action="about_me").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("autoparse-settings-cover-letter-style"),
                    callback_data=AutoparseSettingsCallback(action="cover_letter_style").pack(),
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


def cover_letter_style_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    """Keyboard for cover letter style selection: predefined choices + custom + back."""
    rows: list[list[InlineKeyboardButton]] = []
    style_keys = [
        ("professional", "autoparse-cover-letter-style-professional"),
        ("friendly", "autoparse-cover-letter-style-friendly"),
        ("concise", "autoparse-cover-letter-style-concise"),
        ("detailed", "autoparse-cover-letter-style-detailed"),
    ]
    for style_id, i18n_key in style_keys:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get(i18n_key),
                    callback_data=AutoparseSettingsCallback(
                        action=f"cover_letter_style_{style_id}"
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("autoparse-cover-letter-style-custom"),
                callback_data=AutoparseSettingsCallback(
                    action="cover_letter_style_custom"
                ).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=AutoparseCallback(action="settings").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


def autoparse_work_exp_keyboard(
    experiences: list[UserWorkExperience],
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for exp in experiences:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"\u274c {i18n.get('btn-remove')} {exp.company_name}",
                    callback_data=AutoparseWorkExpCallback(
                        action="remove",
                        work_exp_id=exp.id,
                    ).pack(),
                )
            ]
        )

    if len(experiences) < MAX_WORK_EXPERIENCES:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-add-company"),
                    callback_data=AutoparseWorkExpCallback(action="add").pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=AutoparseCallback(action="settings").pack(),
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_add_work_exp_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=AutoparseWorkExpCallback(action="cancel_add").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=AutoparseWorkExpCallback(action="cancel_add").pack(),
                )
            ],
        ]
    )
