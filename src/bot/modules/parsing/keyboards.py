from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.parsing.callbacks import (
    FormatCallback,
    KeyPhrasesCallback,
    ParsingCallback,
)
from src.models.parsing import ParsingCompany

_BACK = "◀️ Back"

_STATUS_ICONS = {
    "pending": "⏳",
    "processing": "🔄",
    "completed": "✅",
    "failed": "❌",
}

KEY_PHRASES_STYLES = {
    "formal": "формальный / деловой",
    "results": "результато-ориентированный (метрики и достижения)",
    "brief": "лаконичный / телеграфный",
    "detailed": "описательный / подробный",
    "expert": "экспертный / профессиональный",
}


def parsing_list_keyboard(companies: list[ParsingCompany]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for c in companies:
        icon = _STATUS_ICONS.get(c.status, "❓")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{icon} {c.vacancy_title} ({c.created_at.strftime('%m/%d')})",
                    callback_data=ParsingCallback(action="detail", company_id=c.id).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=_BACK,
                callback_data=MenuCallback(action="main").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_choice_keyboard(company_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💬 View as Message",
                    callback_data=FormatCallback(company_id=company_id, format="message").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📄 Download .md",
                    callback_data=FormatCallback(company_id=company_id, format="md").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📝 Download .txt",
                    callback_data=FormatCallback(company_id=company_id, format="txt").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✨ Generate Key Phrases (AI Stream)",
                    callback_data=KeyPhrasesCallback(
                        company_id=company_id, action="start"
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_BACK,
                    callback_data=ParsingCallback(
                        action="detail", company_id=company_id
                    ).pack(),
                )
            ],
        ]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )


def blacklist_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Skip blacklisted",
                    callback_data=ParsingCallback(action="bl_skip").pack(),
                ),
                InlineKeyboardButton(
                    text="🔄 Include all",
                    callback_data=ParsingCallback(action="bl_include").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )


def style_selection_keyboard(company_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key, label in KEY_PHRASES_STYLES.items():
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=KeyPhrasesCallback(
                        company_id=company_id,
                        action="select_style",
                        style=key,
                        count=15,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=_BACK,
                callback_data=ParsingCallback(
                    action="detail", company_id=company_id
                ).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
