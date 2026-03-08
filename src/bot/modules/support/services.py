from collections.abc import Sequence
from datetime import UTC, datetime

from aiogram import Bot
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core.i18n import I18nContext, get_text
from src.models.ban import UserBan
from src.models.support import SupportAttachment, SupportMessage, SupportTicket
from src.models.user import User
from src.repositories.ban import UserBanRepository
from src.repositories.support import (
    TICKETS_PER_PAGE,
    SupportAttachmentRepository,
    SupportMessageRepository,
    SupportTicketRepository,
)
from src.repositories.user import UserRepository

ALLOWED_PHOTO_EXTENSIONS = {"webp", "png", "jpg", "jpeg"}
ALLOWED_DOC_EXTENSIONS = {"txt"}
ALLOWED_VIDEO_EXTENSIONS = {"mp4"}
ALLOWED_EXTENSIONS = ALLOWED_PHOTO_EXTENSIONS | ALLOWED_DOC_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS


# ── Ticket CRUD ──────────────────────────────────────────────


async def create_ticket(
    session: AsyncSession,
    *,
    user_id: int,
    title: str,
    description: str,
) -> SupportTicket:
    repo = SupportTicketRepository(session)
    ticket = await repo.create(
        user_id=user_id,
        title=title,
        description=description,
        status="new",
    )
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def get_user_tickets_page(
    session: AsyncSession,
    user_id: int,
    page: int,
) -> tuple[list[SupportTicket], bool]:
    repo = SupportTicketRepository(session)
    tickets = list(
        await repo.get_by_user(
            user_id,
            offset=page * TICKETS_PER_PAGE,
            limit=TICKETS_PER_PAGE + 1,
        )
    )
    has_more = len(tickets) > TICKETS_PER_PAGE
    return tickets[:TICKETS_PER_PAGE], has_more


async def get_ticket(session: AsyncSession, ticket_id: int) -> SupportTicket | None:
    repo = SupportTicketRepository(session)
    return await repo.get_by_id(ticket_id)


async def get_ticket_with_details(
    session: AsyncSession,
    ticket_id: int,
) -> SupportTicket | None:
    repo = SupportTicketRepository(session)
    return await repo.get_with_details(ticket_id)


async def get_all_tickets_filtered(
    session: AsyncSession,
    *,
    status: str = "",
    query: str = "",
    page: int = 0,
) -> tuple[list[SupportTicket], bool]:
    repo = SupportTicketRepository(session)
    tickets = list(
        await repo.get_all_filtered(
            status=status,
            query=query,
            offset=page * TICKETS_PER_PAGE,
            limit=TICKETS_PER_PAGE + 1,
        )
    )
    has_more = len(tickets) > TICKETS_PER_PAGE
    return tickets[:TICKETS_PER_PAGE], has_more


async def get_unseen_ticket_ids(
    session: AsyncSession,
    ticket_ids: list[int],
) -> set[int]:
    repo = SupportTicketRepository(session)
    result = set()
    for tid in ticket_ids:
        if await repo.has_unseen_messages(tid):
            result.add(tid)
    return result


async def take_ticket(
    session: AsyncSession,
    ticket_id: int,
    admin_id: int,
) -> SupportTicket | None:
    repo = SupportTicketRepository(session)
    ticket = await repo.get_by_id(ticket_id)
    if not ticket or ticket.status != "new":
        return None
    await repo.update(ticket, admin_id=admin_id, status="in_progress")
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def close_ticket(
    session: AsyncSession,
    ticket_id: int,
    *,
    close_result: str,
    close_status: str,
) -> SupportTicket | None:
    repo = SupportTicketRepository(session)
    ticket = await repo.get_by_id(ticket_id)
    if not ticket or ticket.status == "closed":
        return None
    await repo.update(
        ticket,
        status="closed",
        close_result=close_result,
        close_status=close_status,
    )
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def close_ticket_by_user(
    session: AsyncSession,
    ticket_id: int,
) -> SupportTicket | None:
    repo = SupportTicketRepository(session)
    ticket = await repo.get_by_id(ticket_id)
    if not ticket or ticket.status == "closed":
        return None
    await repo.update(ticket, status="closed")
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def set_channel_message_id(
    session: AsyncSession,
    ticket_id: int,
    message_id: int,
) -> None:
    repo = SupportTicketRepository(session)
    ticket = await repo.get_by_id(ticket_id)
    if ticket:
        await repo.update(ticket, channel_message_id=message_id)
        await session.commit()


# ── Attachments ──────────────────────────────────────────────


async def save_ticket_attachment(
    session: AsyncSession,
    *,
    ticket_id: int,
    file_id: str,
    file_type: str,
    file_name: str | None = None,
    mime_type: str | None = None,
) -> SupportAttachment:
    repo = SupportAttachmentRepository(session)
    attachment = await repo.create(
        ticket_id=ticket_id,
        file_id=file_id,
        file_type=file_type,
        file_name=file_name,
        mime_type=mime_type,
    )
    await session.commit()
    return attachment


async def get_ticket_attachments(
    session: AsyncSession,
    ticket_id: int,
) -> Sequence[SupportAttachment]:
    repo = SupportAttachmentRepository(session)
    return await repo.get_by_ticket(ticket_id)


def is_allowed_attachment(message: Message) -> tuple[bool, str, str, str | None, str | None]:
    """Check if the message contains an allowed attachment type.

    Returns (allowed, file_id, file_type, file_name, mime_type).
    """
    if message.photo:
        photo = message.photo[-1]
        return True, photo.file_id, "photo", None, None

    if message.document:
        doc = message.document
        fname = doc.file_name or ""
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext in ALLOWED_DOC_EXTENSIONS:
            return True, doc.file_id, "document", fname, doc.mime_type

    if message.video:
        video = message.video
        fname = video.file_name or ""
        ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
        if ext in ALLOWED_VIDEO_EXTENSIONS:
            return True, video.file_id, "video", fname, video.mime_type

    return False, "", "", None, None


# ── Messages ─────────────────────────────────────────────────


async def save_message(
    session: AsyncSession,
    *,
    ticket_id: int,
    sender_id: int,
    text: str | None = None,
    is_from_admin: bool = False,
    is_seen: bool = False,
) -> SupportMessage:
    repo = SupportMessageRepository(session)
    msg = await repo.create(
        ticket_id=ticket_id,
        sender_id=sender_id,
        text=text,
        is_from_admin=is_from_admin,
        is_seen=is_seen,
    )
    await session.commit()
    return msg


async def save_message_attachment(
    session: AsyncSession,
    *,
    message_id: int,
    file_id: str,
    file_type: str,
    file_name: str | None = None,
    mime_type: str | None = None,
) -> SupportAttachment:
    repo = SupportAttachmentRepository(session)
    attachment = await repo.create(
        message_id=message_id,
        file_id=file_id,
        file_type=file_type,
        file_name=file_name,
        mime_type=mime_type,
    )
    await session.commit()
    return attachment


async def get_unseen_messages(
    session: AsyncSession,
    ticket_id: int,
    *,
    for_admin: bool = True,
) -> Sequence[SupportMessage]:
    repo = SupportMessageRepository(session)
    return await repo.get_unseen_by_ticket(ticket_id, for_admin=for_admin)


async def mark_messages_seen(
    session: AsyncSession,
    ticket_id: int,
    *,
    for_admin: bool = True,
) -> int:
    repo = SupportMessageRepository(session)
    count = await repo.mark_seen(ticket_id, for_admin=for_admin)
    await session.commit()
    return count


async def get_all_messages(
    session: AsyncSession,
    ticket_id: int,
) -> Sequence[SupportMessage]:
    repo = SupportMessageRepository(session)
    return await repo.get_all_by_ticket(ticket_id)


# ── Message relay ────────────────────────────────────────────


async def relay_to_admin(
    bot: Bot,
    admin_telegram_id: int,
    message: Message,
    *,
    sender_name: str,
) -> None:
    header = f"💬 <b>{sender_name}:</b>\n"
    if message.text:
        await bot.send_message(admin_telegram_id, f"{header}{message.text}")
    if message.photo:
        await bot.send_photo(
            admin_telegram_id,
            message.photo[-1].file_id,
            caption=f"{header}{message.caption or ''}",
        )
    if message.document:
        await bot.send_document(
            admin_telegram_id,
            message.document.file_id,
            caption=f"{header}{message.caption or ''}",
        )
    if message.video:
        await bot.send_video(
            admin_telegram_id,
            message.video.file_id,
            caption=f"{header}{message.caption or ''}",
        )


async def relay_to_user(
    bot: Bot,
    user_telegram_id: int,
    message: Message,
    locale: str = "ru",
) -> None:
    header = f"💬 <b>{get_text('support-admin-reply', locale)}:</b>\n"
    if message.text:
        await bot.send_message(user_telegram_id, f"{header}{message.text}")
    if message.photo:
        await bot.send_photo(
            user_telegram_id,
            message.photo[-1].file_id,
            caption=f"{header}{message.caption or ''}",
        )
    if message.document:
        await bot.send_document(
            user_telegram_id,
            message.document.file_id,
            caption=f"{header}{message.caption or ''}",
        )
    if message.video:
        await bot.send_video(
            user_telegram_id,
            message.video.file_id,
            caption=f"{header}{message.caption or ''}",
        )


async def deliver_unseen_to_admin(
    session: AsyncSession,
    bot: Bot,
    ticket_id: int,
    admin_telegram_id: int,
    locale: str = "ru",
) -> int:
    messages = await get_unseen_messages(session, ticket_id, for_admin=True)
    if not messages:
        return 0

    for msg in messages:
        sender_name = msg.sender.first_name or get_text("support-user-label", locale)
        text_parts = [f"💬 <b>{sender_name}:</b>"]
        if msg.text:
            text_parts.append(msg.text)
        await bot.send_message(admin_telegram_id, "\n".join(text_parts))

        for att in msg.attachments:
            await _send_attachment(bot, admin_telegram_id, att)

    count = await mark_messages_seen(session, ticket_id, for_admin=True)
    return count


async def _send_attachment(
    bot: Bot,
    chat_id: int,
    attachment: SupportAttachment,
) -> None:
    if attachment.file_type == "photo":
        await bot.send_photo(chat_id, attachment.file_id)
    elif attachment.file_type == "document":
        await bot.send_document(chat_id, attachment.file_id)
    elif attachment.file_type == "video":
        await bot.send_video(chat_id, attachment.file_id)


# ── Send message history ─────────────────────────────────────


async def send_message_history(
    session: AsyncSession,
    bot: Bot,
    ticket_id: int,
    admin_telegram_id: int,
    locale: str = "ru",
) -> int:
    messages = await get_all_messages(session, ticket_id)
    if not messages:
        await bot.send_message(
            admin_telegram_id,
            get_text("support-no-messages", locale),
        )
        return 0

    for msg in messages:
        label = (
            get_text("support-admin-label", locale)
            if msg.is_from_admin
            else get_text("support-user-label", locale)
        )
        time_str = msg.created_at.strftime("%Y-%m-%d %H:%M")
        header = f"[{time_str}] <b>{label}:</b>"
        text_parts = [header]
        if msg.text:
            text_parts.append(msg.text)
        await bot.send_message(admin_telegram_id, "\n".join(text_parts))

        for att in msg.attachments:
            await _send_attachment(bot, admin_telegram_id, att)

    return len(messages)


# ── Channel notification ─────────────────────────────────────


async def post_ticket_to_channel(
    session: AsyncSession,
    bot: Bot,
    ticket: SupportTicket,
    i18n: I18nContext,
) -> int | None:
    chat_id = settings.support_chat_id
    if not chat_id:
        return None

    from src.bot.modules.support.keyboards import ticket_channel_keyboard

    user = ticket.user
    text = (
        f"{i18n.get('support-channel-new-ticket')}\n\n"
        f"<b>{i18n.get('support-ticket-title-label')}:</b> {ticket.title}\n"
        f"<b>{i18n.get('support-ticket-desc-label')}:</b>\n{ticket.description}\n\n"
        f"<b>{i18n.get('support-ticket-author')}:</b> "
        f"{user.first_name} (@{user.username or '—'}) [ID: {user.telegram_id}]\n"
        f"<b>{i18n.get('support-ticket-id-label')}:</b> #{ticket.id}"
    )

    sent = await bot.send_message(
        int(chat_id),
        text,
        reply_markup=ticket_channel_keyboard(ticket, i18n),
    )
    await set_channel_message_id(session, ticket.id, sent.message_id)
    return sent.message_id


# ── User profile for support ─────────────────────────────────


async def format_user_profile_support(
    session: AsyncSession,
    user_id: int,
    locale: str = "ru",
) -> str:
    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)
    if not user:
        return get_text("admin-user-not-found", locale)

    from src.repositories.blacklist import BlacklistRepository

    bl_repo = BlacklistRepository(session)
    bl_count = await bl_repo.count_active(user.id)

    ban_repo = UserBanRepository(session)
    ban_history = await ban_repo.get_ban_history(user.id, limit=5)

    banned_text = get_text("yes", locale) if user.is_banned else get_text("no", locale)
    lines = [
        f"<b>👤 {get_text('support-user-profile', locale)}</b>",
        "",
        f"<b>ID:</b> {user.id}",
        f"<b>Telegram ID:</b> <code>{user.telegram_id}</code>",
        get_text(
            'admin-user-detail-name',
            locale,
            name=f'{user.first_name} {user.last_name or ""}',
        ),
        get_text(
            'admin-user-detail-username',
            locale,
            username=user.username or '—',
        ),
        get_text(
            'admin-user-detail-role',
            locale,
            role=user.role.name,
        ),
        get_text(
            'admin-user-detail-balance',
            locale,
            balance=str(user.balance),
        ),
        get_text(
            'admin-user-detail-banned',
            locale,
            banned=banned_text,
        ),
        get_text(
            'admin-user-detail-language',
            locale,
            language=user.language_code,
        ),
        get_text(
            'admin-user-detail-joined',
            locale,
            date=user.created_at.strftime('%Y-%m-%d %H:%M'),
        ),
        "",
        f"<b>{get_text('support-blacklist-count', locale)}:</b> {bl_count}",
        f"<b>{get_text('support-referral-code', locale)}:</b> <code>{user.referral_code}</code>",
        f"<b>{get_text('support-referred-by', locale)}:</b> "
        f"{'#' + str(user.referred_by_id) if user.referred_by_id else '—'}",
    ]

    if ban_history:
        lines.append("")
        lines.append(f"<b>{get_text('support-ban-history', locale)}:</b>")
        for ban in ban_history:
            status = "🟢" if not ban.is_active else "🔴"
            until = ban.banned_until.strftime("%Y-%m-%d %H:%M") if ban.banned_until else "∞"
            lines.append(f"  {status} {ban.reason[:50]} → {until}")

    return "\n".join(lines)


# ── User companies for support ───────────────────────────────


async def get_user_companies_page(
    session: AsyncSession,
    user_id: int,
    page: int,
) -> tuple[list, bool]:
    from src.repositories.parsing import ParsingCompanyRepository

    repo = ParsingCompanyRepository(session)
    per_page = 10
    companies = list(await repo.get_by_user(user_id, offset=page * per_page, limit=per_page + 1))
    has_more = len(companies) > per_page
    return companies[:per_page], has_more


async def get_user_tickets_page_admin(
    session: AsyncSession,
    user_id: int,
    page: int,
) -> tuple[list[SupportTicket], bool]:
    repo = SupportTicketRepository(session)
    tickets = list(
        await repo.get_by_user(
            user_id,
            offset=page * TICKETS_PER_PAGE,
            limit=TICKETS_PER_PAGE + 1,
        )
    )
    has_more = len(tickets) > TICKETS_PER_PAGE
    return tickets[:TICKETS_PER_PAGE], has_more


# ── Ban management ───────────────────────────────────────────


async def ban_user(
    session: AsyncSession,
    *,
    user_id: int,
    admin_id: int,
    reason: str,
    banned_until: datetime | None = None,
    ticket_id: int | None = None,
) -> UserBan:
    ban_repo = UserBanRepository(session)
    user_repo = UserRepository(session)

    user = await user_repo.get_by_id(user_id)
    if user:
        await user_repo.update(user, is_banned=True)

    ban = await ban_repo.create_ban(
        user_id=user_id,
        admin_id=admin_id,
        reason=reason,
        banned_until=banned_until,
        ticket_id=ticket_id,
    )
    await session.commit()
    return ban


async def check_ban_expiry(session: AsyncSession, user: User) -> bool:
    """Check if active ban has expired. Returns True if user was unbanned."""
    if not user.is_banned:
        return False

    ban_repo = UserBanRepository(session)
    active_ban = await ban_repo.get_active_ban(user.id)

    if not active_ban:
        return False

    now = datetime.now(UTC)
    if active_ban.banned_until and active_ban.banned_until.replace(tzinfo=UTC) < now:
        user_repo = UserRepository(session)
        await user_repo.update(user, is_banned=False)
        await ban_repo.deactivate_bans(user.id)
        await session.commit()
        return True

    return False
