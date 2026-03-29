"""Keyboard builders for the My Interviews module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.interviews.callbacks import InterviewCallback, InterviewFormCallback
from src.core.constants import IMPROVEMENT_STATUS_ICONS as _IMPROVEMENT_STATUS_ICONS_RAW
from src.models.interview import ImprovementStatus, InterviewImprovement

if TYPE_CHECKING:
    from src.core.i18n import I18nContext
    from src.models.interview import Interview


def _t(key: str, i18n: I18nContext | None = None, locale: str = "ru") -> str:
    """Resolve a translation key using i18n context or standalone get_text."""
    if i18n is not None:
        return i18n.get(key)
    from src.core.i18n import get_text

    return get_text(key, locale)


_PAGE_SIZE = 5

_IMPROVEMENT_STATUS_ICONS = {
    ImprovementStatus.PENDING: _IMPROVEMENT_STATUS_ICONS_RAW.get("pending", "⏳"),
    ImprovementStatus.SUCCESS: _IMPROVEMENT_STATUS_ICONS_RAW.get("success", "✅"),
    ImprovementStatus.ERROR: _IMPROVEMENT_STATUS_ICONS_RAW.get("error", "❌"),
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
    i18n: I18nContext | None = None,
    locale: str = "ru",
    has_questions: bool = True,
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
                text=_t("btn-iv-prepare-me", i18n, locale),
                callback_data=InterviewCallback(
                    action="prepare_me", interview_id=interview_id
                ).pack(),
            )
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text=_t("btn-iv-company-review", i18n, locale),
                callback_data=InterviewCallback(
                    action="company_review", interview_id=interview_id
                ).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=_t("btn-iv-questions-to-ask", i18n, locale),
                callback_data=InterviewCallback(
                    action="questions_to_ask", interview_id=interview_id
                ).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=_t("btn-iv-notes", i18n, locale),
                callback_data=InterviewCallback(
                    action="notes", interview_id=interview_id
                ).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=_t("btn-iv-employer-questions", i18n, locale),
                callback_data=InterviewCallback(
                    action="employer_qa", interview_id=interview_id
                ).pack(),
            )
        ]
    )

    if not has_questions:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t("btn-iv-add-results", i18n, locale),
                    callback_data=InterviewCallback(
                        action="add_results", interview_id=interview_id
                    ).pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=_t("btn-iv-delete", i18n, locale),
                callback_data=InterviewCallback(action="delete", interview_id=interview_id).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=_t("btn-back", i18n, locale),
                callback_data=InterviewCallback(action="list").pack(),
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def employer_qa_list_keyboard(
    interview_id: int,
    i18n: I18nContext | None = None,
    locale: str = "ru",
    *,
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text=_t("btn-notes-prev", i18n, locale),
                    callback_data=InterviewCallback(
                        action="employer_qa",
                        interview_id=interview_id,
                        page=page - 1,
                    ).pack(),
                )
            )
        from src.core.i18n import get_text

        page_label = (
            i18n.get("iv-notes-page", current=page + 1, total=total_pages)
            if i18n is not None
            else get_text("iv-notes-page", locale, current=page + 1, total=total_pages)
        )
        nav.append(
            InlineKeyboardButton(
                text=page_label,
                callback_data=InterviewCallback(
                    action="employer_qa", interview_id=interview_id, page=page
                ).pack(),
            )
        )
        if page < total_pages - 1:
            nav.append(
                InlineKeyboardButton(
                    text=_t("btn-notes-next", i18n, locale),
                    callback_data=InterviewCallback(
                        action="employer_qa",
                        interview_id=interview_id,
                        page=page + 1,
                    ).pack(),
                )
            )
        rows.append(nav)
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=_t("btn-iv-employer-qa-new", i18n, locale),
                    callback_data=InterviewCallback(
                        action="employer_qa_new", interview_id=interview_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t("btn-back", i18n, locale),
                    callback_data=InterviewCallback(
                        action="detail", interview_id=interview_id
                    ).pack(),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def employer_qa_cancel_keyboard(
    interview_id: int,
    i18n: I18nContext | None = None,
    locale: str = "ru",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t("btn-cancel", i18n, locale),
                    callback_data=InterviewCallback(
                        action="employer_qa_cancel", interview_id=interview_id
                    ).pack(),
                )
            ],
        ]
    )


def prep_steps_keyboard(
    steps: list,
    interview_id: int,
    i18n: I18nContext | None = None,
    locale: str = "ru",
) -> InlineKeyboardMarkup:
    from src.models.interview import PrepStepStatus

    status_icons = {
        PrepStepStatus.PENDING: "⏳",
        PrepStepStatus.SKIPPED: "⏭️",
        PrepStepStatus.COMPLETED: "✅",
    }
    rows = []
    for step in steps:
        icon = status_icons.get(step.status, "⏳")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{icon} {step.step_number}. {step.title[:40]}",
                    callback_data=InterviewCallback(
                        action="prep_step_detail",
                        interview_id=interview_id,
                        prep_step_id=step.id,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=_t("prep-btn-regenerate-plan", i18n, locale),
                callback_data=InterviewCallback(
                    action="prep_regenerate_plan",
                    interview_id=interview_id,
                ).pack(),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=_t("btn-back", i18n, locale),
                callback_data=InterviewCallback(action="detail", interview_id=interview_id).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def prep_step_detail_keyboard(
    step_id: int,
    interview_id: int,
    has_deep_summary: bool = False,
    has_test: bool = False,
    i18n: I18nContext | None = None,
    locale: str = "ru",
) -> InlineKeyboardMarkup:
    rows = []

    rows.append(
        [
            InlineKeyboardButton(
                text=_t("prep-btn-skip", i18n, locale),
                callback_data=InterviewCallback(
                    action="prep_skip",
                    interview_id=interview_id,
                    prep_step_id=step_id,
                ).pack(),
            ),
            InlineKeyboardButton(
                text=_t("prep-btn-continue", i18n, locale),
                callback_data=InterviewCallback(
                    action="prep_continue",
                    interview_id=interview_id,
                    prep_step_id=step_id,
                ).pack(),
            ),
        ]
    )

    if has_deep_summary:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t("prep-btn-view-deep", i18n, locale),
                    callback_data=InterviewCallback(
                        action="prep_step_deep",
                        interview_id=interview_id,
                        prep_step_id=step_id,
                    ).pack(),
                )
            ]
        )

    if has_test:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t("prep-btn-start-test", i18n, locale),
                    callback_data=InterviewCallback(
                        action="prep_test_enter",
                        interview_id=interview_id,
                        prep_step_id=step_id,
                    ).pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=_t("btn-back", i18n, locale),
                callback_data=InterviewCallback(
                    action="prep_steps", interview_id=interview_id
                ).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def deep_summary_keyboard(
    step_id: int,
    interview_id: int,
    has_test: bool = False,
    i18n: I18nContext | None = None,
    locale: str = "ru",
) -> InlineKeyboardMarkup:
    rows = []
    if not has_test:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t("prep-btn-create-test", i18n, locale),
                    callback_data=InterviewCallback(
                        action="prep_create_test",
                        interview_id=interview_id,
                        prep_step_id=step_id,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=_t("prep-btn-download", i18n, locale),
                callback_data=InterviewCallback(
                    action="prep_download",
                    interview_id=interview_id,
                    prep_step_id=step_id,
                ).pack(),
            ),
            InlineKeyboardButton(
                text=_t("prep-btn-regenerate", i18n, locale),
                callback_data=InterviewCallback(
                    action="prep_regenerate_deep",
                    interview_id=interview_id,
                    prep_step_id=step_id,
                ).pack(),
            ),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=_t("btn-back", i18n, locale),
                callback_data=InterviewCallback(
                    action="prep_step_detail",
                    interview_id=interview_id,
                    prep_step_id=step_id,
                ).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def download_options_keyboard(
    step_id: int,
    interview_id: int,
    i18n: I18nContext | None = None,
    locale: str = "ru",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t("prep-btn-download-md", i18n, locale),
                    callback_data=InterviewCallback(
                        action="prep_download_md",
                        interview_id=interview_id,
                        prep_step_id=step_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t("prep-btn-download-docs", i18n, locale),
                    callback_data=InterviewCallback(
                        action="prep_download_docs",
                        interview_id=interview_id,
                        prep_step_id=step_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t("btn-back", i18n, locale),
                    callback_data=InterviewCallback(
                        action="prep_download_back",
                        interview_id=interview_id,
                        prep_step_id=step_id,
                    ).pack(),
                )
            ],
        ]
    )


def test_question_keyboard(
    options: list[str],
    step_id: int,
    interview_id: int,
    q_index: int,
    total_questions: int,
    i18n: I18nContext | None = None,
    locale: str = "ru",
) -> InlineKeyboardMarkup:
    rows = []
    for i in range(len(options)):
        rows.append(
            [
                InlineKeyboardButton(
                    text=chr(65 + i),
                    callback_data=InterviewCallback(
                        action="prep_test_answer",
                        interview_id=interview_id,
                        prep_step_id=step_id,
                        test_q_index=q_index,
                        test_answer=i,
                    ).pack(),
                )
            ]
        )
    nav_row: list[InlineKeyboardButton] = []
    if q_index > 0:
        nav_row.append(
            InlineKeyboardButton(
                text=_t("prep-btn-prev", i18n, locale),
                callback_data=InterviewCallback(
                    action="prep_test",
                    interview_id=interview_id,
                    prep_step_id=step_id,
                    test_q_index=q_index - 1,
                ).pack(),
            )
        )
    if q_index < total_questions - 1:
        nav_row.append(
            InlineKeyboardButton(
                text=_t("prep-btn-next", i18n, locale),
                callback_data=InterviewCallback(
                    action="prep_test",
                    interview_id=interview_id,
                    prep_step_id=step_id,
                    test_q_index=q_index + 1,
                ).pack(),
            )
        )
    if nav_row:
        rows.append(nav_row)
    rows.append(
        [
            InlineKeyboardButton(
                text=_t("btn-back", i18n, locale),
                callback_data=InterviewCallback(
                    action="prep_step_detail",
                    interview_id=interview_id,
                    prep_step_id=step_id,
                ).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def test_results_keyboard(
    step_id: int,
    interview_id: int,
    i18n: I18nContext | None = None,
    locale: str = "ru",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t("prep-btn-extend-test", i18n, locale),
                    callback_data=InterviewCallback(
                        action="prep_extend_test",
                        interview_id=interview_id,
                        prep_step_id=step_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t("btn-back", i18n, locale),
                    callback_data=InterviewCallback(
                        action="prep_step_detail",
                        interview_id=interview_id,
                        prep_step_id=step_id,
                    ).pack(),
                )
            ],
        ]
    )


def improvement_detail_keyboard(
    interview_id: int,
    improvement_id: int,
    has_flow: bool,
    i18n: I18nContext | None = None,
    locale: str = "ru",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    if not has_flow:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t("btn-iv-generate-flow", i18n, locale),
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
                text=_t("btn-iv-set-improved", i18n, locale),
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
                text=_t("btn-iv-set-incorrect", i18n, locale),
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
                text=_t("btn-iv-back-improvements", i18n, locale),
                callback_data=InterviewCallback(action="detail", interview_id=interview_id).pack(),
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def company_review_view_keyboard(
    interview_id: int,
    i18n: I18nContext | None = None,
    locale: str = "ru",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t("btn-iv-regenerate", i18n, locale),
                    callback_data=InterviewCallback(
                        action="company_review_regenerate",
                        interview_id=interview_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t("btn-back", i18n, locale),
                    callback_data=InterviewCallback(
                        action="detail", interview_id=interview_id
                    ).pack(),
                )
            ],
        ]
    )


def questions_to_ask_view_keyboard(
    interview_id: int,
    i18n: I18nContext | None = None,
    locale: str = "ru",
    *,
    page: int = 0,
    total_pages: int = 1,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if total_pages > 1:
        nav: list[InlineKeyboardButton] = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text=_t("btn-notes-prev", i18n, locale),
                    callback_data=InterviewCallback(
                        action="questions_to_ask",
                        interview_id=interview_id,
                        page=page - 1,
                    ).pack(),
                )
            )
        from src.core.i18n import get_text

        page_label = (
            i18n.get("iv-notes-page", current=page + 1, total=total_pages)
            if i18n is not None
            else get_text("iv-notes-page", locale, current=page + 1, total=total_pages)
        )
        nav.append(
            InlineKeyboardButton(
                text=page_label,
                callback_data=InterviewCallback(
                    action="questions_to_ask", interview_id=interview_id, page=page
                ).pack(),
            )
        )
        if page < total_pages - 1:
            nav.append(
                InlineKeyboardButton(
                    text=_t("btn-notes-next", i18n, locale),
                    callback_data=InterviewCallback(
                        action="questions_to_ask",
                        interview_id=interview_id,
                        page=page + 1,
                    ).pack(),
                )
            )
        rows.append(nav)
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=_t("btn-iv-regenerate", i18n, locale),
                    callback_data=InterviewCallback(
                        action="questions_to_ask_regenerate",
                        interview_id=interview_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t("btn-notes-start", i18n, locale),
                    callback_data=InterviewCallback(
                        action="notes_start_from_questions",
                        interview_id=interview_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t("btn-back", i18n, locale),
                    callback_data=InterviewCallback(
                        action="detail", interview_id=interview_id
                    ).pack(),
                )
            ],
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


def notes_view_keyboard(
    interview_id: int,
    i18n: I18nContext | None = None,
    locale: str = "ru",
    is_noting: bool = False,
    *,
    page: int = 0,
    total_pages: int = 1,
    full_mode: bool = False,
    notes_count: int = 0,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    page_action = "notes_full" if full_mode else "notes"

    if is_noting:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t("btn-notes-stop", i18n, locale),
                    callback_data=InterviewCallback(
                        action="notes_stop", interview_id=interview_id
                    ).pack(),
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t("btn-notes-start", i18n, locale),
                    callback_data=InterviewCallback(
                        action="notes_start", interview_id=interview_id
                    ).pack(),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t("btn-notes-edit", i18n, locale),
                    callback_data=InterviewCallback(
                        action="notes_edit", interview_id=interview_id
                    ).pack(),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t("btn-notes-delete", i18n, locale),
                    callback_data=InterviewCallback(
                        action="notes_delete", interview_id=interview_id
                    ).pack(),
                )
            ]
        )
        if not full_mode and notes_count > 0:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=_t("btn-notes-output-all", i18n, locale),
                        callback_data=InterviewCallback(
                            action="notes_full",
                            interview_id=interview_id,
                            page=0,
                        ).pack(),
                    )
                ]
            )

    if total_pages > 1:
        nav_buttons: list[InlineKeyboardButton] = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(
                    text=_t("btn-notes-prev", i18n, locale),
                    callback_data=InterviewCallback(
                        action=page_action,
                        interview_id=interview_id,
                        page=page - 1,
                    ).pack(),
                )
            )
        page_label = (
            i18n.get("iv-notes-page", current=page + 1, total=total_pages)
            if i18n
            else f"{page + 1}/{total_pages}"
        )
        nav_buttons.append(
            InlineKeyboardButton(
                text=page_label,
                callback_data=InterviewCallback(
                    action=page_action,
                    interview_id=interview_id,
                    page=page,
                ).pack(),
            )
        )
        if page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton(
                    text=_t("btn-notes-next", i18n, locale),
                    callback_data=InterviewCallback(
                        action=page_action,
                        interview_id=interview_id,
                        page=page + 1,
                    ).pack(),
                )
            )
        if nav_buttons:
            rows.append(nav_buttons)

    rows.append(
        [
            InlineKeyboardButton(
                text=_t("btn-back", i18n, locale),
                callback_data=InterviewCallback(
                    action="detail", interview_id=interview_id
                ).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def notes_stop_noting_reply_keyboard(
    i18n: I18nContext | None = None,
    locale: str = "ru",
) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=_t("btn-notes-stop", i18n, locale)),
            ],
        ],
        resize_keyboard=True,
    )


def _cancel_button(i18n: I18nContext) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=i18n.get("btn-cancel"),
        callback_data=InterviewCallback(action="cancel").pack(),
    )
