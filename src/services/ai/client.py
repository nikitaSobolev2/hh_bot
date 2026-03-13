"""Async OpenAI client wrapper with streaming support."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncGenerator, Callable, Coroutine
from dataclasses import dataclass
from typing import Any

import httpx
from openai import APIStatusError, AsyncOpenAI, RateLimitError

from src.config import settings
from src.core.constants import AI_MAX_DESCRIPTION_LENGTH
from src.core.logging import get_logger
from src.schemas.ai import QAPair
from src.services.ai.prompts import (
    VacancyCompatInput,
    build_batch_compatibility_system_prompt,
    build_batch_compatibility_user_content,
    build_batch_vacancy_analysis_system_prompt,
    build_batch_vacancy_analysis_user_content,
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

# 429 rate limit retry: Cloudflare recommends 30s minimum, exponential backoff
_RATE_LIMIT_MIN_WAIT = 30
_RATE_LIMIT_MAX_RETRIES = 5
# Matches retry_after in JSON-like strings: "retry_after": 30 or 'retry_after': 30
_RETRY_AFTER_RE = re.compile(r"retry_after['\"]?\s*:\s*(\d+)", re.IGNORECASE)


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True if the exception indicates a 429 rate limit."""
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIStatusError) and exc.status_code == 429:
        return True
    return getattr(exc, "status_code", None) == 429


def _extract_retry_after(exc: Exception) -> int:
    """Extract retry_after in seconds from 429 error. Returns _RATE_LIMIT_MIN_WAIT if not found.

    Handles OpenAI RateLimitError, APIStatusError, and Cloudflare-style error bodies.
    """
    # Response headers (Retry-After)
    if hasattr(exc, "response") and exc.response is not None:
        ra = exc.response.headers.get("Retry-After")
        if ra:
            try:
                return max(int(ra), _RATE_LIMIT_MIN_WAIT)
            except ValueError:
                pass

    # Body as dict (OpenAI/Cloudflare JSON)
    if hasattr(exc, "body") and exc.body is not None:
        body = exc.body
        if isinstance(body, dict):
            for key in ("retry_after", "retry-after"):
                ra = body.get(key)
                if ra is not None:
                    try:
                        return max(int(ra), _RATE_LIMIT_MIN_WAIT)
                    except (ValueError, TypeError):
                        pass
            err = body.get("error")
            if isinstance(err, dict) and err.get("retry_after") is not None:
                try:
                    return max(int(err["retry_after"]), _RATE_LIMIT_MIN_WAIT)
                except (ValueError, TypeError, KeyError):
                    pass
        elif isinstance(body, str):
            match = _RETRY_AFTER_RE.search(body)
            if match:
                return max(int(match.group(1)), _RATE_LIMIT_MIN_WAIT)

    # Fallback: regex on string representation (Cloudflare embeds JSON in error string)
    match = _RETRY_AFTER_RE.search(str(exc))
    if match:
        return max(int(match.group(1)), _RATE_LIMIT_MIN_WAIT)
    return _RATE_LIMIT_MIN_WAIT


async def _call_with_rate_limit_retry[T](
    coro_fn: Callable[[], Coroutine[Any, Any, T]],
) -> T:
    """Execute an AI API call, retrying on 429 with exponential backoff.

    Catches RateLimitError and APIStatusError (status 429) including Cloudflare-style
    proxy errors. Uses retry_after from response when available; otherwise 30s minimum.
    """
    last_exc: Exception | None = None
    for attempt in range(_RATE_LIMIT_MAX_RETRIES):
        try:
            return await coro_fn()
        except (RateLimitError, APIStatusError) as exc:
            if not _is_rate_limit_error(exc):
                raise
            last_exc = exc
            if attempt >= _RATE_LIMIT_MAX_RETRIES - 1:
                raise
            wait = _extract_retry_after(exc)
            # Exponential backoff: 30, 60, 120, 240 (cap 300s)
            wait = min(wait * (2**attempt), 300)
            logger.warning(
                "AI rate limited, retrying after wait",
                attempt=attempt + 1,
                wait_seconds=wait,
                retry_after=wait,
            )
            await asyncio.sleep(wait)
    raise last_exc  # type: ignore[misc]


_STACK_PATTERN = re.compile(r"\[Stack\]:\s*(.+)", re.IGNORECASE)
_COMPAT_PATTERN = re.compile(r"\[Compatibility\]:\s*(\d+)", re.IGNORECASE)
_BATCH_VACANCY_COMPAT_PATTERN = re.compile(
    r"\[Vacancy\]:(\w+)\s*\n\s*\[Compatibility\]:(\d+)",
    re.IGNORECASE,
)
_BATCH_VACANCY_START_PATTERN = re.compile(
    r"\[VacancyStart\]:(\w+)",
    re.IGNORECASE,
)


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


def _parse_batch_compat_response(raw: str) -> dict[str, float]:
    """Parse batch compatibility response into {hh_vacancy_id: score}.

    Expects blocks: [Vacancy]:hh_id\n[Compatibility]:72\n[VacancyEnd]:hh_id
    Falls back to [Vacancy]:hh_id\n[Compatibility]:72 if VacancyEnd is missing.
    Missing or malformed entries get score 0.0.
    """
    result: dict[str, float] = {}
    for m in _BATCH_VACANCY_COMPAT_PATTERN.finditer(raw):
        hh_id = m.group(1)
        try:
            score = min(float(m.group(2)), 100.0)
        except (ValueError, IndexError):
            score = 0.0
        result[hh_id] = score
    return result


def _parse_batch_vacancy_analysis(raw: str) -> dict[str, VacancyAnalysis]:
    """Parse batch vacancy analysis response into {hh_vacancy_id: VacancyAnalysis}.

    Splits by [VacancyStart]:hh_id, parses each block with _parse_vacancy_analysis.
    """
    result: dict[str, VacancyAnalysis] = {}
    parts = _BATCH_VACANCY_START_PATTERN.split(raw)
    # parts[0] is text before first match; odd indices are hh_ids, even (after first) are block content
    i = 1
    while i + 1 < len(parts):
        hh_id = parts[i]
        block = parts[i + 1]
        # Block ends at next [VacancyStart] or end; strip trailing [VacancyEnd]:hh_id if present
        end_marker = f"[VacancyEnd]:{hh_id}"
        if end_marker in block:
            block = block.split(end_marker)[0]
        try:
            result[hh_id] = _parse_vacancy_analysis(block.strip())
        except Exception as exc:
            logger.warning(
                "Batch vacancy analysis parse failed for hh_id",
                hh_id=hh_id,
                error=str(exc),
            )
            result[hh_id] = VacancyAnalysis(summary="", stack=[], compatibility_score=0.0)
        i += 2
    return result


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
        # max_retries=0: we handle 429 ourselves with 30s+ backoff; SDK's 9s retry
        # is too short for Cloudflare/proxy rate limits.
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            max_retries=0,
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

        async def _call() -> list[str]:
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

        try:
            return await _call_with_rate_limit_retry(_call)
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

        async def _call() -> VacancyAnalysis:
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

        try:
            return await _call_with_rate_limit_retry(_call)
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

        async def _call() -> float:
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

        try:
            return await _call_with_rate_limit_retry(_call)
        except Exception as exc:
            logger.error("Compatibility scoring failed", error=str(exc))
            return 0.0

    async def calculate_compatibility_batch(
        self,
        vacancies: list[VacancyCompatInput],
        user_tech_stack: list[str],
        user_work_experience: str,
    ) -> dict[str, float]:
        """Score N vacancies in one API call. Returns {hh_vacancy_id: score}."""
        if not vacancies:
            return {}

        messages = [
            {"role": "system", "content": build_batch_compatibility_system_prompt()},
            {
                "role": "user",
                "content": build_batch_compatibility_user_content(
                    vacancies=vacancies,
                    user_tech_stack=user_tech_stack,
                    user_work_experience=user_work_experience,
                ),
            },
        ]
        max_tokens = max(50 * len(vacancies), 100)

        async def _call() -> dict[str, float]:
            await self._acquire_rate_limit()
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=120,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.1,
            )
            raw = (response.choices[0].message.content or "").strip()
            parsed = _parse_batch_compat_response(raw)
            if len(parsed) != len(vacancies):
                logger.warning(
                    "Batch compat parse incomplete",
                    expected=len(vacancies),
                    got=len(parsed),
                )
            return {
                v.hh_vacancy_id: parsed.get(v.hh_vacancy_id, 0.0)
                for v in vacancies
            }

        try:
            return await _call_with_rate_limit_retry(_call)
        except Exception as exc:
            logger.error("Batch compatibility scoring failed", error=str(exc))
            return {v.hh_vacancy_id: 0.0 for v in vacancies}

    async def analyze_vacancies_batch(
        self,
        vacancies: list[VacancyCompatInput],
        user_tech_stack: list[str],
        user_work_experience: str,
    ) -> dict[str, VacancyAnalysis]:
        """Analyse N vacancies in one call. Returns {hh_vacancy_id: VacancyAnalysis}."""
        if not vacancies:
            return {}

        messages = [
            {
                "role": "system",
                "content": build_batch_vacancy_analysis_system_prompt(
                    user_tech_stack=user_tech_stack,
                    user_work_experience=user_work_experience,
                ),
            },
            {
                "role": "user",
                "content": build_batch_vacancy_analysis_user_content(vacancies=vacancies),
            },
        ]
        max_tokens = max(2000 * len(vacancies), 2000)

        async def _call() -> dict[str, VacancyAnalysis]:
            await self._acquire_rate_limit()
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=180,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.2,
            )
            raw = (response.choices[0].message.content or "").strip()
            parsed = _parse_batch_vacancy_analysis(raw)
            for v in vacancies:
                if v.hh_vacancy_id not in parsed:
                    parsed[v.hh_vacancy_id] = VacancyAnalysis(
                        summary="", stack=[], compatibility_score=0.0
                    )
            return parsed

        try:
            return await _call_with_rate_limit_retry(_call)
        except Exception as exc:
            logger.error("Batch vacancy analysis failed", error=str(exc))
            return {
                v.hh_vacancy_id: VacancyAnalysis(
                    summary="", stack=[], compatibility_score=0.0
                )
                for v in vacancies
            }

    async def generate_key_phrases(
        self,
        prompt: str,
    ) -> str:
        async def _call() -> str:
            await self._acquire_rate_limit()
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=300,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100000,
                temperature=0.7,
            )
            return response.choices[0].message.content or ""

        try:
            return await _call_with_rate_limit_retry(_call)
        except Exception as exc:
            logger.error("OpenAI key phrases generation failed", error=str(exc))
            raise

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

        async def _call() -> str:
            await self._acquire_rate_limit()
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=180,
                messages=messages,
                max_tokens=4000,
                temperature=0.3,
            )
            return (response.choices[0].message.content or "").strip()

        try:
            return await _call_with_rate_limit_retry(_call)
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

        async def _call() -> str:
            await self._acquire_rate_limit()
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=180,
                messages=messages,
                max_tokens=3000,
                temperature=0.4,
            )
            return (response.choices[0].message.content or "").strip()

        try:
            return await _call_with_rate_limit_retry(_call)
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

        async def _call() -> str:
            await self._acquire_rate_limit()
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=timeout,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return (response.choices[0].message.content or "").strip()

        try:
            return await _call_with_rate_limit_retry(_call)
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

        async def _create_stream():
            await self._acquire_rate_limit()
            return await self._client.chat.completions.create(
                model=self._model,
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100000,
                temperature=0.7,
                stream=True,
            )

        try:
            stream = await _call_with_rate_limit_retry(_create_stream)
        except Exception as exc:
            logger.error("OpenAI stream_key_phrases create failed", error=str(exc))
            return

        try:
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
