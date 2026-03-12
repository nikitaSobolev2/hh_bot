"""Keyboard builders for the Resume Generator module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.resume.callbacks import ResumeCallback
from src.services.ai.prompts import REC_LETTER_CHARACTERS

if TYPE_CHECKING:
    from src.core.i18n import I18nContext
    from src.models.parsing import ParsingCompany
    from src.models.recommendation_letter import RecommendationLetter
    from src.models.resume import Resume

_SKILL_LEVELS: list[str] = ["Junior", "Middle", "Senior", "Lead"]
_PAGE_SIZE = 5


def resume_list_keyboard(
    resumes: list[Resume],
    page: int,
    total: int,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """Paginated list of resumes with Create New and Back to Menu."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=i18n.get("res-btn-create-new"),
                callback_data=ResumeCallback(action="start").pack(),
            )
        ]
    ]

    for r in resumes:
        date_str = r.created_at.strftime("%m/%d %H:%M")
        label = f"📋 {r.job_title}"
        if r.skill_level:
            label += f" ({r.skill_level})"
        label += f" — {date_str}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data=ResumeCallback(
                        action="view",
                        work_exp_id=r.id,
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
                    callback_data=ResumeCallback(action="list", page=page - 1).pack(),
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=f"{page + 1}/{total_pages}",
                callback_data=ResumeCallback(action="list", page=page).pack(),
            )
        )
        if page < total_pages - 1:
            nav.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=ResumeCallback(action="list", page=page + 1).pack(),
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


def resume_start_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("res-btn-start"),
                    callback_data=ResumeCallback(action="start").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back-menu"),
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )


def resume_cancel_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=ResumeCallback(action="cancel").pack(),
                )
            ]
        ]
    )


def resume_skill_level_buttons(i18n: I18nContext) -> InlineKeyboardMarkup:
    """One button per skill level, packed with the level value as work_exp_id placeholder.

    Because callback_data fields are typed ints we encode the level index (1-4).
    """
    rows = []
    for idx, level in enumerate(_SKILL_LEVELS, start=1):
        rows.append(
            [
                InlineKeyboardButton(
                    text=level,
                    callback_data=ResumeCallback(
                        action="set_skill_level",
                        work_exp_id=idx,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-skip"),
                callback_data=ResumeCallback(action="skip_skill_level").pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-cancel"),
                callback_data=ResumeCallback(action="cancel").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def resume_keywords_source_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    """Ask the user where their extra keywords should come from."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("res-btn-keywords-manual"),
                    callback_data=ResumeCallback(action="keywords_manual").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("res-btn-keywords-from-parsing"),
                    callback_data=ResumeCallback(action="keywords_from_parsing").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip"),
                    callback_data=ResumeCallback(action="keywords_skip").pack(),
                )
            ],
        ]
    )


def resume_parsing_companies_keyboard(
    companies: list[ParsingCompany],
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """One button per parsing company that has aggregated keywords, plus a Skip."""
    rows = [
        [
            InlineKeyboardButton(
                text=company.vacancy_title,
                callback_data=ResumeCallback(
                    action="keywords_use_company",
                    company_id=company.id,
                ).pack(),
            )
        ]
        for company in companies
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-skip"),
                callback_data=ResumeCallback(action="keywords_skip").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def resume_rec_letter_ask_keyboard(
    work_exp_id: int,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """Yes / No keyboard for the recommendation-letter prompt per job."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-yes"),
                    callback_data=ResumeCallback(
                        action="rec_yes",
                        work_exp_id=work_exp_id,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=i18n.get("btn-no"),
                    callback_data=ResumeCallback(
                        action="rec_no",
                        work_exp_id=work_exp_id,
                    ).pack(),
                ),
            ]
        ]
    )


def resume_rec_character_keyboard(
    work_exp_id: int,
    locale: str,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """Predefined character-type buttons for the recommendation letter."""
    rows = []
    for key, labels in REC_LETTER_CHARACTERS.items():
        label = labels.get(locale, labels.get("ru", key))
        rows.append(
            [
                InlineKeyboardButton(
                    text=label.capitalize(),
                    callback_data=ResumeCallback(
                        action=f"rec_char_{key}",
                        work_exp_id=work_exp_id,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-cancel"),
                callback_data=ResumeCallback(action="cancel").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def resume_rec_focus_keyboard(
    work_exp_id: int,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """Skip + Cancel for the optional focus-text step."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip"),
                    callback_data=ResumeCallback(
                        action="rec_skip_focus",
                        work_exp_id=work_exp_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=ResumeCallback(action="cancel").pack(),
                )
            ],
        ]
    )


def resume_result_keyboard(
    resume: Resume,
    letters: list[RecommendationLetter],
    locale: str,
    i18n: I18nContext,
    *,
    from_list: bool = False,
) -> InlineKeyboardMarkup:
    """Final result view keyboard — keywords, per-job buttons, summary, autoparser."""
    rows: list[list[InlineKeyboardButton]] = []

    if resume.parsed_keywords:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("res-btn-show-parsed-keywords"),
                    callback_data=ResumeCallback(action="show_keywords").pack(),
                )
            ]
        )

    if resume.keyphrases_by_company:
        for company_index, company_name in enumerate(resume.keyphrases_by_company):
            rows.append(
                [
                    InlineKeyboardButton(
                        text=f"💼 {company_name}",
                        callback_data=ResumeCallback(
                            action="show_job_keyphrases",
                            company_id=resume.id,
                            # work_exp_id carries the 0-based company index so each
                            # button produces a unique callback_data string
                            work_exp_id=company_index,
                        ).pack(),
                    )
                ]
            )

        for letter in letters:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=i18n.get("res-btn-show-rec-letter"),
                        callback_data=ResumeCallback(
                            action="show_rec_letter",
                            work_exp_id=letter.id,
                        ).pack(),
                    )
                ]
            )

    if resume.summary_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("res-btn-show-summary"),
                    callback_data=ResumeCallback(
                        action="show_summary",
                        summary_id=resume.summary_id,
                    ).pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("res-btn-create-autoparser"),
                callback_data=ResumeCallback(action="create_autoparser").pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("res-btn-delete"),
                callback_data=ResumeCallback(action="delete", work_exp_id=resume.id).pack(),
            )
        ]
    )
    if from_list:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=ResumeCallback(action="list").pack(),
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


def resume_job_view_keyboard(
    resume_id: int,
    company_name: str,
    letter_id: int | None,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """Per-job detail view: keyphrases button + optional recommendation letter button."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=i18n.get("res-btn-show-job-keyphrases"),
                callback_data=ResumeCallback(
                    action="show_job_keyphrases",
                    company_id=resume_id,
                ).pack(),
            )
        ]
    ]
    if letter_id:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("res-btn-show-rec-letter"),
                    callback_data=ResumeCallback(
                        action="show_rec_letter",
                        work_exp_id=letter_id,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=ResumeCallback(action="show_result").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def resume_step3_continue_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    """Continue to step 3 (summary) or skip directly to rec letters."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("res-btn-continue-step3"),
                    callback_data=ResumeCallback(action="step3_summary").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip"),
                    callback_data=ResumeCallback(action="skip_to_rec_letters").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=ResumeCallback(action="cancel").pack(),
                )
            ],
        ]
    )
