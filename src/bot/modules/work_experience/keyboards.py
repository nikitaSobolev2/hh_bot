"""Keyboard builders for the shared Work Experience module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.modules.work_experience.callbacks import WorkExpCallback

if TYPE_CHECKING:
    from src.core.i18n import I18nContext
    from src.models.work_experience import UserWorkExperience

MAX_WORK_EXPERIENCES = 6


def work_experience_keyboard(
    experiences: list[UserWorkExperience],
    return_to: str,
    i18n: I18nContext,
    *,
    show_continue: bool = False,
    show_skip: bool = False,
    disabled_exp_ids: set[int] | None = None,
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    """List view — each job is a clickable button leading to the detail view."""
    rows: list[list[InlineKeyboardButton]] = []
    disabled = disabled_exp_ids or set()

    for exp in experiences:
        prefix = "🚫 " if exp.id in disabled else "🏢 "
        label = f"{prefix}{exp.company_name}"
        if exp.title:
            label += f" — {exp.title}"
        if exp.period:
            label += f" ({exp.period})"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=WorkExpCallback(
                        action="detail",
                        work_exp_id=exp.id,
                        return_to=return_to,
                    ).pack(),
                )
            ]
        )

    if is_admin or len(experiences) < MAX_WORK_EXPERIENCES:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-add-company"),
                    callback_data=WorkExpCallback(
                        action="add",
                        return_to=return_to,
                    ).pack(),
                )
            ]
        )

    if show_skip:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip"),
                    callback_data=WorkExpCallback(
                        action="skip",
                        return_to=return_to,
                    ).pack(),
                )
            ]
        )

    if show_continue and experiences:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-continue"),
                    callback_data=WorkExpCallback(
                        action="continue",
                        return_to=return_to,
                    ).pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=WorkExpCallback(
                    action="back",
                    return_to=return_to,
                ).pack(),
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def work_exp_detail_keyboard(
    work_exp_id: int,
    return_to: str,
    i18n: I18nContext,
    *,
    show_resume_toggle: bool = False,
    is_disabled: bool = False,
) -> InlineKeyboardMarkup:
    """Detail view — buttons to edit each field and delete."""

    def _edit_btn(label: str, field: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=label,
            callback_data=WorkExpCallback(
                action="edit_field",
                work_exp_id=work_exp_id,
                return_to=return_to,
                field=field,
            ).pack(),
        )

    rows: list[list[InlineKeyboardButton]] = [
        [_edit_btn(i18n.get("we-btn-edit-company-name"), "company_name")],
        [_edit_btn(i18n.get("we-btn-edit-title"), "title")],
        [_edit_btn(i18n.get("we-btn-edit-period"), "period")],
        [_edit_btn(i18n.get("we-btn-edit-stack"), "stack")],
        [_edit_btn(i18n.get("we-btn-edit-achievements"), "achievements")],
        [_edit_btn(i18n.get("we-btn-edit-duties"), "duties")],
        [
            InlineKeyboardButton(
                text=i18n.get("we-btn-delete"),
                callback_data=WorkExpCallback(
                    action="delete",
                    work_exp_id=work_exp_id,
                    return_to=return_to,
                ).pack(),
            )
        ],
    ]

    if show_resume_toggle:
        toggle_label = (
            i18n.get("we-btn-enable-for-resume")
            if is_disabled
            else i18n.get("we-btn-disable-for-resume")
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=toggle_label,
                    callback_data=WorkExpCallback(
                        action="toggle_for_resume",
                        work_exp_id=work_exp_id,
                        return_to=return_to,
                    ).pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=WorkExpCallback(
                    action="view",
                    return_to=return_to,
                ).pack(),
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_add_keyboard(return_to: str, i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=WorkExpCallback(
                        action="cancel_add",
                        return_to=return_to,
                    ).pack(),
                )
            ]
        ]
    )


def work_exp_optional_keyboard(
    return_to: str,
    field: str,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """Skip + Cancel keyboard for optional creation steps (title, period)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip"),
                    callback_data=WorkExpCallback(
                        action="skip_field",
                        return_to=return_to,
                        field=field,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=WorkExpCallback(
                        action="cancel_add",
                        return_to=return_to,
                    ).pack(),
                )
            ],
        ]
    )


def work_exp_ai_input_keyboard(
    return_to: str,
    field: str,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """Generate with AI + Skip + Cancel keyboard for achievements/duties steps."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-generate-ai"),
                    callback_data=WorkExpCallback(
                        action="generate_ai",
                        return_to=return_to,
                        field=field,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip"),
                    callback_data=WorkExpCallback(
                        action="skip_field",
                        return_to=return_to,
                        field=field,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=WorkExpCallback(
                        action="cancel_add",
                        return_to=return_to,
                    ).pack(),
                )
            ],
        ]
    )


def cancel_edit_keyboard(
    work_exp_id: int,
    return_to: str,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """Cancel button during field editing — returns to detail view."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=WorkExpCallback(
                        action="detail",
                        work_exp_id=work_exp_id,
                        return_to=return_to,
                    ).pack(),
                )
            ]
        ]
    )


def work_exp_ai_result_keyboard(
    field: str,
    return_to: str,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    """Accept / Regenerate / Skip keyboard shown after AI draft is ready (create mode)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("we-btn-accept-draft"),
                    callback_data=WorkExpCallback(
                        action="accept_draft",
                        field=field,
                        return_to=return_to,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("we-btn-regenerate"),
                    callback_data=WorkExpCallback(
                        action="generate_ai",
                        field=field,
                        return_to=return_to,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip"),
                    callback_data=WorkExpCallback(
                        action="skip_field",
                        field=field,
                        return_to=return_to,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=WorkExpCallback(
                        action="back_to_input",
                        field=field,
                        return_to=return_to,
                    ).pack(),
                )
            ],
        ]
    )
