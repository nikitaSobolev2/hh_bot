from collections.abc import Sequence

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.support import SupportAttachment, SupportMessage, SupportTicket
from src.repositories.base import BaseRepository

TICKETS_PER_PAGE = 10
MESSAGES_PER_PAGE = 50


class SupportTicketRepository(BaseRepository[SupportTicket]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SupportTicket)

    async def get_by_user(
        self,
        user_id: int,
        *,
        offset: int = 0,
        limit: int = TICKETS_PER_PAGE,
    ) -> Sequence[SupportTicket]:
        stmt = (
            select(SupportTicket)
            .where(SupportTicket.user_id == user_id)
            .order_by(SupportTicket.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_admin(
        self,
        admin_id: int,
        *,
        offset: int = 0,
        limit: int = TICKETS_PER_PAGE,
    ) -> Sequence[SupportTicket]:
        stmt = (
            select(SupportTicket)
            .where(SupportTicket.admin_id == admin_id)
            .order_by(SupportTicket.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_all_filtered(
        self,
        *,
        status: str = "",
        query: str = "",
        offset: int = 0,
        limit: int = TICKETS_PER_PAGE,
    ) -> Sequence[SupportTicket]:
        stmt = select(SupportTicket)

        conditions = []
        if status:
            conditions.append(SupportTicket.status == status)
        if query:
            pattern = f"%{query}%"
            conditions.append(
                or_(
                    SupportTicket.title.ilike(pattern),
                    SupportTicket.description.ilike(pattern),
                )
            )
        if conditions:
            stmt = stmt.where(and_(*conditions))

        stmt = stmt.order_by(SupportTicket.updated_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_with_details(self, ticket_id: int) -> SupportTicket | None:
        stmt = (
            select(SupportTicket)
            .options(
                selectinload(SupportTicket.messages).selectinload(SupportMessage.attachments),
                selectinload(SupportTicket.attachments),
            )
            .where(SupportTicket.id == ticket_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_by_user(self, user_id: int) -> int:
        stmt = (
            select(func.count()).select_from(SupportTicket).where(SupportTicket.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def has_unseen_messages(self, ticket_id: int) -> bool:
        stmt = (
            select(func.count())
            .select_from(SupportMessage)
            .where(
                SupportMessage.ticket_id == ticket_id,
                SupportMessage.is_seen.is_(False),
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() > 0


class SupportMessageRepository(BaseRepository[SupportMessage]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SupportMessage)

    async def get_by_ticket(
        self,
        ticket_id: int,
        *,
        offset: int = 0,
        limit: int = MESSAGES_PER_PAGE,
    ) -> Sequence[SupportMessage]:
        stmt = (
            select(SupportMessage)
            .options(selectinload(SupportMessage.attachments))
            .where(SupportMessage.ticket_id == ticket_id)
            .order_by(SupportMessage.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_all_by_ticket(self, ticket_id: int) -> Sequence[SupportMessage]:
        stmt = (
            select(SupportMessage)
            .options(selectinload(SupportMessage.attachments))
            .where(SupportMessage.ticket_id == ticket_id)
            .order_by(SupportMessage.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_unseen_by_ticket(
        self,
        ticket_id: int,
        *,
        for_admin: bool = True,
    ) -> Sequence[SupportMessage]:
        stmt = (
            select(SupportMessage)
            .options(selectinload(SupportMessage.attachments))
            .where(
                SupportMessage.ticket_id == ticket_id,
                SupportMessage.is_seen.is_(False),
                SupportMessage.is_from_admin == (not for_admin),
            )
            .order_by(SupportMessage.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def mark_seen(self, ticket_id: int, *, for_admin: bool = True) -> int:
        stmt = (
            update(SupportMessage)
            .where(
                SupportMessage.ticket_id == ticket_id,
                SupportMessage.is_seen.is_(False),
                SupportMessage.is_from_admin == (not for_admin),
            )
            .values(is_seen=True)
        )
        result = await self._session.execute(stmt)
        return result.rowcount


class SupportAttachmentRepository(BaseRepository[SupportAttachment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SupportAttachment)

    async def get_by_ticket(self, ticket_id: int) -> Sequence[SupportAttachment]:
        stmt = (
            select(SupportAttachment)
            .where(
                SupportAttachment.ticket_id == ticket_id,
                SupportAttachment.message_id.is_(None),
            )
            .order_by(SupportAttachment.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_message(self, message_id: int) -> Sequence[SupportAttachment]:
        stmt = (
            select(SupportAttachment)
            .where(SupportAttachment.message_id == message_id)
            .order_by(SupportAttachment.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()
