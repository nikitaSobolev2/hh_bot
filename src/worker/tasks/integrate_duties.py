"""Celery task for integrating parsing keywords into work experience duties."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.constants import AppSettingKey, TaskName
from src.core.logging import get_logger
from src.services.ai.duties_integration import (
    IntegratedWorkExperienceBlock,
    build_integrated_duties_payload,
    format_integrated_duties_report,
    parse_integrated_duties_response,
)
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)

INTEGRATED_DUTIES_KEYWORD_COUNT = 25


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name=TaskName.INTEGRATE_DUTIES_TO_WORK_EXPERIENCE,
    max_retries=1,
    default_retry_delay=15,
    soft_time_limit=300,
    time_limit=360,
)
def integrate_duties_to_work_experience_task(
    self,
    parsing_company_id: int,
    user_id: int,
    telegram_chat_id: int,
) -> dict:
    return run_async(
        lambda sf: _integrate_duties_async(
            sf,
            self,
            parsing_company_id,
            user_id,
            telegram_chat_id,
        )
    )


def _build_idempotency_key(parsing_company_id: int) -> str:
    time_bucket = int(datetime.now(UTC).timestamp()) // 300
    return f"integrate_duties:{parsing_company_id}:{time_bucket}"


async def _save_task_record(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    celery_task,
    user_id: int,
    idempotency_key: str,
    parsing_company_id: int,
    status: str,
    generated_payload: dict | None = None,
    error_message: str | None = None,
) -> None:
    from sqlalchemy.exc import IntegrityError

    from src.models.task import CompanyIntegrateDutiesTask

    celery_task_id = celery_task.request.id if celery_task.request else None

    async with session_factory() as session:
        record = CompanyIntegrateDutiesTask(
            celery_task_id=celery_task_id,
            task_type="integrate_duties",
            user_id=user_id,
            status=status,
            idempotency_key=idempotency_key,
            parsing_company_id=parsing_company_id,
            generated_payload=generated_payload,
            error_message=error_message,
        )
        session.add(record)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.warning(
                "Integrate duties task record already exists, skipping",
                idempotency_key=idempotency_key,
                status=status,
            )


async def _notify_user(
    bot,
    chat_id: int,
    text: str,
    *,
    reply_markup=None,
) -> None:
    from src.services.ai.streaming import _send_with_retry

    await _send_with_retry(
        bot,
        chat_id,
        text=text,
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


async def _integrate_duties_async(
    session_factory: async_sessionmaker[AsyncSession],
    task,
    parsing_company_id: int,
    user_id: int,
    telegram_chat_id: int,
) -> dict:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from src.bot.modules.parsing.keyboards import integrate_duties_result_keyboard
    from src.config import settings as app_settings
    from src.core.i18n import get_text
    from src.repositories.app_settings import AppSettingRepository
    from src.repositories.parsing import (
        AggregatedResultRepository,
        ParsingCompanyRepository,
    )
    from src.repositories.task import CeleryTaskRepository
    from src.repositories.user import UserRepository
    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient, close_ai_client
    from src.services.ai.prompts import (
        WorkExperienceInput,
        build_integrate_duties_system_prompt,
        build_integrate_duties_user_content,
    )
    from src.worker.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("integrate_duties")

    async with session_factory() as session:
        settings_repo = AppSettingRepository(session)
        enabled = await settings_repo.get_value(
            AppSettingKey.TASK_INTEGRATE_DUTIES_ENABLED,
            default=True,
        )
        if not enabled:
            return {"status": "disabled"}

        cb_threshold = await settings_repo.get_value(
            AppSettingKey.CB_INTEGRATE_DUTIES_FAILURE_THRESHOLD,
            default=5,
        )
        cb_timeout = await settings_repo.get_value(
            AppSettingKey.CB_INTEGRATE_DUTIES_RECOVERY_TIMEOUT,
            default=60,
        )
        cb.update_config(
            failure_threshold=int(cb_threshold),
            recovery_timeout=int(cb_timeout),
        )

    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    idempotency_key = _build_idempotency_key(parsing_company_id)

    async with session_factory() as session:
        task_repo = CeleryTaskRepository(session)
        existing = await task_repo.get_by_idempotency_key(idempotency_key)
        if existing and existing.status == "completed":
            return {"status": "already_completed"}

    locale = "ru"
    async with session_factory() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)
        if user:
            locale = user.language_code or "ru"

    bot = Bot(
        token=app_settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    try:
        async with session_factory() as session:
            company_repo = ParsingCompanyRepository(session)
            agg_repo = AggregatedResultRepository(session)
            we_repo = WorkExperienceRepository(session)

            company = await company_repo.get_by_id(parsing_company_id)
            if not company:
                return {"status": "error", "message": "Company not found"}

            agg = await agg_repo.get_by_company(parsing_company_id)
            if not agg or not agg.top_keywords:
                await _notify_user(
                    bot,
                    telegram_chat_id,
                    get_text("integrate-duties-error-no-keywords", locale),
                )
                return {"status": "error", "message": "No aggregated keywords"}

            sorted_kw = sorted(agg.top_keywords.items(), key=lambda x: -x[1])
            keywords = [kw for kw, _ in sorted_kw[:INTEGRATED_DUTIES_KEYWORD_COUNT]]
            if not keywords:
                await _notify_user(
                    bot,
                    telegram_chat_id,
                    get_text("integrate-duties-error-no-keywords", locale),
                )
                return {"status": "error", "message": "No keywords"}

            work_experiences = await we_repo.get_active_by_user(user_id)
            entries = [
                WorkExperienceInput(
                    work_exp_id=we.id,
                    company_name=we.company_name,
                    stack=we.stack,
                    title=we.title,
                    period=we.period,
                    achievements=we.achievements,
                    duties=we.duties,
                )
                for we in work_experiences
                if we.duties and we.duties.strip()
            ]
            if not entries:
                await _notify_user(
                    bot,
                    telegram_chat_id,
                    get_text("integrate-duties-error-no-duties", locale),
                )
                return {"status": "error", "message": "No work experiences with duties"}

            allowed_ids = {entry.work_exp_id for entry in entries}
            metadata = {
                entry.work_exp_id: {
                    "company_name": entry.company_name,
                    "title": entry.title,
                }
                for entry in entries
            }

        user_content = build_integrate_duties_user_content(
            company.vacancy_title,
            keywords,
            entries,
        )
        system_prompt = build_integrate_duties_system_prompt()

        ai = AIClient()
        try:
            raw = await ai.generate_text(
                user_content,
                system_prompt=system_prompt,
                temperature=0.3,
            )
        finally:
            await close_ai_client(ai)

        parsed_blocks = parse_integrated_duties_response(raw, allowed_ids)
        enriched_blocks = [
            IntegratedWorkExperienceBlock(
                work_exp_id=block.work_exp_id,
                company_name=metadata[block.work_exp_id]["company_name"],
                title=metadata[block.work_exp_id]["title"],
                duties=block.duties,
            )
            for block in parsed_blocks
        ]
        payload = build_integrated_duties_payload(
            vacancy_title=company.vacancy_title,
            keywords_used=keywords,
            blocks=enriched_blocks,
        )

        async with session_factory() as session:
            agg_repo = AggregatedResultRepository(session)
            agg = await agg_repo.get_by_company(parsing_company_id)
            if agg:
                agg.integrated_duties = payload
                agg.integrated_duties_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()

        report_text = format_integrated_duties_report(payload, locale)
        if len(report_text) > 4000:
            report_text = report_text[:3900] + "\n…"

        header = get_text(
            "integrate-duties-completed-header",
            locale,
            title=company.vacancy_title,
        )
        await _notify_user(
            bot,
            telegram_chat_id,
            f"{header}\n\n{report_text}",
            reply_markup=integrate_duties_result_keyboard(parsing_company_id, locale=locale),
        )

        await _save_task_record(
            session_factory,
            celery_task=task,
            user_id=user_id,
            idempotency_key=idempotency_key,
            parsing_company_id=parsing_company_id,
            status="completed",
            generated_payload=payload,
        )

        cb.record_success()
        return {"status": "completed", "blocks": len(enriched_blocks)}

    except Exception as exc:
        cb.record_failure()
        await _save_task_record(
            session_factory,
            celery_task=task,
            user_id=user_id,
            idempotency_key=idempotency_key,
            parsing_company_id=parsing_company_id,
            status="failed",
            error_message=str(exc),
        )
        try:
            await _notify_user(
                bot,
                telegram_chat_id,
                get_text("integrate-duties-error-failed", locale),
            )
        except Exception:
            logger.exception("Failed to notify user about integrate duties error")
        logger.error("Integrate duties task failed", error=str(exc))
        raise
    finally:
        await bot.session.close()
