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

        truncated = description[:8000]
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
                max_tokens=20000,
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
        count: int = 10,
        language: str = "ru",
    ) -> str | None:
        keywords_joined = ", ".join(keywords)
        count_instruction = (
            f"ненумерованный список из ровно {count} должностных обязанностей, "
            if count > 0
            else "ненумерованный список не более чем из 30 должностных обязанностей, "
        )
        prompt = (
            f"Чат, ты мой карьерный консультант, HR-директор с опытом в 30 лет. Ты специалист, который понимает об устройстве на работу и развитии карьеры в найме абсолютно всё. "
            f"Составь для резюме на позицию '{resume_title}' "
            f"{count_instruction}"
            f"который включает следующие ключевые слова: "
            f'"[{keywords_joined}]".\n'
            f"Каждое из этих слов должно присутствовать хотя бы один раз. "
            f"Слова можно склонять и менять на множественное число.\n"
            f"Не делай каждую позицию из списка сильно длинной.\n"
            f"Не используй специальные символы и форматирование: "
            f"никаких **, *, >, +, %, номеров и прочей разметки. "
            f"Только простой текст, каждый пункт начинай с дефиса (-).\n\n"
            f"Обязанности должны быть описаны в стиле: {style}\n\n"
            f"Весь ответ напиши на языке: {language}"
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                timeout=60,
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
        resume_title: str,
        keywords: list[str],
        style: str,
        count: int = 10,
        language: str = "ru",
    ) -> AsyncGenerator[str, None]:
        keywords_joined = ", ".join(keywords)
        count_instruction = (
            f"ненумерованный список из ровно {count} должностных обязанностей, "
            if count > 0
            else "ненумерованный список не более чем из 30 должностных обязанностей, "
        )
        prompt = (
            f"Чат, ты мой карьерный консультант, HR-директор с опытом в 30 лет. Ты специалист, который понимает об устройстве на работу и развитии карьеры в найме абсолютно всё. "
            f"Составь для резюме на позицию '{resume_title}' "
            f"{count_instruction}"
            f"который включает следующие ключевые слова: "
            f'"[{keywords_joined}]".\n'
            f"Каждое из этих слов должно присутствовать хотя бы один раз. "
            f"Слова можно склонять и менять на множественное число.\n"
            f"Не делай каждую позицию из списка сильно длинной.\n"
            f"Не используй специальные символы и форматирование: "
            f"никаких **, *, >, +, %, номеров и прочей разметки. "
            f"Только простой текст, каждый пункт начинай с дефиса (-).\n\n"
            f"Обязанности должны быть описаны в стиле: {style}\n\n"
            f"Весь ответ напиши на языке: {language}"
        )
        chunk_count = 0
        max_chunk_len = 0
        total_chars = 0
        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                timeout=60,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100000,
                temperature=0.7,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue
                text = getattr(delta, "reasoning_content", None) or delta.content
                if text:
                    chunk_count += 1
                    max_chunk_len = max(max_chunk_len, len(text))
                    total_chars += len(text)
                    yield text
        except Exception as exc:
            logger.error("OpenAI streaming failed", error=str(exc))
        finally:
            logger.info(
                "OpenAI stream stats",
                chunk_count=chunk_count,
                max_chunk_len=max_chunk_len,
                total_chars=total_chars,
            )
