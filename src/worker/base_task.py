"""Base Celery task with built-in stability and observability patterns.

All Celery tasks in this project should inherit from ``HHBotTask`` (or use the
``@celery_app.task(base=HHBotTask, ...)`` decorator parameter) to get:

- Structured logging with ``task_id`` and ``task_name`` context.
- Automatic ``task_*_enabled`` flag checking via ``check_enabled(key)``.
- Automatic circuit breaker config loading from ``app_settings`` via
  ``load_circuit_breaker(name, threshold_key, timeout_key)``.
- Shared notification via ``notify_user(chat_id, message_id, text, ...)``.
- Shared bot creation via ``create_bot()``.
- Idempotency checking via ``is_already_completed(key, session_factory)``.
- Idempotency key marking via ``mark_completed(key, session_factory, ...)``.
- Per-user task lock via ``acquire_user_task_lock`` / ``release_user_task_lock``.
- Universal soft-timeout handling via ``handle_soft_timeout``.
"""

from __future__ import annotations

import contextlib

import structlog
from celery import Task
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class HHBotTask(Task):
    """Base task class for all HH Bot Celery tasks.

    Provides shared helpers that encapsulate common patterns, keeping individual
    task implementations focused on their business logic.
    """

    abstract = True

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def get_logger(self) -> structlog.BoundLogger:
        """Return a structlog logger bound with task_id and task_name."""
        return structlog.get_logger().bind(
            task_id=self.request.id or "?",
            task_name=self.name,
        )

    # ------------------------------------------------------------------
    # Feature flags
    # ------------------------------------------------------------------

    async def check_enabled(
        self,
        setting_key: str,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> bool:
        """Return True if the feature flag is enabled in app_settings.

        Returns True when the key is absent (default: enabled).
        """
        from src.repositories.app_settings import AppSettingRepository

        async with session_factory() as session:
            return await AppSettingRepository(session).get_value(setting_key, default=True)

    # ------------------------------------------------------------------
    # Circuit breaker
    # ------------------------------------------------------------------

    async def load_circuit_breaker(
        self,
        name: str,
        threshold_key: str,
        timeout_key: str,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> CircuitBreaker:  # noqa: F821
        """Create and configure a CircuitBreaker from app_settings.

        Falls back to module defaults when the keys are absent.
        """
        from src.core.constants import CB_DEFAULT_FAILURE_THRESHOLD, CB_DEFAULT_RECOVERY_TIMEOUT
        from src.repositories.app_settings import AppSettingRepository
        from src.worker.circuit_breaker import CircuitBreaker

        async with session_factory() as session:
            repo = AppSettingRepository(session)
            threshold = await repo.get_value(threshold_key, default=CB_DEFAULT_FAILURE_THRESHOLD)
            timeout = await repo.get_value(timeout_key, default=CB_DEFAULT_RECOVERY_TIMEOUT)

        cb = CircuitBreaker(name)
        cb.update_config(failure_threshold=int(threshold), recovery_timeout=int(timeout))
        return cb

    # ------------------------------------------------------------------
    # Bot factory
    # ------------------------------------------------------------------

    def create_bot(self) -> Bot:  # noqa: F821
        """Create an HTML-mode Bot instance."""
        from src.services.telegram.bot_factory import create_task_bot

        return create_task_bot()

    # ------------------------------------------------------------------
    # User notification
    # ------------------------------------------------------------------

    async def notify_user(
        self,
        bot: Bot,  # noqa: F821
        chat_id: int,
        message_id: int,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,  # noqa: F821
        parse_mode: str | None = "HTML",
    ) -> None:
        """Edit the processing message or fall back to a new message."""
        from src.services.telegram.messenger import TelegramMessenger

        messenger = TelegramMessenger(bot)
        await messenger.edit_or_send(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )

    # ------------------------------------------------------------------
    # Soft time-limit handler
    # ------------------------------------------------------------------

    async def handle_soft_timeout(
        self,
        bot: Bot,  # noqa: F821
        chat_id: int,
        message_id: int,
        locale: str,
        *,
        idempotency_key: str | None = None,
        task_type: str | None = None,
        user_id: int | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        """Notify user of soft timeout and optionally mark the task failed."""
        from src.core.i18n import get_text

        logger = self.get_logger()
        logger.warning("Task soft time limit exceeded", task_name=self.name)

        with contextlib.suppress(Exception):
            await self.notify_user(
                bot,
                chat_id,
                message_id,
                get_text("task-soft-timeout", locale),
            )

        if idempotency_key and task_type and user_id and session_factory:
            with contextlib.suppress(Exception):
                await self.mark_failed(
                    idempotency_key,
                    task_type,
                    user_id,
                    session_factory,
                    error="soft_time_limit_exceeded",
                )

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    async def is_already_completed(
        self,
        idempotency_key: str,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> bool:
        """Return True if a task with this key has already completed."""
        from src.repositories.task import CeleryTaskRepository

        async with session_factory() as session:
            existing = await CeleryTaskRepository(session).get_by_idempotency_key(idempotency_key)
        return existing is not None and existing.status == "completed"

    async def mark_completed(
        self,
        idempotency_key: str,
        task_type: str,
        user_id: int,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        result_data: dict | None = None,
    ) -> None:
        """Persist the idempotency key with status='completed'."""
        from src.models.task import BaseCeleryTask, CoverLetterTask, InterviewQATask

        task_cls = (
            CoverLetterTask
            if task_type == "cover_letter"
            else InterviewQATask
            if task_type == "interview_qa"
            else BaseCeleryTask
        )
        async with session_factory() as session:
            session.add(
                task_cls(
                    celery_task_id=self.request.id,
                    task_type=task_type,
                    user_id=user_id,
                    status="completed",
                    idempotency_key=idempotency_key,
                    result_data=result_data or {},
                )
            )
            await session.commit()

    async def mark_failed(
        self,
        idempotency_key: str,
        task_type: str,
        user_id: int,
        session_factory: async_sessionmaker[AsyncSession],
        error: str,
    ) -> None:
        """Persist the idempotency key with status='failed'."""
        from src.models.task import BaseCeleryTask, CoverLetterTask, InterviewQATask

        task_cls = (
            CoverLetterTask
            if task_type == "cover_letter"
            else InterviewQATask
            if task_type == "interview_qa"
            else BaseCeleryTask
        )
        async with session_factory() as session:
            session.add(
                task_cls(
                    celery_task_id=self.request.id,
                    task_type=task_type,
                    user_id=user_id,
                    status="failed",
                    idempotency_key=idempotency_key,
                    error_message=error,
                )
            )
            await session.commit()

    # ------------------------------------------------------------------
    # Per-user task lock (prevents duplicate concurrent submissions)
    # ------------------------------------------------------------------

    async def acquire_user_task_lock(
        self,
        user_id: int,
        task_type: str,
        ttl: int = 600,
    ) -> bool:
        """Attempt to acquire a per-user task lock. Returns True if acquired.

        Uses Redis SET NX EX to prevent the same user from running two
        instances of the same task_type concurrently.
        """
        from src.core.redis import create_async_redis

        redis = create_async_redis()
        key = f"lock:user_task:{task_type}:{user_id}"
        try:
            acquired = await redis.set(key, self.request.id or "1", nx=True, ex=ttl)
            return bool(acquired)
        finally:
            await redis.aclose()

    async def release_user_task_lock(self, user_id: int, task_type: str) -> None:
        """Release the per-user task lock."""
        from src.core.redis import create_async_redis

        redis = create_async_redis()
        key = f"lock:user_task:{task_type}:{user_id}"
        try:
            await redis.delete(key)
        finally:
            await redis.aclose()
