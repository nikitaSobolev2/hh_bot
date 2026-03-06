"""Celery task for AI key phrases generation."""

from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.utils import run_async

logger = get_logger(__name__)


@celery_app.task(
    bind=True,
    name="ai.generate_key_phrases",
    max_retries=1,
    default_retry_delay=15,
)
def generate_key_phrases_task(
    self,
    parsing_company_id: int,
    user_id: int,
    style: str,
    keyword_count: int,
) -> dict:
    return run_async(
        _generate_key_phrases_async(self, parsing_company_id, user_id, style, keyword_count)
    )


async def _generate_key_phrases_async(
    task,
    parsing_company_id: int,
    user_id: int,
    style: str,
    keyword_count: int,
) -> dict:
    from src.db.engine import async_session_factory
    from src.models.task import CompanyCreateKeyPhrasesTask
    from src.repositories.app_settings import AppSettingRepository
    from src.repositories.parsing import AggregatedResultRepository, ParsingCompanyRepository
    from src.repositories.task import CeleryTaskRepository
    from src.services.ai.client import AIClient
    from src.worker.circuit_breaker import CircuitBreaker

    cb = CircuitBreaker("keyphrase")

    async with async_session_factory() as session:
        settings_repo = AppSettingRepository(session)
        enabled = await settings_repo.get_value("task_keyphrase_enabled", default=True)
        if not enabled:
            return {"status": "disabled"}

        cb_threshold = await settings_repo.get_value("cb_keyphrase_failure_threshold", default=5)
        cb_timeout = await settings_repo.get_value("cb_keyphrase_recovery_timeout", default=60)
        cb.update_config(failure_threshold=int(cb_threshold), recovery_timeout=int(cb_timeout))

    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    idempotency_key = f"keyphrase:{parsing_company_id}:{style}:{keyword_count}"

    async with async_session_factory() as session:
        task_repo = CeleryTaskRepository(session)
        existing = await task_repo.get_by_idempotency_key(idempotency_key)
        if existing and existing.status == "completed":
            return {"status": "already_completed"}

    try:
        async with async_session_factory() as session:
            agg_repo = AggregatedResultRepository(session)
            company_repo = ParsingCompanyRepository(session)

            company = await company_repo.get_by_id(parsing_company_id)
            if not company:
                return {"status": "error", "message": "Company not found"}

            agg = await agg_repo.get_by_company(parsing_company_id)
            if not agg or not agg.top_keywords:
                return {"status": "error", "message": "No aggregated keywords"}

            sorted_kw = sorted(agg.top_keywords.items(), key=lambda x: -x[1])
            top_keywords = [kw for kw, _ in sorted_kw[:keyword_count]]

        ai = AIClient()
        phrases = await ai.generate_key_phrases(company.vacancy_title, top_keywords, style)

        async with async_session_factory() as session:
            agg_repo = AggregatedResultRepository(session)
            agg = await agg_repo.get_by_company(parsing_company_id)
            if agg:
                agg.key_phrases = phrases
                agg.key_phrases_style = style

            task_record = CompanyCreateKeyPhrasesTask(
                celery_task_id=task.request.id if task.request else None,
                task_type="create_key_phrases",
                user_id=user_id,
                status="completed",
                idempotency_key=idempotency_key,
                parsing_company_id=parsing_company_id,
                style=style,
                keyword_count=keyword_count,
                generated_phrases=phrases,
            )
            session.add(task_record)
            await session.commit()

        cb.record_success()
        return {"status": "completed", "phrases_length": len(phrases or "")}

    except Exception as exc:
        cb.record_failure()

        async with async_session_factory() as session:
            task_record = CompanyCreateKeyPhrasesTask(
                celery_task_id=task.request.id if task.request else None,
                task_type="create_key_phrases",
                user_id=user_id,
                status="failed",
                idempotency_key=idempotency_key,
                parsing_company_id=parsing_company_id,
                style=style,
                keyword_count=keyword_count,
                error_message=str(exc),
            )
            session.add(task_record)
            await session.commit()

        logger.error("Key phrases task failed", error=str(exc))
        raise
