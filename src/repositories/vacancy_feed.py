from sqlalchemy.ext.asyncio import AsyncSession

from src.models.vacancy_feed import VacancyFeedSession
from src.repositories.base import BaseRepository


class VacancyFeedSessionRepository(BaseRepository[VacancyFeedSession]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, VacancyFeedSession)
