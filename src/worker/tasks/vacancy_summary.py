"""Celery task for the vacancy summary (about-me) generation feature."""

from __future__ import annotations

import re

from src.core.constants import AppSettingKey
from src.core.logging import get_logger
from src.worker.app import celery_app
from src.worker.base_task import HHBotTask
from src.worker.utils import run_async

logger = get_logger(__name__)

_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")

_AGENT_OUTRO_MARKERS = ("Если хотите", "Хотите, чтобы", "Могу подготовить")
_INTRO_PHRASES = ("Вот профессиональный", "Составляю", "Вот текст", "Готово.", "Вот ваш")


def _strip_agent_wrapper(text: str) -> str:
    """Remove agent intro/outro so only the summary content remains."""
    if not text or not text.strip():
        return text
    result = text.strip()

    # Strip trailing outro (upsell, questions)
    for marker in _AGENT_OUTRO_MARKERS:
        idx = result.find(marker)
        if idx >= 0:
            result = result[:idx].rstrip()
            break

    # Strip leading intro: before first "---" or before first real paragraph
    if "---" in result:
        parts = result.split("---", 2)
        if len(parts) >= 2:
            before, after = parts[0].strip(), "---".join(parts[1:]).strip()
            if before and not any(
                before.lower().startswith(p.lower()) for p in ("Я ", "🔥", "⭐", "⚠")
            ):
                # Do not drop `before` if it already contains section markers (RU body may follow
                # an English preamble — Cyrillic in the intro alone is not enough).
                has_section_markers = "🔥" in before or "⭐" in before or "⚠" in before
                if not has_section_markers:
                    result = after

    # Remove leading intro phrase if no --- was used
    for phrase in _INTRO_PHRASES:
        if result.lower().startswith(phrase.lower()):
            idx = result.find("\n\n")
            if idx > 0:
                result = result[idx + 2 :].lstrip()
            break

    # Remove trailing --- separator left after stripping outro
    result = result.rstrip()
    if result.endswith("---"):
        result = result[:-3].rstrip()
    return result


def _vacancy_summary_output_meets_format(text: str) -> bool:
    """Return True if the about-me text matches the expected RU body + --- + EN tail shape."""
    if not text or not text.strip():
        return False
    if "---" not in text:
        return False
    main, sep, tail = text.partition("---")
    if not sep:
        return False
    main = main.strip()
    tail = tail.strip()
    if not main or not tail:
        return False
    if not _CYRILLIC_RE.search(main):
        return False
    if "🔥" not in main:
        return False
    if "⭐" not in main:
        return False
    return "⚠" in main


@celery_app.task(
    bind=True,
    base=HHBotTask,
    name="vacancy_summary.generate",
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=240,
    time_limit=300,
)
def generate_vacancy_summary_task(
    self,
    summary_id: int,
    user_id: int,
    excluded_industries: str | None,
    location: str | None,
    remote_preference: str | None,
    additional_notes: str | None,
    chat_id: int,
    message_id: int,
    locale: str = "ru",
    context: str = "",
) -> dict:
    return run_async(
        lambda sf: _generate_summary_async(
            self,
            sf,
            summary_id,
            user_id,
            excluded_industries,
            location,
            remote_preference,
            additional_notes,
            chat_id,
            message_id,
            locale,
            context,
        )
    )


async def _generate_summary_async(
    task: HHBotTask,
    session_factory,
    summary_id: int,
    user_id: int,
    excluded_industries: str | None,
    location: str | None,
    remote_preference: str | None,
    additional_notes: str | None,
    chat_id: int,
    message_id: int,
    locale: str,
    context: str = "",
) -> dict:
    from src.core.i18n import get_text
    from src.repositories.vacancy_summary import VacancySummaryRepository
    from src.repositories.work_experience import WorkExperienceRepository
    from src.services.ai.client import AIClient
    from src.services.ai.prompts import (
        WorkExperienceEntry,
        build_vacancy_summary_system_prompt,
        build_vacancy_summary_user_content,
    )

    enabled = await task.check_enabled(AppSettingKey.TASK_VACANCY_SUMMARY_ENABLED, session_factory)
    if not enabled:
        return {"status": "disabled"}

    cb = await task.load_circuit_breaker(
        "vacancy_summary",
        AppSettingKey.CB_VACANCY_SUMMARY_FAILURE_THRESHOLD,
        AppSettingKey.CB_VACANCY_SUMMARY_RECOVERY_TIMEOUT,
        session_factory,
    )
    if not cb.is_call_allowed():
        return {"status": "circuit_open"}

    idempotency_key = f"vacancy_summary:{summary_id}"
    if await task.is_already_completed(idempotency_key, session_factory):
        return {"status": "already_completed"}

    async with session_factory() as session:
        we_repo = WorkExperienceRepository(session)
        raw_experiences = await we_repo.get_active_by_user(user_id)

    experiences = [
        WorkExperienceEntry(
            company_name=e.company_name,
            stack=e.stack,
            title=e.title,
            period=e.period,
            achievements=e.achievements,
            duties=e.duties,
        )
        for e in raw_experiences
    ]

    from src.bot.modules.autoparse.services import derive_tech_stack_from_experiences

    tech_stack = derive_tech_stack_from_experiences(raw_experiences)

    ai_client = AIClient()
    system_prompt = build_vacancy_summary_system_prompt()
    user_content = build_vacancy_summary_user_content(
        work_experiences=experiences,
        tech_stack=tech_stack,
        excluded_industries=excluded_industries,
        location=location,
        remote_preference=remote_preference,
        additional_notes=additional_notes,
    )
    if context == "regenerate":
        user_content += (
            "\n\n[ВАЖНО] Сгенерируй новый, отличающийся вариант текста «О себе». "
            "Сохрани ТОЧНО ту же шестисекционную структуру и эмодзи из system prompt (🔥 ⭐️ ⚠️, "
            "разделитель ---, английский только после ---). "
            "Меняй только формулировки и примеры; не сокращай до одного абзаца "
            "и не переходи на английский в русской части."
        )

    temperature = 0.45 if context == "regenerate" else 0.35

    async def _generate_once(content: str) -> str:
        raw = await ai_client.generate_text(
            content,
            system_prompt=system_prompt,
            timeout=180,
            max_tokens=2000,
            temperature=temperature,
        )
        cb.record_success()
        return _strip_agent_wrapper(raw)

    try:
        generated_text = await _generate_once(user_content)
        if not _vacancy_summary_output_meets_format(generated_text):
            logger.info(
                "vacancy_summary_format_retry",
                summary_id=summary_id,
            )
            retry_instruction = get_text("vs-ai-format-retry", locale)
            retry_user = f"{user_content}\n\n{retry_instruction}"
            generated_text = await _generate_once(retry_user)
            if not _vacancy_summary_output_meets_format(generated_text):
                logger.warning(
                    "vacancy_summary_format_invalid_after_retry",
                    summary_id=summary_id,
                    validation_failed_after_retry=True,
                )
    except Exception as exc:
        cb.record_failure()
        logger.error("Vacancy summary generation failed", summary_id=summary_id, error=str(exc))
        raise

    async with session_factory() as session:
        repo = VacancySummaryRepository(session)
        summary = await repo.get_by_id(summary_id)
        if summary:
            await repo.update_text(summary, generated_text)
            await session.commit()

    await _notify_user(task, chat_id, message_id, summary_id, locale, context)
    await task.mark_completed(idempotency_key, "vacancy_summary", user_id, session_factory)
    return {"status": "completed", "summary_id": summary_id}


async def _notify_user(
    task: HHBotTask,
    chat_id: int,
    message_id: int,
    summary_id: int,
    locale: str,
    context: str = "",
) -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from src.bot.modules.vacancy_summary.callbacks import VacancySummaryCallback
    from src.core.i18n import get_text

    rows = [
        [
            InlineKeyboardButton(
                text=get_text("vs-btn-view", locale),
                callback_data=VacancySummaryCallback(action="detail", summary_id=summary_id).pack(),
            )
        ]
    ]

    if context == "resume":
        from src.bot.modules.resume.callbacks import ResumeCallback

        rows.append(
            [
                InlineKeyboardButton(
                    text=get_text("res-btn-continue-rec-letters", locale),
                    callback_data=ResumeCallback(action="rec_start").pack(),
                )
            ]
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    bot = task.create_bot()
    try:
        await task.notify_user(
            bot,
            chat_id,
            message_id,
            get_text("vs-generation-completed", locale),
            reply_markup=keyboard,
        )
    finally:
        await bot.session.close()
