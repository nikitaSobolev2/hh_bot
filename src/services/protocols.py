"""Service protocols (structural interfaces) for dependency inversion.

Using Protocol instead of ABC allows structural subtyping — any class that
implements the required methods satisfies the interface without explicit
inheritance.  This enables easy test mocking and future swapping of
implementations.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Protocol, runtime_checkable

from src.schemas.ai import QAPair
from src.schemas.vacancy import PipelineResult, VacancyData


@runtime_checkable
class AIClientProtocol(Protocol):
    """Abstract interface for all AI (LLM) operations."""

    async def extract_keywords(self, description: str) -> list[str]: ...

    async def analyze_vacancy(
        self,
        vacancy_title: str,
        vacancy_skills: list[str],
        vacancy_description: str,
        user_tech_stack: list[str],
        user_work_experience: str,
    ) -> dict: ...

    async def calculate_compatibility(
        self,
        vacancy_title: str,
        vacancy_skills: list[str],
        vacancy_description: str,
        user_tech_stack: list[str],
        user_work_experience: str,
    ) -> float: ...

    async def generate_key_phrases(self, prompt: str) -> str | None: ...

    async def analyze_interview(
        self,
        vacancy_title: str,
        vacancy_description: str | None,
        company_name: str | None,
        experience_level: str | None,
        questions_answers: list[QAPair],
        user_improvement_notes: str | None,
    ) -> str: ...

    async def generate_improvement_flow(
        self,
        technology_title: str,
        improvement_summary: str,
        vacancy_title: str,
        vacancy_description: str | None,
    ) -> str: ...

    async def generate_text(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        timeout: int = 180,
        max_tokens: int = 4000,
        temperature: float = 0.5,
    ) -> str: ...

    def stream_key_phrases(self, prompt: str) -> AsyncGenerator[str, None]: ...


@runtime_checkable
class ScraperProtocol(Protocol):
    """Abstract interface for HH.ru vacancy scraping."""

    async def scrape_vacancies(
        self,
        search_url: str,
        *,
        target_count: int,
        blacklisted_ids: set[str],
        keyword_filter: str,
    ) -> list[VacancyData]: ...


@runtime_checkable
class NotificationProtocol(Protocol):
    """Abstract interface for sending Telegram messages from background tasks."""

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: object | None = None,
        parse_mode: str = "HTML",
    ) -> None: ...

    async def edit_or_send(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        reply_markup: object | None = None,
        parse_mode: str = "HTML",
    ) -> None: ...


@runtime_checkable
class ProgressProtocol(Protocol):
    """Abstract interface for task progress reporting."""

    async def start_task(self, task_key: str, title: str, bar_labels: list[str]) -> None: ...

    async def update_bar(self, task_key: str, bar_index: int, current: int, total: int) -> None: ...

    async def finish_task(self, task_key: str) -> None: ...


@runtime_checkable
class ExtractorProtocol(Protocol):
    """Abstract interface for the full parsing pipeline (scrape + extract)."""

    async def run_pipeline(
        self,
        *,
        search_url: str,
        keyword_filter: str,
        target_count: int,
        blacklisted_ids: set[str],
        on_page_scraped: object | None,
        on_vacancy_processed: object | None,
        compat_filter: object | None,
    ) -> PipelineResult: ...


@runtime_checkable
class RateLimiterProtocol(Protocol):
    """Abstract interface for rate limiting external API calls."""

    async def acquire(self) -> None: ...

    async def release(self) -> None: ...
