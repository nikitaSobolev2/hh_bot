"""Async OpenAI client wrapper with streaming support."""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI

from src.config import settings
from src.core.constants import AI_MAX_DESCRIPTION_LENGTH
from src.core.logging import get_logger
from src.schemas.ai import QAPair
from src.services.ai.prompts import (
    build_compatibility_system_prompt,
    build_compatibility_user_content,
    build_improvement_flow_system_prompt,
    build_improvement_flow_user_content,
    build_interview_analysis_system_prompt,
    build_interview_analysis_user_content,
    build_keyword_extraction_system_prompt,
    build_keyword_extraction_user_content,
    build_vacancy_analysis_system_prompt,
    build_vacancy_analysis_user_content,
)

logger = get_logger(__name__)

MAX_DESCRIPTION_LENGTH = AI_MAX_DESCRIPTION_LENGTH

_STACK_PATTERN = re.compile(r"\[Stack\]:\s*(.+)", re.IGNORECASE)
_COMPAT_PATTERN = re.compile(r"\[Compatibility\]:\s*(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class VacancyAnalysis:
    summary: str
    stack: list[str]
    compatibility_score: float


def _parse_vacancy_analysis(text: str) -> VacancyAnalysis:
    """Extract summary, stack list, and compatibility score from the AI response."""
    stack_match = _STACK_PATTERN.search(text)
    compat_match = _COMPAT_PATTERN.search(text)

    stack = [s.strip() for s in stack_match.group(1).split(",") if s.strip()] if stack_match else []
    compat = min(float(compat_match.group(1)), 100.0) if compat_match else 0.0

    if stack_match:
        summary = text[: stack_match.start()].strip()
    elif compat_match:
        summary = text[: compat_match.start()].strip()
    else:
        summary = text.strip()

    return VacancyAnalysis(summary=summary, stack=stack, compatibility_score=compat)


class AIClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        rate_limiter=None,
    ) -> None:
        self._api_key = api_key or settings.openai_api_key
        self._base_url = base_url or settings.openai_base_url
        self._model = model or settings.openai_model
        self._rate_limiter = rate_limiter
        # max_retries=1: retry once on transient errors (429, 500, timeout) then
        # let the caller decide — Celery tasks handle their own retry logic.
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            max_retries=1,
        )

    async def _acquire_rate_limit(self) -> None:
        """Wait for an AI rate-limit slot if a limiter is configured."""
        if self._rate_limiter is not None:
            await self._rate_limiter.acquire()

    async def extract_keywords(self, description: str) -> list[str]:
        if not description.strip():
            return []

        truncated = description[:MAX_DESCRIPTION_LENGTH]
        messages = [
            {"role": "system", "content": build_keyword_extraction_system_prompt()},
            {"role": "user", "content": build_keyword_extraction_user_content(truncated)},
        ]
        try:
            await self._acquire_rate_limit()
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=120,
                messages=messages,
                max_tokens=20000,
                temperature=0.2,
            )
            raw = response.choices[0].message.content or ""
            return [kw.strip() for kw in raw.split(",") if kw.strip()]
        except Exception as exc:
            logger.error("OpenAI keyword extraction failed", error=str(exc))
            return []

    async def analyze_vacancy(
        self,
        vacancy_title: str,
        vacancy_skills: list[str],
        vacancy_description: str,
        user_tech_stack: list[str],
        user_work_experience: str,
    ) -> VacancyAnalysis:
        """Analyse a vacancy against the candidate profile in a single LLM call.

        Returns a summary of positives/negatives, a parsed tech stack, and the
        compatibility score — all extracted from the structured model response.
        """
        messages = [
            {
                "role": "system",
                "content": build_vacancy_analysis_system_prompt(
                    user_tech_stack=user_tech_stack,
                    user_work_experience=user_work_experience,
                ),
            },
            {
                "role": "user",
                "content": build_vacancy_analysis_user_content(
                    vacancy_title=vacancy_title,
                    vacancy_skills=vacancy_skills,
                    vacancy_description=vacancy_description,
                ),
            },
        ]
        try:
            await self._acquire_rate_limit()
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=120,
                messages=messages,
                max_tokens=2000,
                temperature=0.2,
            )
            raw = (response.choices[0].message.content or "").strip()
            return _parse_vacancy_analysis(raw)
        except Exception as exc:
            logger.error("Vacancy analysis failed", error=str(exc))
            return VacancyAnalysis(summary="", stack=[], compatibility_score=0.0)

    async def calculate_compatibility(
        self,
        vacancy_title: str,
        vacancy_skills: list[str],
        vacancy_description: str,
        user_tech_stack: list[str],
        user_work_experience: str,
    ) -> float:
        messages = [
            {"role": "system", "content": build_compatibility_system_prompt()},
            {
                "role": "user",
                "content": build_compatibility_user_content(
                    vacancy_title=vacancy_title,
                    vacancy_skills=vacancy_skills,
                    vacancy_description=vacancy_description,
                    user_tech_stack=user_tech_stack,
                    user_work_experience=user_work_experience,
                ),
            },
        ]
        try:
            await self._acquire_rate_limit()
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=60,
                messages=messages,
                max_tokens=10,
                temperature=0.1,
            )
            raw = (response.choices[0].message.content or "").strip()
            digits = "".join(c for c in raw if c.isdigit())
            return min(float(int(digits)), 100.0) if digits else 0.0
        except Exception as exc:
            logger.error("Compatibility scoring failed", error=str(exc))
            return 0.0

    async def generate_key_phrases(
        self,
        prompt: str,
    ) -> str | None:
        try:
            await self._acquire_rate_limit()
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=300,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100000,
                temperature=0.7,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            logger.error("OpenAI key phrases generation failed", error=str(exc))
            return None

    async def analyze_interview(
        self,
        vacancy_title: str,
        vacancy_description: str | None,
        company_name: str | None,
        experience_level: str | None,
        questions_answers: list[QAPair],
        user_improvement_notes: str | None,
    ) -> str:
        """Analyze interview Q&A against the vacancy and return a structured report.

        The response contains an [InterviewSummaryStart/End] block and zero or
        more [ImproveStart/End] blocks as defined in the system prompt.
        """
        messages = [
            {
                "role": "system",
                "content": build_interview_analysis_system_prompt(),
            },
            {
                "role": "user",
                "content": build_interview_analysis_user_content(
                    vacancy_title=vacancy_title,
                    vacancy_description=vacancy_description,
                    company_name=company_name,
                    experience_level=experience_level,
                    questions_answers=questions_answers,
                    user_improvement_notes=user_improvement_notes,
                ),
            },
        ]
        try:
            await self._acquire_rate_limit()
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=180,
                messages=messages,
                max_tokens=4000,
                temperature=0.3,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.error("Interview analysis failed", error=str(exc))
            return ""

    async def generate_improvement_flow(
        self,
        technology_title: str,
        improvement_summary: str,
        vacancy_title: str,
        vacancy_description: str | None,
    ) -> str:
        """Generate a step-by-step improvement guide for a specific technology weakness."""
        messages = [
            {
                "role": "system",
                "content": build_improvement_flow_system_prompt(),
            },
            {
                "role": "user",
                "content": build_improvement_flow_user_content(
                    technology_title=technology_title,
                    improvement_summary=improvement_summary,
                    vacancy_title=vacancy_title,
                    vacancy_description=vacancy_description,
                ),
            },
        ]
        try:
            await self._acquire_rate_limit()
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=180,
                messages=messages,
                max_tokens=3000,
                temperature=0.4,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.error("Improvement flow generation failed", error=str(exc))
            return ""

    async def generate_text(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        timeout: int = 180,
        max_tokens: int = 4000,
        temperature: float = 0.5,
    ) -> str:
        """Send a prompt and return the full text response.

        If system_prompt is provided, sends [system, user] messages; otherwise
        sends only the user prompt. Use system_prompt when the model must
        follow a specific output format (e.g. [QAStart]:key/[QAEnd]:key).
        """
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        try:
            await self._acquire_rate_limit()
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=timeout,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            logger.error("OpenAI generate_text failed", error=str(exc))
            raise

    async def stream_key_phrases(
        self,
        prompt: str,
    ) -> AsyncGenerator[str, None]:
        chunk_count = 0
        max_chunk_len = 0
        total_chars = 0
        await self._acquire_rate_limit()
        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100000,
                temperature=0.7,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue
                text = delta.content
                if text:
                    chunk_count += 1
                    max_chunk_len = max(max_chunk_len, len(text))
                    total_chars += len(text)
                    yield text
        finally:
            logger.info(
                "OpenAI stream stats",
                chunk_count=chunk_count,
                max_chunk_len=max_chunk_len,
                total_chars=total_chars,
            )
