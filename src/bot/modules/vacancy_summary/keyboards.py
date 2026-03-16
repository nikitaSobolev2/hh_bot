"""Keyboard builders for the Vacancy Summary module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.vacancy_summary.callbacks import VacancySummaryCallback

if TYPE_CHECKING:
    from src.core.i18n import I18nContext
    from src.models.vacancy_summary import VacancySummary

_PAGE_SIZE = 5


def vacancy_summary_list_keyboard(
    summaries: list[VacancySummary],
    page: int,
    total: int,
    i18n: I18nContext,
    *,
    in_resume_context: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=i18n.get("vs-btn-generate-new"),
                callback_data=VacancySummaryCallback(action="generate_new").pack(),
            )
        ]
    ]

    for s in summaries:
        date_str = s.created_at.strftime("%m/%d %H:%M")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📄 {date_str}",
                    callback_data=VacancySummaryCallback(action="detail", summary_id=s.id).pack(),
                )
            ]
        )

    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=VacancySummaryCallback(action="list", page=page - 1).pack(),
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data=VacancySummaryCallback(action="list", page=page).pack(),
            )
        )
        if page < total_pages - 1:
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=VacancySummaryCallback(action="list", page=page + 1).pack(),
                )
            )
        rows.append(nav)

    if in_resume_context:
        from src.bot.modules.resume.callbacks import ResumeCallback

        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("res-btn-continue-rec-letters"),
                    callback_data=ResumeCallback(action="rec_start").pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back-menu"),
                callback_data=MenuCallback(action="main").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def vacancy_summary_detail_keyboard(
    summary_id: int,
    i18n: I18nContext,
    *,
    in_resume_context: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=i18n.get("vs-btn-regenerate"),
                callback_data=VacancySummaryCallback(
                    action="regenerate", summary_id=summary_id
                ).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.get("vs-btn-delete"),
                callback_data=VacancySummaryCallback(action="delete", summary_id=summary_id).pack(),
            )
        ],
    ]

    if in_resume_context:
        from src.bot.modules.resume.callbacks import ResumeCallback

        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("vs-btn-use-for-resume"),
                    callback_data=ResumeCallback(
                        action="select_summary",
                        summary_id=summary_id,
                    ).pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=VacancySummaryCallback(action="list").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skip_keyboard(i18n: I18nContext, *, step: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip"),
                    callback_data=VacancySummaryCallback(action="skip_step").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=VacancySummaryCallback(
                        action="back_step", step=step
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=VacancySummaryCallback(action="cancel").pack(),
                )
            ],
        ]
    )
