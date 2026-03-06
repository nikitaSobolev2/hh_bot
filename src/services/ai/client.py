"""Async OpenAI client wrapper with streaming support."""

from collections.abc import AsyncGenerator

from openai import AsyncOpenAI

from src.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


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
        self._client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

    async def extract_keywords(self, description: str) -> list[str]:
        if not description.strip():
            return []

        truncated = description[:4000]
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=30,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты — ассистент для анализа вакансий. "
                            "Из текста вакансии извлекай ключевые технологии, "
                            "инструменты, фреймворки и профессиональные навыки. "
                            "Возвращай ТОЛЬКО список через запятую, без пояснений, "
                            "без нумерации, без лишних символов."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Извлеки ключевые слова из текста вакансии:\n\n{truncated}",
                    },
                ],
                max_tokens=8000,
                temperature=0.2,
            )
            raw = response.choices[0].message.content or ""
            return [kw.strip() for kw in raw.split(",") if kw.strip()]
        except Exception as exc:
            logger.error("OpenAI keyword extraction failed", error=str(exc))
            return []

    async def generate_key_phrases(
        self,
        resume_title: str,
        keywords: list[str],
        style: str,
    ) -> str | None:
        keywords_joined = ", ".join(keywords)
        prompt = (
            f"Составь для резюме на позицию '{resume_title}' "
            f"ненумерованный список должностных обязанностей, "
            f"который включает следующие ключевые слова: "
            f'"[{keywords_joined}]".\n'
            f"Каждое из этих слов должно присутствовать хотя бы один раз. "
            f"Слова можно склонять и менять на множественное число.\n"
            f"Не делай каждую позицию из списка сильно длинной.\n\n"
            f"Обязанности должны быть описаны в стиле: {style}"
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=60,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8000,
                temperature=0.7,
            )
            return response.choices[0].message.content or ""
        except Exception as exc:
            logger.error("OpenAI key phrases generation failed", error=str(exc))
            return None

    async def stream_key_phrases(
        self,
        resume_title: str,
        keywords: list[str],
        style: str,
    ) -> AsyncGenerator[str, None]:
        keywords_joined = ", ".join(keywords)
        prompt = (
            f"Составь для резюме на позицию '{resume_title}' "
            f"ненумерованный список должностных обязанностей, "
            f"который включает следующие ключевые слова: "
            f'"[{keywords_joined}]".\n'
            f"Каждое из этих слов должно присутствовать хотя бы один раз. "
            f"Слова можно склонять и менять на множественное число.\n"
            f"Не делай каждую позицию из списка сильно длинной.\n\n"
            f"Обязанности должны быть описаны в стиле: {style}"
        )
        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                timeout=60,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=8000,
                temperature=0.7,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as exc:
            logger.error("OpenAI streaming failed", error=str(exc))
