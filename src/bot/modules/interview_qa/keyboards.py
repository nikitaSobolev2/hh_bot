"""Keyboard builders for the Interview Q&A module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.interview_qa.callbacks import InterviewQACallback
from src.models.interview_qa import WHY_NEW_JOB_REASONS

if TYPE_CHECKING:
    from src.core.i18n import I18nContext
    from src.models.interview_qa import StandardQuestion


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


def why_new_job_reasons_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=i18n.get(f"iqa-reason-{reason}"),
                callback_data=InterviewQACallback(action="why_reason", reason=reason).pack(),
            )
        ]
        for reason in WHY_NEW_JOB_REASONS
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=InterviewQACallback(action="list").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
                    text=i18n.get("btn-back"),
                    callback_data=InterviewQACallback(action="list").pack(),
                )
            ],
        ]
    )
