import contextlib
import re
from datetime import UTC, datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.filters.admin import AdminFilter
from src.bot.keyboards.common import back_to_menu_keyboard
from src.bot.keyboards.pagination import build_paginated_keyboard
from src.bot.modules.parsing import services as parsing_svc
from src.bot.modules.support import services as support_svc
from src.bot.modules.support.callbacks import (
    TicketAdminCallback,
    TicketFilterCallback,
    TicketSearchCallback,
)
from src.bot.modules.support.keyboards import (
    REMOVE_KEYBOARD,
    admin_conversation_keyboard,
    admin_inbox_keyboard,
    admin_ticket_detail_keyboard,
    ban_cancel_keyboard,
    close_cancel_keyboard,
    close_status_keyboard,
)
from src.bot.modules.support.states import AdminConversation, AdminTicketSearch
from src.config import settings
from src.core.i18n import I18nContext, get_text
from src.models.user import User

router = Router(name="support_admin")
router.callback_query.filter(AdminFilter())
router.message.filter(AdminFilter())

_PERIOD_RE = re.compile(r"^(\d+)([dhm])$", re.IGNORECASE)


# ── Admin inbox ──────────────────────────────────────────────


async def show_admin_inbox(
    callback: CallbackQuery,
    session: AsyncSession,
    i18n: I18nContext,
    *,
    status: str = "",
    page: int = 0,
) -> None:
    tickets, has_more = await support_svc.get_all_tickets_filtered(
        session,
        status=status,
        page=page,
    )

    if not tickets and page == 0:
        await callback.message.edit_text(
            f"{i18n.get('support-inbox-title')}\n\n{i18n.get('support-inbox-empty')}",
            reply_markup=admin_inbox_keyboard(
                [],
                0,
                False,
                i18n,
                current_filter=status,
            ),
        )
        return

    unseen_ids = await support_svc.get_unseen_ticket_ids(
        session,
        [t.id for t in tickets],
    )

    await callback.message.edit_text(
        i18n.get("support-inbox-title"),
        reply_markup=admin_inbox_keyboard(
            tickets,
            page,
            has_more,
            i18n,
            current_filter=status,
            unseen_ticket_ids=unseen_ids,
        ),
    )


# ── Inbox filter & pagination ────────────────────────────────


@router.callback_query(TicketFilterCallback.filter())
async def inbox_filter(
    callback: CallbackQuery,
    callback_data: TicketFilterCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await show_admin_inbox(
        callback,
        session,
        i18n,
        status=callback_data.status,
        page=callback_data.page,
    )
    await callback.answer()


# ── Inbox search ─────────────────────────────────────────────


@router.callback_query(TicketSearchCallback.filter(F.action == "prompt"))
async def search_prompt(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.set_state(AdminTicketSearch.waiting_query)
    await callback.message.edit_text(
        i18n.get("support-search-prompt"),
        reply_markup=back_to_menu_keyboard(i18n),
    )
    await callback.answer()


@router.message(AdminTicketSearch.waiting_query)
async def handle_ticket_search(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    query = (message.text or "").strip()
    await state.clear()

    tickets, has_more = await support_svc.get_all_tickets_filtered(
        session,
        query=query,
        page=0,
    )

    if not tickets:
        await message.answer(
            i18n.get("support-search-empty", query=query),
            reply_markup=back_to_menu_keyboard(i18n),
        )
        return

    unseen_ids = await support_svc.get_unseen_ticket_ids(
        session,
        [t.id for t in tickets],
    )
    await message.answer(
        i18n.get("support-search-results", query=query),
        reply_markup=admin_inbox_keyboard(
            tickets,
            0,
            has_more,
            i18n,
            unseen_ticket_ids=unseen_ids,
        ),
    )


# ── Admin ticket detail (from inbox) ─────────────────────────


@router.callback_query(TicketAdminCallback.filter(F.action == "view"))
async def admin_ticket_view(
    callback: CallbackQuery,
    callback_data: TicketAdminCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    ticket = await support_svc.get_ticket(session, callback_data.ticket_id)
    if not ticket:
        await callback.answer(i18n.get("parsing-not-found"), show_alert=True)
        return

    status_map = {
        "new": i18n.get("support-ticket-status-new"),
        "in_progress": i18n.get("support-ticket-status-progress"),
        "closed": i18n.get("support-ticket-status-closed"),
    }
    text = i18n.get(
        "support-ticket-detail",
        id=str(ticket.id),
        title=ticket.title,
        status=status_map.get(ticket.status, ticket.status),
        date=ticket.created_at.strftime("%Y-%m-%d %H:%M"),
    )
    await callback.message.edit_text(
        text,
        reply_markup=admin_ticket_detail_keyboard(ticket, i18n),
    )
    await callback.answer()


# ── Take into work ───────────────────────────────────────────


@router.callback_query(TicketAdminCallback.filter(F.action == "take"))
async def take_ticket(
    callback: CallbackQuery,
    callback_data: TicketAdminCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    ticket = await support_svc.take_ticket(
        session,
        callback_data.ticket_id,
        user.id,
    )
    if not ticket:
        await callback.answer(i18n.get("support-already-taken"), show_alert=True)
        return

    text = i18n.get(
        "support-taken",
        id=str(ticket.id),
        title=ticket.title,
        description=ticket.description[:500],
    )
    reply_chat_id = callback.message.chat.id
    await callback.bot.send_message(
        reply_chat_id,
        text,
        reply_markup=admin_conversation_keyboard(i18n),
    )

    attachments = await support_svc.get_ticket_attachments(session, ticket.id)
    for att in attachments:
        await support_svc._send_attachment(callback.bot, reply_chat_id, att)

    unseen_count = await support_svc.deliver_unseen_to_admin(
        session,
        callback.bot,
        ticket.id,
        reply_chat_id,
        locale=user.language_code or "ru",
    )
    if unseen_count:
        await callback.bot.send_message(
            reply_chat_id,
            i18n.get("support-unseen-delivered", count=str(unseen_count)),
        )

    await state.set_state(AdminConversation.chatting)
    await state.update_data(
        ticket_id=ticket.id,
        target_user_id=ticket.user_id,
    )

    channel_id = settings.support_chat_id
    if channel_id and ticket.channel_message_id:
        admin_link = f"https://t.me/{user.username}" if user.username else ""
        taken_label = i18n.get("support-taken-popup", id=str(ticket.id))
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"👤 @{user.username}" if user.username else taken_label,
                url=admin_link or f"tg://user?id={user.telegram_id}",
            )],
        ])
        with contextlib.suppress(Exception):
            await callback.bot.edit_message_reply_markup(
                chat_id=int(channel_id),
                message_id=ticket.channel_message_id,
                reply_markup=kb,
            )

    await callback.answer(i18n.get("support-taken-popup", id=str(ticket.id)))


# ── Enter conversation from inbox detail ─────────────────────


@router.callback_query(TicketAdminCallback.filter(F.action == "enter_conv"))
async def enter_admin_conversation(
    callback: CallbackQuery,
    callback_data: TicketAdminCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    ticket = await support_svc.get_ticket(session, callback_data.ticket_id)
    if not ticket or ticket.status == "closed":
        await callback.answer(i18n.get("support-ticket-already-closed"), show_alert=True)
        return

    text = i18n.get(
        "support-taken",
        id=str(ticket.id),
        title=ticket.title,
        description=ticket.description[:500],
    )
    await callback.bot.send_message(
        user.telegram_id,
        text,
        reply_markup=admin_conversation_keyboard(i18n),
    )

    unseen_count = await support_svc.deliver_unseen_to_admin(
        session,
        callback.bot,
        ticket.id,
        user.telegram_id,
        locale=user.language_code or "ru",
    )
    if unseen_count:
        await callback.bot.send_message(
            user.telegram_id,
            i18n.get("support-unseen-delivered", count=str(unseen_count)),
        )

    await state.set_state(AdminConversation.chatting)
    await state.update_data(
        ticket_id=ticket.id,
        target_user_id=ticket.user_id,
    )
    await callback.answer()


# ── Channel inline button actions ─────────────────────────────


@router.callback_query(TicketAdminCallback.filter(F.action == "profile"))
async def view_user_profile(
    callback: CallbackQuery,
    callback_data: TicketAdminCallback,
    session: AsyncSession,
    user: User,
    i18n: I18nContext,
) -> None:
    profile_text = await support_svc.format_user_profile_support(
        session,
        callback_data.user_id,
        locale=user.language_code or "ru",
    )
    await callback.bot.send_message(callback.message.chat.id, profile_text)
    await callback.answer()


@router.callback_query(TicketAdminCallback.filter(F.action == "companies"))
async def view_user_companies(
    callback: CallbackQuery,
    callback_data: TicketAdminCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    page = callback_data.page
    companies, has_more = await support_svc.get_user_companies_page(
        session,
        callback_data.user_id,
        page,
    )

    chat_id = callback.message.chat.id

    if not companies:
        await callback.bot.send_message(
            chat_id,
            i18n.get("support-companies-empty"),
        )
        await callback.answer()
        return

    def _company_btn(c) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=f"📋 {c.vacancy_title} ({c.status})",
            callback_data=TicketAdminCallback(
                action="company_detail",
                ticket_id=callback_data.ticket_id,
                user_id=callback_data.user_id,
                page=c.id,
            ).pack(),
        )

    kb = build_paginated_keyboard(
        items=companies,
        item_to_button=_company_btn,
        page=page,
        has_more=has_more,
        page_callback_factory=lambda p: TicketAdminCallback(
            action="companies",
            ticket_id=callback_data.ticket_id,
            user_id=callback_data.user_id,
            page=p,
        ).pack(),
        i18n=i18n,
    )
    await callback.bot.send_message(
        chat_id,
        f"<b>{i18n.get('btn-check-companies')}</b>",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(TicketAdminCallback.filter(F.action == "tickets"))
async def view_user_tickets(
    callback: CallbackQuery,
    callback_data: TicketAdminCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    page = callback_data.page
    tickets, has_more = await support_svc.get_user_tickets_page_admin(
        session,
        callback_data.user_id,
        page,
    )

    chat_id = callback.message.chat.id

    if not tickets:
        await callback.bot.send_message(
            chat_id,
            i18n.get("support-tickets-empty"),
        )
        await callback.answer()
        return

    def _ticket_btn(t) -> InlineKeyboardButton:
        status_map = {"new": "🆕", "in_progress": "🔄", "closed": "✅"}
        icon = status_map.get(t.status, "📝")
        return InlineKeyboardButton(
            text=f"{icon} {t.title[:40]}",
            callback_data=TicketAdminCallback(
                action="view",
                ticket_id=t.id,
                user_id=callback_data.user_id,
            ).pack(),
        )

    kb = build_paginated_keyboard(
        items=tickets,
        item_to_button=_ticket_btn,
        page=page,
        has_more=has_more,
        page_callback_factory=lambda p: TicketAdminCallback(
            action="tickets",
            ticket_id=callback_data.ticket_id,
            user_id=callback_data.user_id,
            page=p,
        ).pack(),
        i18n=i18n,
    )
    await callback.bot.send_message(
        chat_id,
        f"<b>{i18n.get('btn-check-tickets')}</b>",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(TicketAdminCallback.filter(F.action == "notifications"))
async def view_notifications(
    callback: CallbackQuery,
    user: User,
    i18n: I18nContext,
) -> None:
    await callback.bot.send_message(
        callback.message.chat.id,
        i18n.get("support-notifications-soon"),
    )
    await callback.answer()


@router.callback_query(TicketAdminCallback.filter(F.action == "noop"))
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()


# ── Company detail (from company list) ───────────────────────


def _company_format_keyboard(
    company_id: int,
    i18n: I18nContext,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=i18n.get("btn-view-message"),
                callback_data=TicketAdminCallback(action="fmt_msg", page=company_id).pack(),
            )],
            [InlineKeyboardButton(
                text=i18n.get("btn-download-md"),
                callback_data=TicketAdminCallback(action="fmt_md", page=company_id).pack(),
            )],
            [InlineKeyboardButton(
                text=i18n.get("btn-download-txt"),
                callback_data=TicketAdminCallback(action="fmt_txt", page=company_id).pack(),
            )],
        ]
    )


@router.callback_query(TicketAdminCallback.filter(F.action == "company_detail"))
async def view_company_detail(
    callback: CallbackQuery,
    callback_data: TicketAdminCallback,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company = await parsing_svc.get_company_with_details(session, callback_data.page)
    if not company:
        await callback.answer(i18n.get("parsing-not-found"), show_alert=True)
        return

    text = parsing_svc.format_company_detail(company, i18n)
    kb = _company_format_keyboard(company.id, i18n) if company.status == "completed" else None
    await callback.bot.send_message(callback.message.chat.id, text, reply_markup=kb)
    await callback.answer()


@router.callback_query(TicketAdminCallback.filter(F.action.in_({"fmt_msg", "fmt_md", "fmt_txt"})))
async def admin_format_selection(
    callback: CallbackQuery,
    callback_data: TicketAdminCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    company_id = callback_data.page
    company = await parsing_svc.get_company_by_id(session, company_id)
    if not company:
        await callback.answer(i18n.get("parsing-not-found"), show_alert=True)
        return

    agg = await parsing_svc.get_aggregated_result(session, company_id)
    if not agg:
        await callback.answer(i18n.get("parsing-no-results"), show_alert=True)
        return

    locale = user.language_code or "ru"
    report = parsing_svc.build_report(company, agg, locale=locale)
    fmt = callback_data.action.removeprefix("fmt_")

    if fmt == "msg":
        text = report.generate_message()
        if len(text) > 4000:
            text = text[:3950] + "\n\n" + i18n.get("parsing-truncated")
        await callback.bot.send_message(callback.message.chat.id, text)
    elif fmt in ("md", "txt"):
        content = report.generate_md() if fmt == "md" else report.generate_txt()
        doc = parsing_svc.generate_document(
            content, f"report_{company.vacancy_title}_{company.id}.{fmt}"
        )
        await callback.message.answer_document(doc)

    await callback.answer()


# ── Ban from channel/inline buttons ──────────────────────────


@router.callback_query(TicketAdminCallback.filter(F.action == "ban"))
async def ban_prompt(
    callback: CallbackQuery,
    callback_data: TicketAdminCallback,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.set_state(AdminConversation.ban_period)
    await state.update_data(
        ticket_id=callback_data.ticket_id,
        target_user_id=callback_data.user_id,
    )
    await callback.bot.send_message(
        callback.message.chat.id,
        i18n.get("support-ban-enter-period"),
        reply_markup=ban_cancel_keyboard(i18n),
    )
    await callback.answer()


@router.callback_query(TicketAdminCallback.filter(F.action == "cancel_ban"))
async def cancel_ban(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    was_in_conversation = data.get("from_conversation", False)
    ticket_id = data.get("ticket_id")
    target_user_id = data.get("target_user_id")

    if was_in_conversation:
        await state.set_state(AdminConversation.chatting)
        await state.update_data(ticket_id=ticket_id, target_user_id=target_user_id)
        await callback.message.edit_text(i18n.get("support-ban-cancelled"))
        await callback.message.answer(
            i18n.get("support-ban-cancelled"),
            reply_markup=admin_conversation_keyboard(i18n),
        )
    else:
        await state.clear()
        await callback.message.edit_text(i18n.get("support-ban-cancelled"))

    await callback.answer()


# ── Close from channel/inline buttons ────────────────────────


@router.callback_query(TicketAdminCallback.filter(F.action == "close"))
async def close_prompt(
    callback: CallbackQuery,
    callback_data: TicketAdminCallback,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.set_state(AdminConversation.close_result)
    await state.update_data(
        ticket_id=callback_data.ticket_id,
        target_user_id=callback_data.user_id,
    )
    await callback.bot.send_message(
        callback.message.chat.id,
        i18n.get("support-close-enter-result"),
        reply_markup=close_cancel_keyboard(i18n),
    )
    await callback.answer()


@router.callback_query(TicketAdminCallback.filter(F.action == "cancel_close"))
async def cancel_close(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    was_in_conversation = data.get("from_conversation", False)
    ticket_id = data.get("ticket_id")
    target_user_id = data.get("target_user_id")

    if was_in_conversation:
        await state.set_state(AdminConversation.chatting)
        await state.update_data(ticket_id=ticket_id, target_user_id=target_user_id)
        await callback.message.edit_text(i18n.get("support-close-cancelled"))
        await callback.message.answer(
            i18n.get("support-close-cancelled"),
            reply_markup=admin_conversation_keyboard(i18n),
        )
    else:
        await state.clear()
        await callback.message.edit_text(i18n.get("support-close-cancelled"))

    await callback.answer()


# ── Admin conversation mode ──────────────────────────────────


@router.message(AdminConversation.close_result)
async def close_result_entered(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    result_text = (message.text or "").strip()
    if not result_text:
        await message.answer(i18n.get("support-close-enter-result"))
        return
    await state.update_data(close_result=result_text)
    await state.set_state(AdminConversation.close_status)
    await message.answer(
        i18n.get("support-close-select-status"),
        reply_markup=close_status_keyboard(i18n),
    )


@router.callback_query(
    AdminConversation.close_status,
    F.data.startswith("close_status:"),
)
async def close_status_selected(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    status = callback.data.split(":", 1)[1]
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    close_result = data.get("close_result", "")

    await state.clear()

    ticket = await support_svc.close_ticket(
        session,
        ticket_id,
        close_result=close_result,
        close_status=status,
    )

    status_labels = {"valid": "✅", "invalid": "❌", "bug": "🐛"}
    status_label = status_labels.get(status, status)

    await callback.message.edit_text(
        i18n.get(
            "support-ticket-closed-admin",
            id=str(ticket_id),
            result=close_result,
            status=status_label,
        ),
    )
    await callback.bot.send_message(
        callback.message.chat.id,
        i18n.get("support-conversation-left"),
        reply_markup=REMOVE_KEYBOARD,
    )

    if ticket and ticket.user:
        locale = ticket.user.language_code or "ru"
        with contextlib.suppress(Exception):
            await callback.bot.send_message(
                ticket.user.telegram_id,
                get_text(
                    "support-ticket-closed-notify-user",
                    locale,
                    id=str(ticket_id),
                    result=close_result,
                    status=status_label,
                ),
            )

    await callback.answer()


@router.message(AdminConversation.ban_period)
async def ban_period_entered(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    raw = (message.text or "").strip()

    if raw == "0":
        await state.update_data(ban_until=None, ban_period_label="∞")
        await state.set_state(AdminConversation.ban_reason)
        await message.answer(
            i18n.get("support-ban-enter-reason"),
            reply_markup=ban_cancel_keyboard(i18n),
        )
        return

    match = _PERIOD_RE.match(raw)
    if not match:
        await message.answer(
            i18n.get("support-ban-invalid-period"),
            reply_markup=ban_cancel_keyboard(i18n),
        )
        return

    amount, unit = int(match.group(1)), match.group(2).lower()
    delta_map = {
        "d": timedelta(days=amount),
        "h": timedelta(hours=amount),
        "m": timedelta(minutes=amount),
    }
    delta = delta_map.get(unit)
    if not delta:
        await message.answer(
            i18n.get("support-ban-invalid-period"),
            reply_markup=ban_cancel_keyboard(i18n),
        )
        return

    ban_until = datetime.now(UTC) + delta
    await state.update_data(
        ban_until=ban_until.isoformat(),
        ban_period_label=raw,
    )
    await state.set_state(AdminConversation.ban_reason)
    await message.answer(
        i18n.get("support-ban-enter-reason"),
        reply_markup=ban_cancel_keyboard(i18n),
    )


@router.message(AdminConversation.ban_reason)
async def ban_reason_entered(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    reason = (message.text or "").strip()
    if not reason:
        await message.answer(
            i18n.get("support-ban-enter-reason"),
            reply_markup=ban_cancel_keyboard(i18n),
        )
        return

    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    ticket_id = data.get("ticket_id")
    ban_until_str = data.get("ban_until")
    period_label = data.get("ban_period_label", "∞")

    ban_until = datetime.fromisoformat(ban_until_str) if ban_until_str else None

    await support_svc.ban_user(
        session,
        user_id=target_user_id,
        admin_id=user.id,
        reason=reason,
        banned_until=ban_until,
        ticket_id=ticket_id,
    )

    was_in_conversation = data.get("from_conversation", False)
    if was_in_conversation:
        await state.set_state(AdminConversation.chatting)
        await state.update_data(
            ticket_id=ticket_id,
            target_user_id=target_user_id,
        )
    else:
        await state.clear()

    await message.answer(
        i18n.get("support-ban-applied", period=period_label, reason=reason),
        reply_markup=admin_conversation_keyboard(i18n) if was_in_conversation else REMOVE_KEYBOARD,
    )


async def _conv_show_companies(
    message: Message,
    session: AsyncSession,
    i18n: I18nContext,
    ticket_id: int,
    target_user_id: int,
) -> None:
    companies, has_more = await support_svc.get_user_companies_page(
        session,
        target_user_id,
        0,
    )
    if not companies:
        await message.answer(i18n.get("support-companies-empty"))
        return

    def _btn(c) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=f"📋 {c.vacancy_title} ({c.status})",
            callback_data=TicketAdminCallback(
                action="company_detail",
                ticket_id=ticket_id,
                user_id=target_user_id,
                page=c.id,
            ).pack(),
        )

    kb = build_paginated_keyboard(
        items=companies,
        item_to_button=_btn,
        page=0,
        has_more=has_more,
        page_callback_factory=lambda p: TicketAdminCallback(
            action="companies",
            ticket_id=ticket_id,
            user_id=target_user_id,
            page=p,
        ).pack(),
        i18n=i18n,
    )
    await message.answer(f"<b>{i18n.get('btn-check-companies')}</b>", reply_markup=kb)


async def _conv_show_tickets(
    message: Message,
    session: AsyncSession,
    i18n: I18nContext,
    ticket_id: int,
    target_user_id: int,
) -> None:
    tickets, has_more = await support_svc.get_user_tickets_page_admin(
        session,
        target_user_id,
        0,
    )
    if not tickets:
        await message.answer(i18n.get("support-tickets-empty"))
        return

    def _btn(t) -> InlineKeyboardButton:
        status_map = {"new": "🆕", "in_progress": "🔄", "closed": "✅"}
        icon = status_map.get(t.status, "📝")
        return InlineKeyboardButton(
            text=f"{icon} {t.title[:40]}",
            callback_data=TicketAdminCallback(
                action="view",
                ticket_id=t.id,
                user_id=target_user_id,
            ).pack(),
        )

    kb = build_paginated_keyboard(
        items=tickets,
        item_to_button=_btn,
        page=0,
        has_more=has_more,
        page_callback_factory=lambda p: TicketAdminCallback(
            action="tickets",
            ticket_id=ticket_id,
            user_id=target_user_id,
            page=p,
        ).pack(),
        i18n=i18n,
    )
    await message.answer(f"<b>{i18n.get('btn-check-tickets')}</b>", reply_markup=kb)


async def _conv_save_and_relay(
    message: Message,
    user: User,
    session: AsyncSession,
    ticket,
    ticket_id: int,
) -> None:
    msg_text = message.text or message.caption
    db_msg = await support_svc.save_message(
        session,
        ticket_id=ticket_id,
        sender_id=user.id,
        text=msg_text,
        is_from_admin=True,
        is_seen=False,
    )

    has_attachment = bool(message.photo or message.document or message.video)
    if has_attachment:
        allowed, file_id, file_type, file_name, mime_type = support_svc.is_allowed_attachment(
            message
        )
        if allowed:
            await support_svc.save_message_attachment(
                session,
                message_id=db_msg.id,
                file_id=file_id,
                file_type=file_type,
                file_name=file_name,
                mime_type=mime_type,
            )

    if ticket.user:
        locale = ticket.user.language_code or "ru"
        try:
            await support_svc.relay_to_user(
                message.bot,
                ticket.user.telegram_id,
                message,
                locale=locale,
            )
            await support_svc.mark_messages_seen(session, ticket_id, for_admin=False)
        except Exception:
            pass


_BUTTON_HANDLERS: dict[str, str] = {
    "btn-quit-conversation": "quit",
    "btn-close-ticket-admin": "close",
    "btn-view-profile": "profile",
    "btn-check-companies": "companies",
    "btn-check-tickets": "tickets",
    "btn-check-notifications": "notifications",
    "btn-ban": "ban",
    "btn-message-history": "history",
}


@router.message(AdminConversation.chatting)
async def admin_conversation_message(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    text = message.text or ""
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    target_user_id = data.get("target_user_id")

    label_to_action = {i18n.get(key): act for key, act in _BUTTON_HANDLERS.items()}
    action = label_to_action.get(text)

    if action == "quit":
        await state.clear()
        await message.answer(i18n.get("support-conversation-left"), reply_markup=REMOVE_KEYBOARD)
        return
    if action == "close":
        await state.set_state(AdminConversation.close_result)
        await state.update_data(from_conversation=True)
        await message.answer(
            i18n.get("support-close-enter-result"),
            reply_markup=close_cancel_keyboard(i18n),
        )
        return
    if action == "profile":
        profile_text = await support_svc.format_user_profile_support(
            session,
            target_user_id,
            locale=user.language_code or "ru",
        )
        await message.answer(profile_text)
        return
    if action == "companies":
        await _conv_show_companies(message, session, i18n, ticket_id, target_user_id)
        return
    if action == "tickets":
        await _conv_show_tickets(message, session, i18n, ticket_id, target_user_id)
        return
    if action == "notifications":
        await message.answer(i18n.get("support-notifications-soon"))
        return
    if action == "ban":
        await state.set_state(AdminConversation.ban_period)
        await state.update_data(from_conversation=True)
        await message.answer(
            i18n.get("support-ban-enter-period"),
            reply_markup=ban_cancel_keyboard(i18n),
        )
        return
    if action == "history":
        count = await support_svc.send_message_history(
            session,
            message.bot,
            ticket_id,
            user.telegram_id,
            locale=user.language_code or "ru",
        )
        await message.answer(i18n.get("support-history-sent", count=str(count)))
        return

    if not ticket_id:
        await state.clear()
        await message.answer(i18n.get("support-conversation-left"), reply_markup=REMOVE_KEYBOARD)
        return

    ticket = await support_svc.get_ticket(session, ticket_id)
    if not ticket or ticket.status == "closed":
        await state.clear()
        await message.answer(
            i18n.get("support-ticket-already-closed"),
            reply_markup=REMOVE_KEYBOARD,
        )
        return

    await _conv_save_and_relay(message, user, session, ticket, ticket_id)
