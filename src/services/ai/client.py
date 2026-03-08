"""Async OpenAI client wrapper with streaming support."""

from collections.abc import AsyncGenerator

import httpx
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
                timeout=120,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты — профессиональный HR-аналитик. "
                            "Твоя задача — извлекать из описания вакансии ТОЛЬКО профессиональные ключевые слова, "
                            "которые описывают hard skills, технологии, инструменты, языки программирования, "
                            "фреймворки, методологии, профессиональные навыки и зоны ответственности.\n"
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
                        "content": f"Извлеки профессиональные ключевые слова из вакансии:\n\n{truncated}",
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
        main_keywords: list[str],
        secondary_keywords: list[str],
        style: str,
        count: int = 10,
        language: str = "ru",
    ) -> str | None:
        main_joined = ", ".join(main_keywords)
        secondary_joined = ", ".join(secondary_keywords)
        count_instruction = (
            f"ненумерованный список из ровно {count} должностных обязанностей, "
            if count > 0
            else "ненумерованный список не более чем из 30 должностных обязанностей, "
        )
        prompt = (
            f"Ты — опытный карьерный консультант. "
            f"Составь для резюме на позицию '{resume_title}' "
            f"{count_instruction}"
            f"который естественно включает ключевые слова из двух групп.\n\n"
            f'Основные ключевые слова (каждое должно появиться хотя бы раз): [{main_joined}].\n'
            f'Дополнительные ключевые слова (используй уместные): [{secondary_joined}].\n\n'
            f"[ТРЕБОВАНИЯ К КАЧЕСТВУ]\n"
            f"- Каждый пункт должен описывать конкретную задачу или зону ответственности, "
            f"а не абстрактное достижение.\n"
            f"- ЗАПРЕЩЕНО выдумывать цифры, проценты, метрики и статистику. "
            f"Не пиши 'сократил на 30%', 'ускорил на 45%', 'до 99.9% аптайма' и подобное.\n"
            f"- Ключевые слова должны быть вплетены в текст естественно. "
            f"Плохо: 'Оформлял стили с помощью CSS'. "
            f"Хорошо: 'Вёрстка адаптивных интерфейсов (HTML, CSS, responsive design)'.\n"
            f"- Пиши разнообразно: чередуй структуру фраз, не начинай каждый пункт одинаково.\n"
            f"- Пункты должны звучать как реальный опыт специалиста, "
            f"а не как шаблонная генерация.\n"
            f"- Допускается объединять несколько связанных ключевых слов в одном пункте.\n\n"
            f"[ФОРМАТ]\n"
            f"- Каждый пункт начинай с дефиса (-).\n"
            f"- Никакого форматирования: без **, *, >, +, номеров.\n"
            f"- Стиль описания: {style}\n"
            f"- Язык: {language}"
        )
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
        resume_title: str,
        main_keywords: list[str],
        secondary_keywords: list[str],
        style: str,
        count: int = 10,
        language: str = "ru",
    ) -> AsyncGenerator[str, None]:
        main_joined = ", ".join(main_keywords)
        secondary_joined = ", ".join(secondary_keywords)
        count_instruction = (
            f"ненумерованный список из ровно {count} должностных обязанностей, "
            if count > 0
            else "ненумерованный список не более чем из 30 должностных обязанностей, "
        )
        prompt = (
            f"Ты — опытный карьерный консультант. "
            f"Составь для резюме на позицию '{resume_title}' "
            f"{count_instruction}"
            f"который естественно включает ключевые слова из двух групп.\n\n"
            f'Основные ключевые слова (каждое должно появиться хотя бы раз): [{main_joined}].\n'
            f'Дополнительные ключевые слова (используй уместные): [{secondary_joined}].\n\n'
            f"[ТРЕБОВАНИЯ К КАЧЕСТВУ]\n"
            f"- Каждый пункт должен описывать конкретную задачу или зону ответственности, "
            f"а не абстрактное достижение.\n"
            f"- ЗАПРЕЩЕНО выдумывать цифры, проценты, метрики и статистику. "
            f"Не пиши 'сократил на 30%', 'ускорил на 45%', 'до 99.9% аптайма' и подобное.\n"
            f"- Ключевые слова должны быть вплетены в текст естественно. "
            f"Плохо: 'Оформлял стили с помощью CSS'. "
            f"Хорошо: 'Вёрстка адаптивных интерфейсов (HTML, CSS, responsive design)'.\n"
            f"- Пиши разнообразно: чередуй структуру фраз, не начинай каждый пункт одинаково.\n"
            f"- Пункты должны звучать как реальный опыт специалиста, "
            f"а не как шаблонная генерация.\n"
            f"- Допускается объединять несколько связанных ключевых слов в одном пункте.\n\n"
            f"[ФОРМАТ]\n"
            f"- Каждый пункт начинай с дефиса (-).\n"
            f"- Никакого форматирования: без **, *, >, +, номеров.\n"
            f"- Стиль описания: {style}\n"
            f"- Язык: {language}"
        )
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
