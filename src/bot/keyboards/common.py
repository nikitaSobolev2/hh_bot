"""Main menu and common navigation keyboards.

Layout design:
- Job Search section: Parsing, Autoparse
- Resume section: Work Experience, Achievements, AI from notes (achievements/duties),
  Vacancy Summary, Resume
- Interview section: My Interviews, Interview Q&A
- Account section: Profile, Settings, Support
- Admin section (admin-only): Admin Panel
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.bot.callbacks.common import MenuCallback
from src.core.i18n import I18nContext


def main_menu_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    """Structured main menu with logical section grouping."""
    builder = InlineKeyboardBuilder()

    builder.button(
        text=i18n.get("btn-new-parsing"),
        callback_data=MenuCallback(action="new_parsing").pack(),
    )
    builder.button(
        text=i18n.get("btn-my-parsings"),
        callback_data=MenuCallback(action="my_parsings").pack(),
    )
    builder.button(
        text=i18n.get("btn-autoparse"),
        callback_data=MenuCallback(action="autoparse").pack(),
    )
    builder.row(
        InlineKeyboardButton(
            text=i18n.get("btn-task-group-run"),
            callback_data=MenuCallback(action="task_group_run").pack(),
        ),
        InlineKeyboardButton(
            text=i18n.get("btn-task-group-settings"),
            callback_data=MenuCallback(action="task_group_settings").pack(),
        ),
    )

    builder.button(
        text=i18n.get("btn-my-interviews"),
        callback_data=MenuCallback(action="my_interviews").pack(),
    )
    builder.button(
        text=i18n.get("btn-interview-qa"),
        callback_data=MenuCallback(action="interview_qa").pack(),
    )

    builder.button(
        text=i18n.get("btn-work-experience"),
        callback_data=MenuCallback(action="work_experience").pack(),
    )
    builder.button(
        text=i18n.get("btn-achievements"),
        callback_data=MenuCallback(action="achievements").pack(),
    )
    builder.button(
        text=i18n.get("btn-we-from-text-achievements"),
        callback_data=MenuCallback(action="we_from_text_achievements").pack(),
    )
    builder.button(
        text=i18n.get("btn-we-from-text-duties"),
        callback_data=MenuCallback(action="we_from_text_duties").pack(),
    )
    builder.button(
        text=i18n.get("btn-we-improve-stack"),
        callback_data=MenuCallback(action="we_improve_stack").pack(),
    )
    builder.button(
        text=i18n.get("btn-vacancy-summary"),
        callback_data=MenuCallback(action="vacancy_summary").pack(),
    )
    builder.button(
        text=i18n.get("btn-resume"),
        callback_data=MenuCallback(action="resume").pack(),
    )
    builder.button(
        text=i18n.get("btn-cover-letter"),
        callback_data=MenuCallback(action="cover_letter").pack(),
    )

    builder.button(
        text=i18n.get("btn-profile"),
        callback_data=MenuCallback(action="profile").pack(),
    )
    builder.button(
        text=i18n.get("btn-settings"),
        callback_data=MenuCallback(action="settings").pack(),
    )
    builder.button(
        text=i18n.get("btn-support-user"),
        callback_data=MenuCallback(action="support").pack(),
    )

    builder.adjust(2, 1, 2, 2, 2, 3, 2, 1, 2, 1)
    return builder.as_markup()


def main_menu_admin_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    """Main menu with admin section appended."""
    kb = main_menu_keyboard(i18n)
    kb.inline_keyboard.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-admin"),
                callback_data=MenuCallback(action="admin").pack(),
            ),
            InlineKeyboardButton(
                text=i18n.get("btn-admin-generate-vacancy-prep-query"),
                callback_data=MenuCallback(action="generate_vacancy_prep_query").pack(),
            ),
        ]
    )
    return kb


def back_to_menu_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    """Single back-to-main-menu button."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=i18n.get("btn-back-menu"),
        callback_data=MenuCallback(action="main").pack(),
    )
    return builder.as_markup()
