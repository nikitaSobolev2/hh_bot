from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models.referral import ReferralEvent
from src.models.user import User
from src.repositories.user import UserRepository

logger = get_logger(__name__)


async def process_referral(session: AsyncSession, user: User, referral_code: str) -> None:
    if user.referred_by_id is not None:
        return

    repo = UserRepository(session)
    referrer = await repo.get_by_referral_code(referral_code)
    if referrer is None or referrer.id == user.id:
        return

    db_user = await repo.get_by_id(user.id)
    if db_user and db_user.referred_by_id is None:
        db_user.referred_by_id = referrer.id
        event = ReferralEvent(
            referrer_id=referrer.id,
            referred_id=user.id,
            event_type="signup",
        )
        session.add(event)
        await session.commit()
        logger.info("Referral recorded", referrer_id=referrer.id, referred_id=user.id)
