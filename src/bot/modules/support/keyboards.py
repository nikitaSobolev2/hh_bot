from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from src.bot.callbacks.common import MenuCallback
from src.bot.keyboards.pagination import build_paginated_keyboard
from src.bot.modules.support.callbacks import (
    SupportCallback,
    TicketAdminCallback,
    TicketFilterCallback,
    TicketSearchCallback,
)
from src.core.i18n import I18nContext
from src.models.support import SupportTicket

REMOVE_KEYBOARD = ReplyKeyboardRemove()


# ── User inline keyboards ─────────────────────────────────────


def user_ticket_list_keyboard(
    tickets: list[SupportTicket],
    page: int,
    has_more: bool,
    i18n: I18nContext,
    *,
    unseen_ticket_ids: set[int] | None = None,
) -> InlineKeyboardMarkup:
    unseen = unseen_ticket_ids or set()

    def _ticket_button(t: SupportTicket) -> InlineKeyboardButton:
        status_map = {"new": "🆕", "in_progress": "🔄", "closed": "✅"}
        icon = status_map.get(t.status, "📝")
        marker = " 💬" if t.id in unseen else ""
        label = f"{icon} {t.title[:40]}{marker}"
        return InlineKeyboardButton(
            text=label,
            callback_data=SupportCallback(action="detail", ticket_id=t.id).pack(),
        )

    return build_paginated_keyboard(
        items=tickets,
        item_to_button=_ticket_button,
        page=page,
        has_more=has_more,
        page_callback_factory=lambda p: SupportCallback(action="list", page=p).pack(),
        i18n=i18n,
        extra_rows=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-new-ticket"),
                    callback_data=SupportCallback(action="new").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back-menu"),
                    callback_data=MenuCallback(action="main").pack(),
                )
            ],
        ],
    )


def ticket_detail_keyboard(
    ticket: SupportTicket,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if ticket.status != "closed":
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-enter-conversation"),
                    callback_data=SupportCallback(
                        action="enter",
                        ticket_id=ticket.id,
                    ).pack(),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-close-ticket"),
                    callback_data=SupportCallback(
                        action="close_user",
                        ticket_id=ticket.id,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back-tickets"),
                callback_data=SupportCallback(action="list").pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def skip_attachments_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-skip-attachments"),
                    callback_data=SupportCallback(action="skip_attach").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-done-attachments"),
                    callback_data=SupportCallback(action="done_attach").pack(),
                )
            ],
        ]
    )


# ── User reply keyboard (conversation mode) ───────────────────


def user_conversation_keyboard(i18n: I18nContext) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=i18n.get("btn-quit-conversation")),
                KeyboardButton(text=i18n.get("btn-close-ticket")),
            ],
        ],
        resize_keyboard=True,
    )


# ── Admin inline keyboards (support channel message) ──────────


def ticket_channel_keyboard(
    ticket: SupportTicket,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    tid = ticket.id
    uid = ticket.user_id
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-take-into-work"),
                    callback_data=TicketAdminCallback(
                        action="take",
                        ticket_id=tid,
                        user_id=uid,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-view-profile"),
                    callback_data=TicketAdminCallback(
                        action="profile",
                        ticket_id=tid,
                        user_id=uid,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=i18n.get("btn-check-companies"),
                    callback_data=TicketAdminCallback(
                        action="companies",
                        ticket_id=tid,
                        user_id=uid,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-check-tickets"),
                    callback_data=TicketAdminCallback(
                        action="tickets",
                        ticket_id=tid,
                        user_id=uid,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=i18n.get("btn-check-notifications"),
                    callback_data=TicketAdminCallback(
                        action="notifications",
                        ticket_id=tid,
                        user_id=uid,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-ban"),
                    callback_data=TicketAdminCallback(
                        action="ban",
                        ticket_id=tid,
                        user_id=uid,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=i18n.get("btn-close-ticket-admin"),
                    callback_data=TicketAdminCallback(
                        action="close",
                        ticket_id=tid,
                        user_id=uid,
                    ).pack(),
                ),
            ],
        ]
    )


# ── Admin inbox keyboards ─────────────────────────────────────


def admin_inbox_keyboard(
    tickets: list[SupportTicket],
    page: int,
    has_more: bool,
    i18n: I18nContext,
    *,
    current_filter: str = "",
    unseen_ticket_ids: set[int] | None = None,
) -> InlineKeyboardMarkup:
    unseen = unseen_ticket_ids or set()

    def _ticket_button(t: SupportTicket) -> InlineKeyboardButton:
        status_map = {"new": "🆕", "in_progress": "🔄", "closed": "✅"}
        icon = status_map.get(t.status, "📝")
        marker = " 💬" if t.id in unseen else ""
        admin_label = ""
        if t.admin:
            admin_label = f" → @{t.admin.username or t.admin.first_name}"
        label = f"{icon} {t.title[:30]}{admin_label}{marker}"
        return InlineKeyboardButton(
            text=label,
            callback_data=TicketAdminCallback(
                action="view",
                ticket_id=t.id,
                user_id=t.user_id,
            ).pack(),
        )

    filter_row: list[InlineKeyboardButton] = []
    for status_val, status_label in [
        ("", i18n.get("btn-filter-all")),
        ("new", i18n.get("btn-filter-new")),
        ("in_progress", i18n.get("btn-filter-progress")),
        ("closed", i18n.get("btn-filter-closed")),
    ]:
        prefix = "▪️ " if status_val == current_filter else ""
        filter_row.append(
            InlineKeyboardButton(
                text=f"{prefix}{status_label}",
                callback_data=TicketFilterCallback(status=status_val, page=0).pack(),
            )
        )

    return build_paginated_keyboard(
        items=tickets,
        item_to_button=_ticket_button,
        page=page,
        has_more=has_more,
        page_callback_factory=lambda p: TicketFilterCallback(
            status=current_filter,
            page=p,
        ).pack(),
        i18n=i18n,
        extra_rows=[
            filter_row,
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-search"),
                    callback_data=TicketSearchCallback(action="prompt").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-back"),
                    callback_data=MenuCallback(action="admin").pack(),
                )
            ],
        ],
    )


def admin_ticket_detail_keyboard(
    ticket: SupportTicket,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    tid = ticket.id
    uid = ticket.user_id
    rows: list[list[InlineKeyboardButton]] = []

    if ticket.status == "new":
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-take-into-work"),
                    callback_data=TicketAdminCallback(
                        action="take",
                        ticket_id=tid,
                        user_id=uid,
                    ).pack(),
                )
            ]
        )
    elif ticket.status == "in_progress":
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-enter-conversation"),
                    callback_data=TicketAdminCallback(
                        action="enter_conv",
                        ticket_id=tid,
                        user_id=uid,
                    ).pack(),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-view-profile"),
                callback_data=TicketAdminCallback(
                    action="profile",
                    ticket_id=tid,
                    user_id=uid,
                ).pack(),
            ),
            InlineKeyboardButton(
                text=i18n.get("btn-check-companies"),
                callback_data=TicketAdminCallback(
                    action="companies",
                    ticket_id=tid,
                    user_id=uid,
                ).pack(),
            ),
        ]
    )
    if ticket.status != "closed":
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-close-ticket-admin"),
                    callback_data=TicketAdminCallback(
                        action="close",
                        ticket_id=tid,
                        user_id=uid,
                    ).pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.get("btn-back"),
                callback_data=TicketFilterCallback(status="", page=0).pack(),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ── Admin reply keyboard (conversation mode) ──────────────────


def admin_conversation_keyboard(i18n: I18nContext) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=i18n.get("btn-quit-conversation")),
                KeyboardButton(text=i18n.get("btn-close-ticket-admin")),
            ],
            [
                KeyboardButton(text=i18n.get("btn-view-profile")),
                KeyboardButton(text=i18n.get("btn-check-companies")),
            ],
            [
                KeyboardButton(text=i18n.get("btn-check-tickets")),
                KeyboardButton(text=i18n.get("btn-check-notifications")),
            ],
            [
                KeyboardButton(text=i18n.get("btn-ban")),
                KeyboardButton(text=i18n.get("btn-message-history")),
            ],
        ],
        resize_keyboard=True,
    )


# ── Ban flow keyboards ────────────────────────────────────────


def ban_cancel_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=TicketAdminCallback(action="cancel_ban").pack(),
                )
            ],
        ]
    )


# ── Close flow keyboards ──────────────────────────────────────


def close_cancel_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=TicketAdminCallback(action="cancel_close").pack(),
                )
            ],
        ]
    )


def close_status_keyboard(i18n: I18nContext) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-status-valid"),
                    callback_data="close_status:valid",
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-status-invalid"),
                    callback_data="close_status:invalid",
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-status-bug"),
                    callback_data="close_status:bug",
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.get("btn-cancel"),
                    callback_data=TicketAdminCallback(action="cancel_close").pack(),
                )
            ],
        ]
    )
