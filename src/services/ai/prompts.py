"""Prompt builders for AI key-phrase generation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkExperienceEntry:
    company_name: str
    stack: str


def _quality_rules() -> str:
    return (
        "[ТРЕБОВАНИЯ К КАЧЕСТВУ]\n"
        "- Каждый пункт должен описывать конкретную задачу или зону ответственности, "
        "а не абстрактное достижение.\n"
        "- ЗАПРЕЩЕНО выдумывать цифры, проценты, метрики и статистику. "
        "Не пиши 'сократил на 30%', 'ускорил на 45%', 'до 99.9% аптайма' и подобное.\n"
        "- Ключевые слова должны быть вплетены в текст естественно. "
        "Плохо: 'Оформлял стили с помощью CSS'. "
        "Хорошо: 'Вёрстка адаптивных интерфейсов (HTML, CSS, responsive design)'.\n"
        "- Пиши разнообразно: чередуй структуру фраз, не начинай каждый пункт одинаково.\n"
        "- Пункты должны звучать как реальный опыт специалиста, "
        "а не как шаблонная генерация.\n"
        "- Допускается объединять несколько связанных ключевых слов в одном пункте.\n"
    )


def _format_rules(style: str, language: str) -> str:
    return (
        "[ФОРМАТ]\n"
        "- Каждый пункт начинай с дефиса (-).\n"
        "- Никакого форматирования: без **, *, >, +, номеров.\n"
        f"- Стиль описания: {style}\n"
        f"- Язык: {language}"
    )


def build_key_phrases_prompt(
    resume_title: str,
    main_keywords: list[str],
    secondary_keywords: list[str],
    style: str,
    count: int = 10,
    language: str = "ru",
) -> str:
    main_joined = ", ".join(main_keywords)
    secondary_joined = ", ".join(secondary_keywords)
    count_instruction = (
        f"ненумерованный список из ровно {count} должностных обязанностей, "
        if count > 0
        else "ненумерованный список не более чем из 30 должностных обязанностей, "
    )

    return (
        f"Ты — опытный карьерный консультант. "
        f"Составь для резюме на позицию '{resume_title}' "
        f"{count_instruction}"
        f"который естественно включает ключевые слова из двух групп.\n\n"
        f"Основные ключевые слова (каждое должно появиться хотя бы раз): "
        f"[{main_joined}].\n"
        f"Дополнительные ключевые слова (используй уместные): "
        f"[{secondary_joined}].\n\n"
        f"{_quality_rules()}\n"
        f"{_format_rules(style, language)}"
    )


def build_per_company_key_phrases_prompt(
    resume_title: str,
    main_keywords: list[str],
    secondary_keywords: list[str],
    style: str,
    per_company_count: int,
    language: str,
    work_experiences: list[WorkExperienceEntry],
) -> str:
    main_joined = ", ".join(main_keywords)
    secondary_joined = ", ".join(secondary_keywords)

    companies_block = "\n".join(
        f"  {idx}. {e.company_name} — стек: {e.stack}" for idx, e in enumerate(work_experiences, 1)
    )

    return (
        f"Ты — опытный карьерный консультант. "
        f"Составь для резюме на позицию '{resume_title}' "
        f"ненумерованный список должностных обязанностей, "
        f"который естественно включает ключевые слова из двух групп.\n\n"
        f"Основные ключевые слова (каждое должно появиться хотя бы раз): "
        f"[{main_joined}].\n"
        f"Дополнительные ключевые слова (используй уместные): "
        f"[{secondary_joined}].\n\n"
        f"[ОПЫТ РАБОТЫ КАНДИДАТА]\n"
        f"Кандидат имеет опыт работы в следующих компаниях:\n"
        f"{companies_block}\n\n"
        f"Сгенерируй по {per_company_count} пунктов для каждой компании, "
        f"адаптируя формулировки к указанному стеку компании и используя "
        f"ключевые слова из групп выше.\n"
        f"Выводи результат сгруппировано по компаниям в формате:\n"
        f"Компания: Название компании\n"
        f"- пункт 1\n"
        f"- пункт 2\n\n"
        f"{_quality_rules()}\n"
        f"{_format_rules(style, language)}"
    )
