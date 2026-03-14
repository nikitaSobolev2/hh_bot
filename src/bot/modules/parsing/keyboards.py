from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks.common import MenuCallback
from src.bot.modules.parsing.callbacks import (
    FormatCallback,
    KeyPhrasesCallback,
    ParsingCallback,
    WorkExperienceCallback,
)
from src.models.parsing import ParsingCompany
from src.models.work_experience import UserWorkExperience

if TYPE_CHECKING:
    from src.core.i18n import I18nContext

from src.core.constants import TASK_STATUS_ICONS as _STATUS_ICONS

KEY_PHRASES_STYLE_KEYS = ["formal", "results", "brief", "detailed", "expert"]

MAX_WORK_EXPERIENCES = 6

KEY_PHRASES_LANGUAGES = {
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
    "de": "🇩🇪 Deutsch",
    "fr": "🇫🇷 Français",
    "es": "🇪🇸 Español",
    "pt": "🇧🇷 Português",
    "zh": "🇨🇳 中文",
    "ja": "🇯🇵 日本語",
    "ko": "🇰🇷 한국어",
    "ar": "🇸🇦 العربية",
}


def _t(key: str, i18n: I18nContext | None = None, locale: str = "ru", **kwargs: str) -> str:
    """Resolve a translation key using i18n context or standalone get_text."""
    if i18n is not None:
        return i18n.get(key, **kwargs)
    from src.core.i18n import get_text

    return get_text(key, locale, **kwargs)


def get_style_label(style_key: str, i18n: I18nContext) -> str:
    return i18n.get(f"style-{style_key}")


def parsing_list_keyboard(
    companies: list[ParsingCompany], i18n: I18nContext
) -> InlineKeyboardMarkup:
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
                text=i18n.get("btn-back"),
                callback_data=MenuCallback(action="main").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_choice_keyboard(
    company_id: int,
    i18n: I18nContext | None = None,
    locale: str = "ru",
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t("btn-view-message", i18n, locale),
                    callback_data=FormatCallback(company_id=company_id, format="message").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t("btn-download-md", i18n, locale),
                    callback_data=FormatCallback(company_id=company_id, format="md").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t("btn-download-txt", i18n, locale),
                    callback_data=FormatCallback(company_id=company_id, format="txt").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t("btn-generate-keyphrases", i18n, locale),
                    callback_data=KeyPhrasesCallback(company_id=company_id, action="start").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t("btn-try-again", i18n, locale),
                    callback_data=ParsingCallback(action="retry", company_id=company_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t("parsing-btn-delete", i18n, locale),
                    callback_data=ParsingCallback(action="delete", company_id=company_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t("btn-back", i18n, locale),
                    callback_data=MenuCallback(action="my_parsings").pack(),
                )
            ],
        ]
    )


def back_to_company_keyboard(company_id: int, i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=ParsingCallback(action="detail", company_id=company_id).pack(),
                )
            ],
        ]
    )


def cancel_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )


def count_input_keyboard(company_id: int, i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip-count"),
                    callback_data=KeyPhrasesCallback(
                        company_id=company_id, action="skip_count"
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )


def compat_check_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-compat-yes"),
                    callback_data=ParsingCallback(action="compat_yes").pack(),
                ),
                InlineKeyboardButton(
                    text=i18n.get("btn-compat-skip"),
                    callback_data=ParsingCallback(action="compat_skip").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )


def retry_compat_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-compat-yes"),
                    callback_data=ParsingCallback(action="retry_compat_yes").pack(),
                ),
                InlineKeyboardButton(
                    text=i18n.get("btn-compat-skip"),
                    callback_data=ParsingCallback(action="retry_compat_skip").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )


def blacklist_choice_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip-blacklisted"),
                    callback_data=ParsingCallback(action="bl_skip").pack(),
                ),
                InlineKeyboardButton(
                    text=i18n.get("btn-include-all"),
                    callback_data=ParsingCallback(action="bl_include").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ]
    )


def parsing_pending_keyboard(company_id: int, i18n: I18nContext) -> InlineKeyboardMarkup:
    """Keyboard for pending/processing parsing (allows delete)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("parsing-btn-delete"),
                    callback_data=ParsingCallback(action="delete", company_id=company_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=MenuCallback(action="my_parsings").pack(),
                )
            ],
        ]
    )


def retry_keyboard(company_id: int, i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-try-again"),
                    callback_data=ParsingCallback(action="retry", company_id=company_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("parsing-btn-delete"),
                    callback_data=ParsingCallback(action="delete", company_id=company_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=MenuCallback(action="my_parsings").pack(),
                )
            ],
        ]
    )


def retry_count_keyboard(
    company_id: int, default_count: int, i18n: I18nContext
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-use-default", count=str(default_count)),
                    callback_data=ParsingCallback(
                        action="retry_use_default", company_id=company_id
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=ParsingCallback(
                        action="retry_cancel", company_id=company_id
                    ).pack(),
                )
            ],
        ]
    )


def language_selection_keyboard(
    company_id: int,
    count: int,
    i18n: I18nContext,
    mode: str = "",
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    items = list(KEY_PHRASES_LANGUAGES.items())
    for idx in range(0, len(items), 2):
        pair = items[idx : idx + 2]
        row = [
            InlineKeyboardButton(
                text=label,
                callback_data=KeyPhrasesCallback(
                    company_id=company_id,
                    action="select_lang",
                    count=count,
                    lang=key,
                    mode=mode,
                ).pack(),
            )
            for key, label in pair
        ]
        rows.append(row)
    if is_admin:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-type-manually"),
                    callback_data=KeyPhrasesCallback(
                        company_id=company_id,
                        action="lang_manual",
                        count=count,
                        mode=mode,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=ParsingCallback(action="detail", company_id=company_id).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def style_selection_keyboard(
    company_id: int,
    i18n: I18nContext,
    count: int = 10,
    lang: str = "ru",
    mode: str = "",
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for key in KEY_PHRASES_STYLE_KEYS:
        label = get_style_label(key, i18n)
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=KeyPhrasesCallback(
                        company_id=company_id,
                        action="select_style",
                        style=key,
                        count=count,
                        lang=lang,
                        mode=mode,
                    ).pack(),
                )
            ]
        )
    if is_admin:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-type-manually"),
                    callback_data=KeyPhrasesCallback(
                        company_id=company_id,
                        action="style_manual",
                        count=count,
                        lang=lang,
                        mode=mode,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=ParsingCallback(action="detail", company_id=company_id).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def work_experience_keyboard(
    company_id: int,
    experiences: list[UserWorkExperience],
    i18n: I18nContext,
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for exp in experiences:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"\u274c {i18n.get('btn-remove')} {exp.company_name}",
                    callback_data=WorkExperienceCallback(
                        action="remove",
                        company_id=company_id,
                        work_exp_id=exp.id,
                    ).pack(),
                )
            ]
        )

    if is_admin or len(experiences) < MAX_WORK_EXPERIENCES:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-add-company"),
                    callback_data=WorkExperienceCallback(
                        action="add", company_id=company_id
                    ).pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-skip"),
                callback_data=WorkExperienceCallback(action="skip", company_id=company_id).pack(),
            )
        ]
    )

    if experiences:
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-continue"),
                    callback_data=WorkExperienceCallback(
                        action="continue", company_id=company_id
                    ).pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=ParsingCallback(action="detail", company_id=company_id).pack(),
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_add_company_keyboard(company_id: int, i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=WorkExperienceCallback(
                        action="cancel_add", company_id=company_id
                    ).pack(),
                )
            ],
        ]
    )


def per_company_count_keyboard(company_id: int, i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=WorkExperienceCallback(
                        action="cancel_add", company_id=company_id
                    ).pack(),
                )
            ],
        ]
    )
