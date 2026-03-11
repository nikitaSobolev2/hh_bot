"""Keyboard builders for the My Interviews module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.interviews.callbacks import InterviewCallback, InterviewFormCallback
from src.models.interview import ImprovementStatus, InterviewImprovement

if TYPE_CHECKING:
    from src.core.i18n import I18nContext
    from src.models.interview import Interview

_PAGE_SIZE = 5

_IMPROVEMENT_STATUS_ICONS = {
    ImprovementStatus.PENDING: "⏳",
    ImprovementStatus.SUCCESS: "✅",
    ImprovementStatus.ERROR: "❌",
}


def interview_list_keyboard(
    interviews: list[Interview],
    page: int,
    total: int,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-iv-add-new"),
                callback_data=InterviewCallback(action="new").pack(),
            )
        ]
    )

    for interview in interviews:
        date_str = interview.created_at.strftime("%m/%d")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📝 {interview.vacancy_title} ({date_str})",
                    callback_data=InterviewCallback(
                        action="detail", interview_id=interview.id
                    ).pack(),
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
                    callback_data=InterviewCallback(action="list", page=page - 1).pack(),
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data=InterviewCallback(action="list", page=page).pack(),
            )
        )
        if page < total_pages - 1:
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=InterviewCallback(action="list", page=page + 1).pack(),
                )
            )
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back-menu"),
                callback_data=MenuCallback(action="main").pack(),
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def source_choice_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-iv-source-hh"),
                    callback_data=InterviewFormCallback(action="source", value="hh").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-iv-source-manual"),
                    callback_data=InterviewFormCallback(action="source", value="manual").pack(),
                )
            ],
            [_cancel_button(i18n)],
        ]
    )


def experience_level_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    levels = [
        ("no_experience", i18n.get("btn-iv-exp-none")),
        ("1-3", i18n.get("btn-iv-exp-junior")),
        ("3-6", i18n.get("btn-iv-exp-middle")),
        ("6+", i18n.get("btn-iv-exp-senior")),
        ("other", i18n.get("btn-iv-exp-other")),
    ]
    rows = [
        [
            InlineKeyboardButton(
                text=label,
                callback_data=InterviewFormCallback(action="exp", value=value).pack(),
            )
        ]
        for value, label in levels
    ]
    rows.append([_cancel_button(i18n)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def questions_keyboard(question_count: int, i18n: I18nContext) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if question_count > 0:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-iv-questions-done"),
                    callback_data=InterviewFormCallback(action="questions_done").pack(),
                )
            ]
        )
    rows.append([_cancel_button(i18n)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skip_notes_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-iv-skip"),
                    callback_data=InterviewFormCallback(action="skip_notes").pack(),
                )
            ],
            [_cancel_button(i18n)],
        ]
    )


def confirm_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-iv-proceed"),
                    callback_data=InterviewFormCallback(action="proceed").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=InterviewFormCallback(action="cancel").pack(),
                )
            ],
        ]
    )


def cancel_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_cancel_button(i18n)]])


def interview_detail_keyboard(
    interview_id: int,
    improvements: list[InterviewImprovement],
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for imp in improvements:
        icon = _IMPROVEMENT_STATUS_ICONS.get(imp.status, "⏳")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{icon} {imp.technology_title}",
                    callback_data=InterviewCallback(
                        action="improvement",
                        interview_id=interview_id,
                        improvement_id=imp.id,
                    ).pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-iv-delete"),
                callback_data=InterviewCallback(action="delete", interview_id=interview_id).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=InterviewCallback(action="list").pack(),
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def improvement_detail_keyboard(
    interview_id: int,
    improvement_id: int,
    has_flow: bool,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    if not has_flow:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-iv-generate-flow"),
                    callback_data=InterviewCallback(
                        action="gen_flow",
                        interview_id=interview_id,
                        improvement_id=improvement_id,
                    ).pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-iv-set-improved"),
                callback_data=InterviewCallback(
                    action="set_success",
                    interview_id=interview_id,
                    improvement_id=improvement_id,
                ).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-iv-set-incorrect"),
                callback_data=InterviewCallback(
                    action="set_error",
                    interview_id=interview_id,
                    improvement_id=improvement_id,
                ).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-iv-back-improvements"),
                callback_data=InterviewCallback(action="detail", interview_id=interview_id).pack(),
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def delete_confirm_keyboard(interview_id: int, i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-iv-delete-confirm"),
                    callback_data=InterviewCallback(
                        action="delete_confirm", interview_id=interview_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=InterviewCallback(
                        action="detail", interview_id=interview_id
                    ).pack(),
                )
            ],
        ]
    )


def _cancel_button(i18n: I18nContext) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=i18n.get("btn-cancel"),
        callback_data=InterviewCallback(action="cancel").pack(),
    )
