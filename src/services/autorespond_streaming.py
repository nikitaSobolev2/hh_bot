"""Stream vacancies into the autorespond pipeline as soon as they are compat-ready.

Used by the manual autoparse+autorespond pipeline:

1. Negotiations sync (orchestrator)
2. Bootstrap: enqueue DB rows that already have compatibility scores
3. Autoparse: detail parse + AI compat per vacancy; each ready row is enqueued immediately
4. Apply pump + cover pregen consume the ready ZSET concurrently with parsing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.bot.modules.autoparse import autorespond_logic
from src.config import settings
from src.core.i18n import get_text
from src.core.logging import get_logger
from src.core.system_load import get_system_load_guard
from src.models.autoparse import AutoparsedVacancy
from src.repositories.autoparse import AutoparsedVacancyRepository
from src.repositories.hh_application_attempt import HhApplicationAttemptRepository
from src.services.autoparse.compatibility import compatibility_score_needs_regeneration
from src.services.autorespond_pipeline_state import (
    clear_pump_lock,
    mark_pregen_pending,
    mark_streaming_parse_complete,
    save_pipeline_envelope,
    seed_ready_to_apply,
)
from src.services.autorespond_progress import (
    clear_autorespond_done_counter,
    clear_autorespond_employer_test_counter,
    clear_autorespond_failed_counter,
    get_autorespond_done_count_sync,
    hh_ui_batch_resume_payload,
    maybe_finish_streaming_autorespond_progress,
)
from src.services.hh_ui.runner import normalize_hh_vacancy_url

logger = get_logger(__name__)


@dataclass
class StreamingAutorespondContext:
    session_factory: async_sessionmaker[AsyncSession]
    company_id: int
    user_id: int
    chat_id: int
    task_key: str
    locale: str
    celery_task_id: str
    hh_linked_account_id: int
    progress: Any
    progress_bot: Any
    bar_index: int = 2
    trigger: str = "manual_pipeline"


@dataclass
class StreamingAutorespondFeed:
    """Producer side of the pipelined manual autorespond run."""

    ctx: StreamingAutorespondContext
    _company: Any = field(default=None, repr=False)
    _resume_items: list[dict] = field(default_factory=list, repr=False)
    _cover_letter_style: str = field(default="professional", repr=False)
    _cover_task_enabled: bool = field(default=True, repr=False)
    _enqueued_ids: set[int] = field(default_factory=set, repr=False)
    _pre_skipped_ids: list[int] = field(default_factory=list, repr=False)
    _resume_envelope: dict[str, Any] | None = field(default=None, repr=False)
    _pump_started: bool = field(default=False, repr=False)
    _work_units: int = field(default=0, repr=False)

    async def _load_company_context(self) -> bool:
        if self._company is not None:
            return True
        from src.bot.modules.autoparse import services as ap_service
        from src.core.constants import AppSettingKey
        from src.repositories.app_settings import AppSettingRepository
        from src.repositories.autoparse import AutoparseCompanyRepository
        from src.repositories.hh_linked_account import HhLinkedAccountRepository
        from src.services.ai.resume_selection import normalize_hh_resume_cache_items

        async with self.ctx.session_factory() as session:
            settings_repo = AppSettingRepository(session)
            if not await settings_repo.get_value("task_autorespond_enabled", default=False):
                return False
            company_repo = AutoparseCompanyRepository(session)
            company = await company_repo.get_by_id(self.ctx.company_id)
            if (
                not company
                or company.is_deleted
                or not company.autorespond_enabled
                or not company.autorespond_hh_linked_account_id
            ):
                return False
            hh_repo = HhLinkedAccountRepository(session)
            hh_linked = await hh_repo.get_by_id(company.autorespond_hh_linked_account_id)
            if not hh_linked:
                return False
            resume_items = normalize_hh_resume_cache_items(hh_linked.resume_list_cache)
            if not resume_items:
                return False
            ap_settings = await ap_service.get_user_autoparse_settings(session, self.ctx.user_id)
            cover_task_enabled = bool(
                await settings_repo.get_value(AppSettingKey.TASK_COVER_LETTER_ENABLED, default=True)
            )
        self._company = company
        self._resume_items = resume_items
        self._cover_letter_style = ap_settings.get("cover_letter_style", "professional")
        self._cover_task_enabled = cover_task_enabled and settings.hh_ui_apply_enabled
        return True

    def _keyword_filter(self) -> str:
        company = self._company
        if company.keyword_check_enabled is False:
            return ""
        return (company.keyword_filter or "").strip()

    async def _already_handled(self, hh_vacancy_ids: list[str]) -> set[str]:
        if not hh_vacancy_ids:
            return set()
        async with self.ctx.session_factory() as session:
            repo = HhApplicationAttemptRepository(session)
            return await repo.hh_vacancy_ids_with_success_or_employer_questions(
                self.ctx.user_id,
                self.ctx.hh_linked_account_id,
                hh_vacancy_ids,
            )

    def _passes_ready_filters(self, vacancy: AutoparsedVacancy) -> bool:
        if vacancy.needs_employer_questions:
            return False
        if compatibility_score_needs_regeneration(vacancy.compatibility_score):
            return False
        kw = self._keyword_filter()
        return autorespond_logic.vacancy_passes_compatibility(
            vacancy,
            self._company.autorespond_min_compat,
            allow_missing_score=False,
        ) and autorespond_logic.vacancy_passes_keyword_mode(
            vacancy,
            kw,
            self._company.autorespond_keyword_mode,
        )

    async def _ensure_resume_envelope(self) -> dict[str, Any]:
        if self._resume_envelope is not None:
            ar = self._resume_envelope.get("autorespond_progress")
            if isinstance(ar, dict):
                ar["total"] = max(0, self._work_units)
                ar["streaming_autorespond"] = True
            return self._resume_envelope
        ar_prog = {
            "task_key": self.ctx.task_key,
            "total": max(0, self._work_units),
            "locale": self.ctx.locale,
            "title": self._company.vacancy_title,
            "celery_task_id": self.ctx.celery_task_id,
            "bar_index": self.ctx.bar_index,
            "finish_progress_task": False,
            "streaming_autorespond": True,
        }
        self._resume_envelope = hh_ui_batch_resume_payload(
            user_id=self.ctx.user_id,
            chat_id=self.ctx.chat_id,
            message_id=0,
            locale=self.ctx.locale,
            hh_linked_account_id=self.ctx.hh_linked_account_id,
            feed_session_id=0,
            cover_letter_style=self._cover_letter_style,
            cover_task_enabled=self._cover_task_enabled,
            silent_feed=True,
            autorespond_progress=ar_prog,
        )
        save_pipeline_envelope(
            self.ctx.chat_id,
            self.ctx.task_key,
            {
                "resume_envelope": self._resume_envelope,
                "total_work_units": self._work_units,
                "company_id": self.ctx.company_id,
                "user_id": self.ctx.user_id,
            },
        )
        return self._resume_envelope

    async def _kick_pump_if_needed(self) -> None:
        if self._pump_started or not settings.hh_ui_apply_enabled:
            return
        from src.worker.tasks.hh_ui_apply import apply_pump_task

        resume_envelope = await self._ensure_resume_envelope()
        clear_pump_lock(self.ctx.chat_id, self.ctx.task_key)
        apply_pump_task.delay(
            task_key=self.ctx.task_key,
            chat_id=self.ctx.chat_id,
            resume_envelope=resume_envelope,
        )
        self._pump_started = True
        logger.info(
            "streaming_autorespond_pump_started",
            company_id=self.ctx.company_id,
            task_key=self.ctx.task_key,
            chat_id=self.ctx.chat_id,
        )

    async def _start_applications_progress_if_needed(self) -> None:
        if self._work_units <= 0 and not self._pre_skipped_ids:
            return
        progress = self.ctx.progress
        task_key = self.ctx.task_key
        if self._work_units > 0:
            await progress.update_bar(task_key, self.ctx.bar_index, 0, self._work_units)
            await progress.set_nested_step_state(task_key, "applications", "running")
            await progress.update_footer(
                task_key,
                [get_text("autorespond-progress-failed", self.ctx.locale, count=0)],
            )
            await clear_autorespond_done_counter(self.ctx.chat_id, task_key)
            await clear_autorespond_failed_counter(self.ctx.chat_id, task_key)
            await clear_autorespond_employer_test_counter(self.ctx.chat_id, task_key)

    async def _enqueue_vacancy(
        self,
        vacancy: AutoparsedVacancy,
        *,
        already_handled: set[str],
    ) -> bool:
        vid = int(vacancy.id)
        if vid in self._enqueued_ids:
            return False
        hh_id = str(vacancy.hh_vacancy_id or "")
        if hh_id in already_handled or not self._passes_ready_filters(vacancy):
            if hh_id in already_handled or vacancy.needs_employer_questions:
                self._pre_skipped_ids.append(vid)
            return False

        from src.services.ai.client import AIClient, close_ai_client
        from src.worker.tasks.autorespond import _resolve_resume_for_autorespond_bounded

        cover_ai_client = AIClient() if len(self._resume_items) > 1 else None
        try:
            await get_system_load_guard().wait_if_overloaded("streaming_autorespond_enqueue")
            resume_id = await _resolve_resume_for_autorespond_bounded(
                cover_ai_client,
                vacancy,
                self._resume_items,
                stored_autorespond_resume_id=self._company.autorespond_resume_id,
            )
        finally:
            if cover_ai_client is not None:
                await close_ai_client(cover_ai_client)
        if not resume_id:
            return False

        spec = {
            "autoparsed_vacancy_id": vid,
            "hh_vacancy_id": hh_id,
            "resume_id": str(resume_id),
            "vacancy_url": normalize_hh_vacancy_url(vacancy.url, hh_id),
            "company_id": int(self.ctx.company_id),
        }
        seed_ready_to_apply(self.ctx.chat_id, self.ctx.task_key, [spec])
        if self._cover_task_enabled:
            mark_pregen_pending(self.ctx.chat_id, self.ctx.task_key, [vid])
            from src.worker.tasks.cover_letter import pregenerate_for_apply_task

            pregenerate_for_apply_task.delay(
                task_key=self.ctx.task_key,
                chat_id=self.ctx.chat_id,
                user_id=self.ctx.user_id,
                autoparsed_vacancy_id=vid,
                resume_id=str(resume_id),
                cover_letter_style=self._cover_letter_style,
            )

        self._enqueued_ids.add(vid)
        self._work_units += 1
        await self._ensure_resume_envelope()
        save_pipeline_envelope(
            self.ctx.chat_id,
            self.ctx.task_key,
            {
                "resume_envelope": self._resume_envelope,
                "total_work_units": self._work_units,
                "company_id": self.ctx.company_id,
                "user_id": self.ctx.user_id,
            },
        )
        if self.ctx.progress and self._work_units > 0:
            current_done = get_autorespond_done_count_sync(
                self.ctx.chat_id, self.ctx.task_key
            )
            await self.ctx.progress.update_bar(
                self.ctx.task_key,
                self.ctx.bar_index,
                current_done,
                self._work_units,
            )
        await self._kick_pump_if_needed()
        logger.info(
            "streaming_autorespond_enqueued",
            company_id=self.ctx.company_id,
            autoparsed_vacancy_id=vid,
            hh_vacancy_id=hh_id,
            work_units=self._work_units,
        )
        return True

    async def bootstrap_pending_from_db(self) -> int:
        """Enqueue existing company vacancies that already have AI compatibility scores."""
        if not await self._load_company_context():
            return 0
        from src.worker.tasks.autorespond import _pending_autorespond_autoparsed_vacancy_ids

        pending_ids = await _pending_autorespond_autoparsed_vacancy_ids(
            self.ctx.session_factory,
            company_id=self.ctx.company_id,
            user_id=self.ctx.user_id,
            hh_linked_account_id=self.ctx.hh_linked_account_id,
        )
        if not pending_ids:
            return 0

        async with self.ctx.session_factory() as session:
            repo = AutoparsedVacancyRepository(session)
            vacancies = await repo.get_by_ids_for_company(self.ctx.company_id, pending_ids)

        hh_ids = [str(v.hh_vacancy_id) for v in vacancies if v.hh_vacancy_id]
        handled = await self._already_handled(hh_ids)
        enqueued = 0
        for vacancy in vacancies:
            if await self._enqueue_vacancy(vacancy, already_handled=handled):
                enqueued += 1
        await self._start_applications_progress_if_needed()
        logger.info(
            "streaming_autorespond_bootstrap",
            company_id=self.ctx.company_id,
            pending=len(pending_ids),
            enqueued=enqueued,
            pre_skipped=len(self._pre_skipped_ids),
        )
        return enqueued

    async def on_autoparsed_rows(self, rows: list[AutoparsedVacancy]) -> int:
        """Hook from autoparse after rows are committed with compatibility scores."""
        if not rows or not await self._load_company_context():
            return 0
        hh_ids = [str(v.hh_vacancy_id) for v in rows if v.hh_vacancy_id]
        handled = await self._already_handled(hh_ids)
        enqueued = 0
        for vacancy in rows:
            if await self._enqueue_vacancy(vacancy, already_handled=handled):
                enqueued += 1
        if enqueued:
            await self._start_applications_progress_if_needed()
        return enqueued

    async def finalize(self) -> dict[str, Any]:
        """Tick pre-skipped units; leave pump running until the bar converges."""
        from src.worker.tasks.autorespond import _tick_autorespond_bar_bounded

        mark_streaming_parse_complete(self.ctx.chat_id, self.ctx.task_key)

        if self._pre_skipped_ids and self.ctx.progress and self._work_units > 0:
            for _vid in self._pre_skipped_ids:
                await _tick_autorespond_bar_bounded(
                    bot=self.ctx.progress_bot,
                    chat_id=self.ctx.chat_id,
                    task_key=self.ctx.task_key,
                    total=self._work_units,
                    locale=self.ctx.locale,
                    footer_failed_line=None,
                    title=self._company.vacancy_title if self._company else None,
                    celery_task_id=self.ctx.celery_task_id,
                    bar_index=self.ctx.bar_index,
                    finish_progress_task=False,
                    streaming_autorespond=True,
                )

        if self._work_units <= 0 and self.ctx.progress:
            from src.services.autorespond_progress import finish_task_group_autorespond_progress

            await finish_task_group_autorespond_progress(
                bot=self.ctx.progress_bot,
                chat_id=self.ctx.chat_id,
                task_key=self.ctx.task_key,
                locale=self.ctx.locale,
                bar_index=self.ctx.bar_index,
                total=0,
                applications_skipped=True,
            )
        elif self._work_units > 0 and self.ctx.progress:
            await maybe_finish_streaming_autorespond_progress(
                bot=self.ctx.progress_bot,
                chat_id=self.ctx.chat_id,
                task_key=self.ctx.task_key,
                locale=self.ctx.locale,
                bar_index=self.ctx.bar_index,
            )

        logger.info(
            "streaming_autorespond_finalize",
            company_id=self.ctx.company_id,
            task_key=self.ctx.task_key,
            queued=self._work_units,
            pre_skipped=len(self._pre_skipped_ids),
            pump_started=self._pump_started,
        )
        return {
            "status": "ok",
            "queued": self._work_units,
            "skipped": len(self._pre_skipped_ids),
            "failed": 0,
            "employer_tests": 0,
            "trigger": self.ctx.trigger,
            "streaming": True,
        }
