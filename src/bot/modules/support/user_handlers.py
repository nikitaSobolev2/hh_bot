import contextlib

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.bot.keyboards.common import back_to_menu_keyboard
from src.bot.modules.support import services as support_svc
from src.bot.modules.support.callbacks import SupportCallback
from src.bot.modules.support.keyboards import (
    REMOVE_KEYBOARD,
    skip_attachments_keyboard,
    ticket_detail_keyboard,
    user_conversation_keyboard,
    user_ticket_list_keyboard,
)
from src.bot.modules.support.states import TicketForm, UserConversation
from src.core.i18n import I18nContext
from src.models.user import User

router = Router(name="support_user")


# ── Ticket list ──────────────────────────────────────────────


async def show_ticket_list(
    callback: CallbackQuery,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
    page: int = 0,
) -> None:
    tickets, has_more = await support_svc.get_user_tickets_page(session, user.id, page)

    if not tickets and page == 0:
        await callback.message.edit_text(
            f"{i18n.get('support-title')}\n\n{i18n.get('support-empty')}",
            reply_markup=user_ticket_list_keyboard([], 0, False, i18n),
        )
        return

    unseen_ids = await support_svc.get_unseen_ticket_ids(
        session,
        [t.id for t in tickets],
    )

    await callback.message.edit_text(
        f"{i18n.get('support-title')}\n\n{i18n.get('support-subtitle')}",
        reply_markup=user_ticket_list_keyboard(
            tickets,
            page,
            has_more,
            i18n,
            unseen_ticket_ids=unseen_ids,
        ),
    )


@router.callback_query(SupportCallback.filter(F.action == "list"))
async def ticket_list_page(
    callback: CallbackQuery,
    callback_data: SupportCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    await show_ticket_list(callback, user, session, i18n, callback_data.page)
    await callback.answer()


# ── Ticket detail ────────────────────────────────────────────


@router.callback_query(SupportCallback.filter(F.action == "detail"))
async def ticket_detail(
    callback: CallbackQuery,
    callback_data: SupportCallback,
    user: User,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    ticket = await support_svc.get_ticket(session, callback_data.ticket_id)
    if not ticket or ticket.user_id != user.id:
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
        reply_markup=ticket_detail_keyboard(ticket, i18n),
    )
    await callback.answer()


# ── New ticket flow ──────────────────────────────────────────


@router.callback_query(SupportCallback.filter(F.action == "new"))
async def new_ticket_start(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    await state.set_state(TicketForm.title)
    await callback.message.edit_text(
        i18n.get("support-enter-title"),
        reply_markup=back_to_menu_keyboard(i18n),
    )
    await callback.answer()


@router.message(TicketForm.title)
async def ticket_title_entered(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    title = (message.text or "").strip()
    if not title:
        await message.answer(i18n.get("support-title-empty"))
        return
    await state.update_data(title=title[:255])
    await state.set_state(TicketForm.description)
    await message.answer(i18n.get("support-enter-description", title=title[:255]))


@router.message(TicketForm.description)
async def ticket_description_entered(
    message: Message,
    state: FSMContext,
    i18n: I18nContext,
) -> None:
    desc = (message.text or "").strip()
    if not desc:
        await message.answer(i18n.get("support-desc-empty"))
        return
    await state.update_data(description=desc)
    await state.set_state(TicketForm.attachments)
    await state.update_data(attachment_count=0)
    await message.answer(
        i18n.get("support-enter-attachments"),
        reply_markup=skip_attachments_keyboard(i18n),
    )


@router.message(TicketForm.attachments, F.photo | F.document | F.video)
async def ticket_attachment_received(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    allowed, file_id, file_type, file_name, mime_type = support_svc.is_allowed_attachment(message)
    if not allowed:
        await message.answer(
            i18n.get("support-attachment-invalid"),
            reply_markup=skip_attachments_keyboard(i18n),
        )
        return

    data = await state.get_data()
    ticket_id = data.get("ticket_id")

    if not ticket_id:
        title = data.get("title")
        description = data.get("description")
        if not title or not description:
            await state.clear()
            await message.answer(i18n.get("support-session-expired"))
            return
        ticket = await support_svc.create_ticket(
            session,
            user_id=user.id,
            title=title,
            description=description,
        )
        ticket_id = ticket.id
        await state.update_data(ticket_id=ticket_id)

    await support_svc.save_ticket_attachment(
        session,
        ticket_id=ticket_id,
        file_id=file_id,
        file_type=file_type,
        file_name=file_name,
        mime_type=mime_type,
    )
    count = data.get("attachment_count", 0) + 1
    await state.update_data(attachment_count=count)
    await message.answer(
        i18n.get("support-attachment-saved", count=str(count)),
        reply_markup=skip_attachments_keyboard(i18n),
    )


@router.message(TicketForm.attachments)
async def ticket_attachment_text(
    message: Message,
    i18n: I18nContext,
) -> None:
    await message.answer(
        i18n.get("support-attachment-invalid"),
        reply_markup=skip_attachments_keyboard(i18n),
    )


@router.callback_query(
    TicketForm.attachments,
    SupportCallback.filter(F.action.in_({"skip_attach", "done_attach"})),
)
async def ticket_finalize(
    callback: CallbackQuery,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    ticket_id = data.get("ticket_id")

    if not ticket_id:
        title = data.get("title")
        description = data.get("description")
        if not title or not description:
            await state.clear()
            await callback.message.edit_text(i18n.get("support-session-expired"))
            await callback.answer()
            return
        ticket = await support_svc.create_ticket(
            session,
            user_id=user.id,
            title=title,
            description=description,
        )
        ticket_id = ticket.id
    else:
        ticket = await support_svc.get_ticket(session, ticket_id)

    await state.clear()
    await state.set_state(UserConversation.chatting)
    await state.update_data(ticket_id=ticket_id)

    await support_svc.post_ticket_to_channel(session, callback.bot, ticket, i18n)

    await callback.message.edit_text(
        i18n.get("support-ticket-created", id=str(ticket_id)),
    )
    await callback.message.answer(
        i18n.get("support-conversation-entered", id=str(ticket_id)),
        reply_markup=user_conversation_keyboard(i18n),
    )
    await callback.answer()


# ── Enter conversation from ticket detail ────────────────────


@router.callback_query(SupportCallback.filter(F.action == "enter"))
async def enter_conversation(
    callback: CallbackQuery,
    callback_data: SupportCallback,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    ticket = await support_svc.get_ticket(session, callback_data.ticket_id)
    if not ticket or ticket.user_id != user.id or ticket.status == "closed":
        await callback.answer(i18n.get("support-ticket-already-closed"), show_alert=True)
        return

    await state.set_state(UserConversation.chatting)
    await state.update_data(ticket_id=ticket.id)

    await callback.message.edit_text(
        i18n.get("support-conversation-entered", id=str(ticket.id)),
    )
    await callback.message.answer(
        i18n.get("support-conversation-entered", id=str(ticket.id)),
        reply_markup=user_conversation_keyboard(i18n),
    )
    await callback.answer()


# ── Conversation mode ────────────────────────────────────────


async def _handle_quit(message: Message, state: FSMContext, i18n: I18nContext) -> None:
    await state.clear()
    await message.answer(
        i18n.get("support-conversation-left"),
        reply_markup=REMOVE_KEYBOARD,
    )


async def _handle_close(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    await state.clear()

    if ticket_id:
        ticket = await support_svc.close_ticket_by_user(session, ticket_id)
        if ticket and ticket.admin_id and ticket.admin:
            with contextlib.suppress(Exception):
                await message.bot.send_message(
                    ticket.admin.telegram_id,
                    i18n.get(
                        "support-ticket-closed-notify-admin",
                        id=str(ticket_id),
                    ),
                )

    await message.answer(
        i18n.get("support-ticket-closed-user", id=str(ticket_id or 0)),
        reply_markup=REMOVE_KEYBOARD,
    )


async def _save_and_relay(
    message: Message,
    user: User,
    session: AsyncSession,
    ticket: object,
    ticket_id: int,
    i18n: I18nContext,
) -> None:
    msg_text = message.text or message.caption

    db_msg = await support_svc.save_message(
        session,
        ticket_id=ticket_id,
        sender_id=user.id,
        text=msg_text,
        is_from_admin=False,
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

    if ticket.admin_id and ticket.admin:
        try:
            await support_svc.relay_to_admin(
                message.bot,
                ticket.admin.telegram_id,
                message,
                sender_name=user.first_name or i18n.get("support-user-label"),
            )
            await support_svc.mark_messages_seen(session, ticket_id, for_admin=True)
        except Exception:
            pass


@router.message(UserConversation.chatting)
async def conversation_message(
    message: Message,
    user: User,
    state: FSMContext,
    session: AsyncSession,
    i18n: I18nContext,
) -> None:
    text = message.text or ""

    if text == i18n.get("btn-quit-conversation"):
        await _handle_quit(message, state, i18n)
        return

    if text == i18n.get("btn-close-ticket"):
        await _handle_close(message, state, session, i18n)
        return

    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    if not ticket_id:
        await _handle_quit(message, state, i18n)
        return

    ticket = await support_svc.get_ticket(session, ticket_id)
    if not ticket or ticket.status == "closed":
        await state.clear()
        await message.answer(
            i18n.get("support-ticket-already-closed"),
            reply_markup=REMOVE_KEYBOARD,
        )
        return

    await _save_and_relay(message, user, session, ticket, ticket_id, i18n)
