"""Keyboard builders for the Interview Q&A module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.interview_qa.callbacks import InterviewQACallback
from src.models.interview_qa import BASE_QUESTION_KEYS, WHY_NEW_JOB_REASONS

if TYPE_CHECKING:
    from src.core.i18n import I18nContext
    from src.models.interview import Interview
    from src.models.interview_qa import StandardQuestion

_PAGE_SIZE = 5


def interview_qa_list_keyboard(
    questions: list[StandardQuestion],
    i18n: I18nContext,
    has_ai_questions: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("iqa-btn-why-new-job"),
                callback_data=InterviewQACallback(
                    action="base_question", question_key="why_new_job"
                ).pack(),
            )
        ]
    )

    for q in questions:
        status = "✅" if q.answer_text else "⏳"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {q.question_text[:50]}",
                    callback_data=InterviewQACallback(
                        action="view_question", question_key=q.question_key
                    ).pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("iqa-btn-custom-question"),
                callback_data=InterviewQACallback(action="custom_question").pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("iqa-btn-generate-all"),
                callback_data=InterviewQACallback(action="generate_all").pack(),
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


def why_new_job_reasons_keyboard(i18n: I18nContext, is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=i18n.get(f"iqa-reason-{reason}"),
                callback_data=InterviewQACallback(action="why_reason", reason=reason).pack(),
            )
        ]
        for reason in WHY_NEW_JOB_REASONS
    ]
    if is_admin:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-type-manually"),
                    callback_data=InterviewQACallback(action="why_reason_manual").pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=InterviewQACallback(action="list").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def generate_select_keyboard(
    generated_keys: set[str],
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    ai_keys = [k for k in BASE_QUESTION_KEYS if k != "why_new_job"]
    rows: list[list[InlineKeyboardButton]] = []

    for key in ai_keys:
        status = "✅" if key in generated_keys else "❌"
        question_text = i18n.get(f"iqa-question-{key}")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {question_text[:45]}",
                    callback_data=InterviewQACallback(
                        action="generate_one", question_key=key
                    ).pack(),
                )
            ]
        )

    pending_count = sum(1 for k in ai_keys if k not in generated_keys)
    if pending_count > 0:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("iqa-btn-generate-pending", count=pending_count),
                    callback_data=InterviewQACallback(action="generate_pending").pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=InterviewQACallback(action="list").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def answer_back_keyboard(
    question_key: str,
    reason: str,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """Keyboard for why_reason / why_reason_manual answer views: Add to interview + Back."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("iqa-btn-add-to-interview"),
                    callback_data=InterviewQACallback(
                        action="add_to_interview",
                        question_key=question_key,
                        reason=reason,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=InterviewQACallback(action="list").pack(),
                )
            ],
        ]
    )


def question_detail_keyboard(
    question_key: str,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("iqa-btn-regenerate"),
                    callback_data=InterviewQACallback(
                        action="regenerate", question_key=question_key
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("iqa-btn-add-to-interview"),
                    callback_data=InterviewQACallback(
                        action="add_to_interview", question_key=question_key
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=InterviewQACallback(action="list").pack(),
                )
            ],
        ]
    )


def interview_add_select_keyboard(
    interviews: list[Interview],
    page: int,
    total: int,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """Paginated interview list for add-to-interview flow."""
    rows: list[list[InlineKeyboardButton]] = []

    for interview in interviews:
        date_str = interview.created_at.strftime("%m/%d")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📝 {interview.vacancy_title} ({date_str})",
                    callback_data=InterviewQACallback(
                        action="add_to_interview_select",
                        interview_id=interview.id,
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
                    callback_data=InterviewQACallback(
                        action="add_to_interview_list", page=page - 1
                    ).pack(),
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data=InterviewQACallback(
                    action="add_to_interview_list", page=page
                ).pack(),
            )
        )
        if page < total_pages - 1:
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=InterviewQACallback(
                        action="add_to_interview_list", page=page + 1
                    ).pack(),
                )
            )
        rows.append(nav)

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=InterviewQACallback(action="add_to_interview_back").pack(),
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)
