"""Async OpenAI client wrapper with streaming support."""

from collections.abc import AsyncGenerator

import httpx
from openai import AsyncOpenAI

from src.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

MAX_DESCRIPTION_LENGTH = 8000
_COMPAT_DESCRIPTION_LIMIT = 4000

_COMPATIBILITY_SYSTEM_PROMPT = (
    "Ты — профессиональный HR-аналитик.\n"
    "Твоя задача: оценить совместимость кандидата и вакансии.\n"
    "Ты получаешь:\n"
    "1. Название вакансии, требуемые навыки и описание.\n"
    "2. Технический стек кандидата и описание его опыта работы.\n\n"
    "[ПРАВИЛА]\n"
    "1. Сравни стек кандидата с требуемыми навыками вакансии.\n"
    "   Каждая совпадающая или близко связанная технология добавляет баллы.\n"
    "2. Оцени релевантность опыта: соответствует ли уровень и домен\n"
    "   кандидата требованиям вакансии?\n"
    "3. Название вакансии задаёт контекст важности каждого навыка.\n"
    "4. Верни ТОЛЬКО одно целое число от 0 до 100. Без пояснений, без лишнего текста.\n"
    "   - 0-20: почти нет совпадений\n"
    "   - 21-50: частичное совпадение, не хватает ключевых требований\n"
    "   - 51-75: хорошее совпадение, большинство требований покрыто\n"
    "   - 76-100: сильное совпадение, покрывает почти все требования"
)


class AIClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self._api_key = api_key or settings.openai_api_key
        self._base_url = base_url or settings.openai_base_url
        self._model = model or settings.openai_model
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            max_retries=5,
        )

    async def extract_keywords(self, description: str) -> list[str]:
        if not description.strip():
            return []

        truncated = description[:MAX_DESCRIPTION_LENGTH]
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=120,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты — профессиональный HR-аналитик. "
                            "Твоя задача — извлекать из описания вакансии "
                            "ТОЛЬКО профессиональные ключевые слова, "
                            "которые описывают hard skills, технологии, "
                            "инструменты, языки программирования, "
                            "фреймворки, методологии, профессиональные "
                            "навыки и зоны ответственности.\n"
                            "[ПРАВИЛА]\n"
                            "1. Извлекай: названия технологий (Python, React, Docker), "
                            "инструменты (Git, Jira, Figma), методологии (Agile, Scrum, CI/CD), "
                            "профессиональные навыки (тестирование, код-ревью, архитектура), "
                            "предметные области (финтех, e-commerce, ML).\n"
                            "2. НЕ извлекай: формат работы (удалённая работа, офис, гибрид), "
                            "условия (ДМС, отпуск, бонусы, зарплата), "
                            "soft skills (коммуникабельность, ответственность, командная работа), "
                            "общие фразы (опыт работы, высшее образование, знание английского).\n"
                            "3. Приводи ключевые слова в каноничной форме: "
                            "'JavaScript' а не 'знание JavaScript', "
                            "'микросервисы' а не 'разработка микросервисов'.\n"
                            "4. Возвращай ТОЛЬКО список через запятую, без пояснений, "
                            "без нумерации, без лишних символов."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Извлеки профессиональные ключевые слова из вакансии:\n\n{truncated}"
                        ),
                    },
                ],
                max_tokens=20000,
                temperature=0.2,
            )
            raw = response.choices[0].message.content or ""
            return [kw.strip() for kw in raw.split(",") if kw.strip()]
        except Exception as exc:
            logger.error("OpenAI keyword extraction failed", error=str(exc))
            return []

    async def calculate_compatibility(
        self,
        vacancy_title: str,
        vacancy_skills: list[str],
        vacancy_description: str,
        user_tech_stack: list[str],
        user_work_experience: str,
    ) -> float:
        user_content = (
            f"Вакансия: {vacancy_title}\n"
            f"Требуемые навыки: {', '.join(vacancy_skills)}\n"
            f"Описание (сокращённое): {vacancy_description[:_COMPAT_DESCRIPTION_LIMIT]}\n\n"
            f"Стек кандидата: {', '.join(user_tech_stack)}\n"
            f"Опыт кандидата: {user_work_experience}"
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=60,
                messages=[
                    {"role": "system", "content": _COMPATIBILITY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
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

    async def stream_key_phrases(
        self,
        prompt: str,
    ) -> AsyncGenerator[str, None]:
        chunk_count = 0
        max_chunk_len = 0
        total_chars = 0
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
